"""Krea 2 Turbo through mflux, in this process. One model for text-to-image and img2img.

The model dir holds mflux-community/krea-2-turbo-mflux-q8, stored at int8. mflux
uses the stored bits whatever it is asked for, so this passes no quantize. Unlike
flux2, the Krea2 initializer evaluates every weight when the model is built, so the
build is the whole read of about 22 GB, and nothing can stop it once it starts.

docs/how-to/set-up-models.md has the download recipe.
"""

import json
from collections.abc import Callable
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob, ImageResult
from studio.l3_interface_adapters.gateways.image.krea2.capabilities import MATCH
from studio.l3_interface_adapters.gateways.image.shared.image_sizes import match_reference_size
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import StepHook, release_mlx_buffers
from studio.l3_interface_adapters.gateways.png_images import to_pil, to_png

REGISTRY_KEY = "krea-2"
# The model card's sampler. Named here so that a change of the mflux default does
# not change the images without a change to this file.
SCHEDULER = "er_sde"
INDEXES = (
    "model.safetensors.index.json",
    "text_encoder/model.safetensors.index.json",
    "vae/model.safetensors.index.json",
)
TOKENIZER_FILES = ("tokenizer/tokenizer.json", "tokenizer/tokenizer_config.json")


def missing_files(model_dir: str) -> list[str]:
    """Each file the checkpoint needs that is not on disk.

    mflux fails with a bare FileNotFoundError on a missing shard, and with a
    Hugging Face layout error on a missing VAE shard. A half-done download is
    the usual cause, so this names the files instead.
    """
    root = Path(model_dir)
    if not root.is_dir():
        return [model_dir]
    missing = [name for name in (*INDEXES, *TOKENIZER_FILES) if not (root / name).is_file()]
    for index in INDEXES:
        path = root / index
        if not path.is_file():
            continue
        try:
            shards = sorted(set(json.loads(path.read_text())["weight_map"].values()))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # A copy that stopped partway leaves a truncated index. It is as good as missing.
            missing.append(index)
            continue
        missing += [str(Path(index).parent / shard) for shard in shards if not (path.parent / shard).is_file()]
    return missing


def image_size(job: ImageJob) -> tuple[int, int]:
    """The chosen size, or the reference's shape at about 1 MP.

    mflux stretches the reference to the target size, so a square output from a
    16:9 photo squashes it. Match keeps the shape.
    """
    size = job.options["size"]
    if size != MATCH:
        width, height = (int(side) for side in str(size).split("x"))
        return width, height
    if job.references:
        reference = job.references[0]
        return match_reference_size(reference.width, reference.height)
    return 1024, 1024


def generate_kwargs(job: ImageJob) -> dict:
    """The job as Krea2.generate_image arguments.

    The width and height are always integers: mflux opens `image_path` as a file
    to find a size when either one is missing. The reference goes in as a PIL
    image, which mflux encodes as it is, so no image reaches the disk.
    """
    width, height = image_size(job)
    kwargs = {
        "seed": job.seed,
        "prompt": job.prompt,
        "width": width,
        "height": height,
        "num_inference_steps": job.options["steps"],
        "scheduler": SCHEDULER,
    }
    if job.references:
        kwargs["image_path"] = to_pil(job.references[0].png)
        kwargs["image_strength"] = job.options["strength"]
    return kwargs


def build_model(model_dir: str, hook: StepHook):
    from mflux.models.common.resolution.config_resolution import ConfigResolution
    from mflux.models.krea2.variants import Krea2

    config = ConfigResolution.resolve_restricted(None, REGISTRY_KEY, model_path=model_dir)
    model = Krea2(model_config=config, model_path=model_dir)
    model.callbacks.register(hook)
    return model


class Krea2Model:
    def __init__(self, model_dir: str, build: Callable = build_model):
        self._model_dir = model_dir
        self._build = build
        self._hook = StepHook()
        self._model = None

    def load(self) -> None:
        self._loaded()

    def _loaded(self):
        if self._model is None:
            missing = missing_files(self._model_dir)
            if missing:
                raise StudioError(
                    f"The Krea 2 weights at {self._model_dir} are incomplete: {', '.join(missing)}. "
                    "Follow the Krea 2 setup in docs/how-to/set-up-models.md."
                )
            self._model = self._build(self._model_dir, self._hook)
        return self._model

    def release(self) -> None:
        self._model = None
        release_mlx_buffers()

    def run(self, job: ImageJob, on_step, should_stop) -> ImageResult:
        kwargs = generate_kwargs(job)
        model = self._loaded()
        steps = kwargs["num_inference_steps"]
        on_step(0, steps)
        try:
            with self._hook.watch(on_step, should_stop, steps):
                image = model.generate_image(**kwargs).image
        finally:
            # mflux keeps every encoded prompt in plain text, keyed by the prompt,
            # for the life of the model. A private run must leave no such copy.
            model.prompt_cache.clear()
            release_mlx_buffers()
        return ImageResult(png=to_png(image), width=image.width, height=image.height, seed=job.seed, steps=steps)
