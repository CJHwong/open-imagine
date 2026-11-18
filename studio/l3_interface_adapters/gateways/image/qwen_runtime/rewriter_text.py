"""The Qwen prompt rewriters' own text: instructions, nudge, and the JSON answer.

This is engine-free on purpose. The MLX rewriter and the CUDA rewriter must ask the same
model the same thing and read its answer the same way, so the cards keep one contract
across the two machines. Only the loader and the sampler differ.
"""

import io
import json
import math
import re
from pathlib import Path

from studio.l1_entities.prompt_rewrite import PromptRewrite

# The cards' own sampling settings, and their token budget. Measured 2026-09-27:
# 317 to 505 tokens out in 22 to 32 s, so the budget is never reached.
MAX_TOKENS = 16384

# What the rewriter sees of each reference. The card spends 11,750 vision tokens on
# a 12 MP picture and 768 on a 1 MP one, and the instruction it writes is one
# sentence either way. Measured 2026-11-19 on the spark: a 12 MP reference costs
# 16 s more than a 1 MP one before the first token is written.
REFERENCE_PIXELS = 1_000_000


def smaller_png(png: bytes, pixels: int = REFERENCE_PIXELS) -> bytes:
    """The reference at about `pixels`, keeping its shape, for the rewriter's copy.

    The image engine keeps the full reference, because fidelity is its job. The
    rewriter reads the picture to know what it is looking at, and a phone photo at
    12 MP spends eleven thousand vision tokens on that. Pixels rather than an edge,
    so a wide picture and a tall one cost the same.
    """
    from PIL import Image

    with Image.open(io.BytesIO(png)) as found:
        width, height = found.size
        if width * height <= pixels:
            return png
        scale = math.sqrt(pixels / (width * height))
        size = (max(1, round(width * scale)), max(1, round(height * scale)))
        written = io.BytesIO()
        found.convert("RGB").resize(size, Image.Resampling.LANCZOS).save(written, format="PNG")
        return written.getvalue()


def system_prompt(repo: str) -> str:
    """The instructions shipped beside the weights. The model depends on them.

    A converted checkpoint keeps them beside its own weights, so the local
    directory answers first and the hub is read only for a repo id.
    """
    path = Path(repo).expanduser()
    if path.is_dir():
        with open(path / "system_prompt.txt", encoding="utf-8") as handle:
            return handle.read().strip()

    from huggingface_hub import hf_hub_download

    with open(hf_hub_download(repo, "system_prompt.txt"), encoding="utf-8") as handle:
        return handle.read().strip()


def as_rewrite(text: str) -> PromptRewrite:
    """The JSON the card says follows the thinking block.

    A model that answers in prose has still written a longer prompt, so the text
    is used as it stands rather than failing the click. Measured 2026-09-27: no
    thinking block is emitted at all, so the whole answer is already the JSON.
    """
    _, marker, tail = text.rpartition("</think>")
    body = (tail if marker else text).strip()
    if body.startswith("```"):
        body = body.split("```")[1].removeprefix("json").strip()
    try:
        answer = json.loads(body)
    except json.JSONDecodeError:
        answer = _repaired(body)
        if answer is None:
            return PromptRewrite(prompt=body)
    return PromptRewrite(
        prompt=answer.get("rewritten_prompt") or body,
        ratio=answer.get("wh_ratio") or None,
        follow_reference=bool(answer.get("ratio_follow")),
    )


_PROMPT_START = re.compile(r'^\{\s*"rewritten_prompt"\s*:\s*"')
_PROMPT_END = re.compile(r'"\s*(?:,\s*"(?:wh_ratio|ratio_follow)"\s*:|\}\s*$)')
_UNESCAPED_QUOTE = re.compile(r'(?<!\\)"')
_RATIO = re.compile(r'"wh_ratio"\s*:\s*"([^"]*)"')
_FOLLOW = re.compile(r'"ratio_follow"\s*:\s*true')


def _repaired(body: str) -> dict | None:
    """The card's answer read again when one quote inside the prompt lost its backslash.

    Seen 2026-10-23: a quoted label closed with a bare quote, json.loads failed, and the
    raw JSON went to the user as the prompt. The keys are fixed, so the prompt is the
    text between its key and the next key or the closing brace.
    """
    start = _PROMPT_START.match(body)
    if start is None:
        return None
    end = _PROMPT_END.search(body, start.end())
    if end is None:
        return None
    raw = _UNESCAPED_QUOTE.sub(r'\\"', body[start.end() : end.start()])
    try:
        prompt = json.loads(f'"{raw}"', strict=False)  # strict=False keeps a raw line break
    except json.JSONDecodeError:
        return None
    ratio = _RATIO.search(body, end.start())
    return {
        "rewritten_prompt": prompt,
        "wh_ratio": ratio.group(1) if ratio else None,
        "ratio_follow": bool(_FOLLOW.search(body, end.start())),
    }


# CJK Unified Ideographs, and the extensions that carry most everyday text.
_CJK = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_CJK_SHARE = 0.5


def in_the_request_language(prompt: str) -> str:
    """The request, asked for in English only when it is not already mostly CJK.

    Measured 2026-09-27, ten seeds each on Qwen-Image-2.1's own fixture:

        request    what is sent            answers in Chinese
        English    the request alone       2 of 10
        English    the request + English   0 of 10
        CJK        the request alone      10 of 10
        English    "same language as ..."  3 of 10, so that wording does not work

    So the model already keeps a CJK request in CJK and needs no help there. An
    English request drifts into Chinese about one time in five, and asking for
    English stops it. This is a branch here rather than a sentence for the model
    to read, because the sentence that asked for the model's own judgment did not
    hold.

    The test is the share of letters that are CJK, not the presence of one, so a
    Latin request with a stray CJK character is still asked for English.
    """
    letters = [character for character in prompt if character.isalpha()]
    cjk = sum(1 for character in letters if _CJK.match(character))
    if letters and cjk / len(letters) > _CJK_SHARE:
        return prompt
    return f"{prompt}\n\nWrite the instruction in English."
