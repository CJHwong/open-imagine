"""The Qwen-Image-2.1 prompt rewriters, through mlx-vlm in this process.

One model per mode. PE-T2I lengthens a request for generate, PE-I2I reads the
picture the run will carry and lengthens an edit instruction. Both are
fine-tuned Qwen3.5-VL 9B, 18.84 GB in bf16, and both answer in JSON after an
optional thinking block.

They run on MLX, the same engine the two image models use, so they share this
process. Its import is deferred to the first rewrite and costs 1.6s, so a studio
that never rewrites never pays it.

The two models do not both fit beside anything, so this adapter keeps at most one
resident and drops it when the other mode asks.

Writing is bound by memory bandwidth: every token reads the whole card. So a card
quantized as it loads writes about twice as fast. Measured 2026-10-23 on an M5 Pro,
ten requests each at the card's own sampling:

    precision   load    write, mean (range)       greedy, same opening words as bf16
    bf16        5.0s    39.7s (20.6 to 68.7)      -
    8-bit       4.4s    20.4s (13.4 to 33.8)      17 to 193 of them
    4-bit       4.2s    23.5s (11.5 to 41.7)      1 to 6, and quoted text split apart

4-bit is not faster in practice: it writes longer answers. 8-bit is the setting.

The cards write English by design: their shipped system prompt says so, and the
4-bit conversion keeps that behaviour. Removing both English-only lines and asking
for the request's language changed nothing in a measured run on 2026-11-03, where a
Chinese request still came back as English.
"""

import contextlib
import io
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from PIL import Image

from studio.l1_entities.errors import Cancelled
from studio.l1_entities.image_job import ReferenceImage
from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_text import (
    MAX_TOKENS,
    smaller_png,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_text import (
    as_rewrite as _as_rewrite,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_text import (
    in_the_request_language as _in_the_request_language,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_text import (
    system_prompt as _system_prompt,
)
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import release_mlx_buffers

# mlx's own default group size, and the one the measurement above used.
QUANTIZE_GROUP_SIZE = 64

# One rewriter in bf16. The module docstring carries the same number.
REWRITER_SIZE = "18.84 GB"

# The files mlx_vlm.utils.get_model_path asks the hub for. The copy is deliberate.
# huggingface_hub's plain local-only lookup is not usable: it also wants README,
# LICENSE and .gitattributes, which mlx_vlm never fetches, so it reports a model
# that is fully on disk as "not fetched". The library's own filter is not read at
# runtime either: importing mlx_vlm costs 1.6s, and this adapter defers that import
# to the first rewrite for exactly that reason. If mlx_vlm widens its filter, this
# line turns optimistic and never pessimistic: it says cached, and the load fetches
# what it would have fetched anyway.
CACHE_FILES = ("*.json", "*.jsonl", "*.safetensors", "*.py", "*.model", "*.tiktoken", "*.txt", "*.jinja")


def in_the_cache(repo: str) -> bool:
    """Whether mlx_vlm can load `repo` without downloading it.

    huggingface_hub's own resolver answers, not a path built here, because the
    cache layout belongs to the library. A cached repo answers in under a
    millisecond and no network is used, so this is cheap enough for startup.

    A directory answers directly. That is how a converted checkpoint, which is a
    local MLX model rather than a hub repo, reaches this line and mlx-vlm.
    """
    if Path(repo).expanduser().is_dir():
        return True

    from huggingface_hub import snapshot_download
    from huggingface_hub.errors import LocalEntryNotFoundError

    try:
        snapshot_download(repo, local_files_only=True, allow_patterns=list(CACHE_FILES))
    except LocalEntryNotFoundError:
        return False
    return True


def cache_line(models: Mapping[str, str]) -> str:
    """One line naming each rewriter mode whose weights are not on disk yet.

    The first rewrite in a mode loads about 19 GB with the progress bar off, so
    the page looks merely busy and the user cannot tell 22 seconds from 19 GB.
    Saying it before the click puts that wait where it can be seen coming.
    """
    fetched = {mode: in_the_cache(repo) for mode, repo in models.items()}
    modes = ", ".join(f"{mode} {'cached' if ok else 'not fetched'}" for mode, ok in fetched.items())
    missing = sum(1 for ok in fetched.values() if not ok)
    if not missing:
        return f"Rewriters: {modes}"
    each = "each " if missing > 1 else ""
    return f"Rewriters: {modes} ({REWRITER_SIZE} {each}to prepare)"


def _quantize(model, config: dict, bits: int) -> None:
    """Quantize a lazily loaded card's language model in place, then make its weights
    resident.

    The vision tower stays in bf16, as mlx-vlm's own loader keeps it. Quantized, its
    position table becomes uint32, and the bilinear weights it reads back in that type
    round every fraction to 0, so the edit card would lose where each patch of the
    picture sits. The tower is small beside the 9B language model.

    The weights are read from disk in this eval, once, on their way to `bits`, so the
    bf16 card is never held whole. Without the eval the first token would pay for it.
    quantize_model prints a line, and this server keeps its terminal quiet.
    """
    import mlx.core as mx
    from mlx_vlm.quant_utils import quantize_model
    from mlx_vlm.utils import skip_multimodal_module

    with contextlib.redirect_stdout(io.StringIO()):
        quantize_model(
            model,
            config,
            QUANTIZE_GROUP_SIZE,
            bits,
            quant_predicate=lambda path, _module: not skip_multimodal_module(path),
        )
    mx.eval(model.parameters())


class Qwen21Rewriter(PromptRewriterGateway):
    def __init__(self, models: Mapping[str, str], quantize: int = 0):
        self._models = dict(models)
        self._quantize = quantize
        self._resident: tuple | None = None

    def modes(self) -> tuple[str, ...]:
        return tuple(self._models)

    def rewrite(
        self,
        prompt: str,
        mode: str,
        references: tuple[ReferenceImage, ...],
        on_writing: Callable[[], None],
        should_stop: Callable[[], bool],
    ) -> PromptRewrite:
        from mlx_vlm import stream_generate
        from mlx_vlm.prompt_utils import apply_chat_template

        model, processor, config, system_prompt = self._resident_for(mode)
        # A PIL image, not a path: the studio tells its user it writes nothing to
        # disk, and mlx-vlm's load_image takes an Image.Image as it takes a path.
        images = [Image.open(io.BytesIO(smaller_png(reference.png))).convert("RGB") for reference in references]
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": _in_the_request_language(prompt)},
        ]
        # apply_chat_template returns a message list only when return_messages is
        # set, and its hint cannot say so, so the string form is taken here.
        formatted = cast(str, apply_chat_template(processor, config, messages, num_images=len(images)))
        # The weights are resident by now, so the load is behind this call, and the
        # caller cannot see that for itself. From here the model writes one segment
        # at a time, and this loop is studio's own, so this is where a stop is seen.
        on_writing()
        written: list[str] = []
        for segment in stream_generate(
            model,
            processor,
            formatted,
            # mlx-vlm's hint for this parameter says str or list[str], and its own
            # process_image only calls load_image for a str: a PIL image is passed
            # straight through. Verified against the installed source, 2026-09-27.
            image=images or None,  # ty: ignore[invalid-argument-type]
            max_tokens=MAX_TOKENS,
            temperature=1.0,
            top_p=0.95,
            top_k=20,
            # The card answers directly. Its thinking block ran to hundreds of tokens
            # and took a 40 second rewrite to 15; see the rewriter load table.
            enable_thinking=False,
            verbose=False,
        ):
            if should_stop():
                raise Cancelled("stopped while rewriting the prompt")
            # A segment, not the text so far: this field is what the tokenizer
            # printed since the last read, and the last segment carries only the
            # flushed tail. So the answer is assembled here and parsed once, at the
            # end, which is how mlx-vlm's own `generate` reads the same stream. The
            # draft filter that call applies belongs to the diffusion streamer,
            # which this call never reaches: this model writes tokens.
            written.append(segment.text)
        return _as_rewrite("".join(written))

    def release(self) -> None:
        if self._resident is None:
            return
        self._resident = None
        release_mlx_buffers()

    def prepare(self) -> None:
        """Load each card once, which fetches it and quantizes it, then free it."""
        try:
            for mode in self._models:
                self._resident_for(mode)
        finally:
            self.release()

    def _resident_for(self, mode: str) -> tuple:
        if self._resident is not None and self._resident[0] == mode:
            return self._resident[1:]
        self.release()
        from huggingface_hub import logging as hub_logging
        from huggingface_hub.utils import disable_progress_bars
        from mlx_vlm import load
        from mlx_vlm.utils import load_config

        # Resolving a cached model still makes huggingface_hub print a line and a
        # progress bar, and this server keeps its terminal quiet. Both of these
        # are runtime switches, so they work whatever imported it first.
        disable_progress_bars()
        hub_logging.set_verbosity_error()
        # A hub id and a local directory both reach mlx-vlm here. The directory
        # form is a converted checkpoint, and `~` is expanded so the config can
        # name one without writing this machine's home path into the repo.
        repo = str(Path(self._models[mode]).expanduser())
        config = load_config(repo)
        # A converted checkpoint carries its own quantization, and quantizing it a
        # second time would read a 4-bit card as if it were bf16.
        if self._quantize and "quantization" not in config:
            model, processor = load(repo, lazy=True)
            _quantize(model, config, self._quantize)
        else:
            model, processor = load(repo)
        self._resident = (mode, model, processor, config, _system_prompt(repo))
        return self._resident[1:]
