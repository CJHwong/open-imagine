"""The H3-Image prompt enhancer's own text: templates, messages and the JSON answer.

Engine-free on purpose. The MLX child and the CUDA child ask the same model the same thing
and read the same fields, so the enhancer keeps one contract across the two machines. Only
the loader and the sampler differ.

The two task templates ship beside the weights, under `prompt/t2i` and `prompt/edit`, and
the model depends on their wording.
"""

import contextlib
import json
import math
from io import BytesIO
from pathlib import Path

from PIL import Image

CAPTION_KEY = "expanded_caption"


def json_objects(text: str):
    """Every balanced {...} in the reply, in order."""
    depth, start = 0, None
    for index, character in enumerate(text):
        if character == "{":
            if depth == 0:
                start = index
            depth += 1
        elif character == "}" and depth:
            depth -= 1
            if depth == 0 and start is not None:
                yield text[start : index + 1]
                start = None


def last_json_object(text: str) -> dict:
    """The last JSON object in the model's reply, after any reasoning in front of it."""
    for candidate in reversed(list(json_objects(text))):
        with contextlib.suppress(json.JSONDecodeError):
            return json.loads(candidate)
    raise ValueError("The prompt enhancer returned no JSON object.")


def picture_ratio(raw: bytes) -> str:
    """The lowest whole-number ratio of the picture bytes."""
    with Image.open(BytesIO(raw)) as image:
        width, height = image.size
    divisor = math.gcd(width, height)
    return f"{width // divisor}:{height // divisor}"


def image_messages(prompt_dir: Path, prompt: str) -> list[dict]:
    """The generate request: the card's own system and task text, with the prompt filled in."""
    system = (prompt_dir / "t2i/system_prompt.txt").read_text(encoding="utf-8").rstrip("\n")
    task = (prompt_dir / "t2i/task_prompt.txt").read_text(encoding="utf-8").rstrip("\n").format(prompt)
    return [{"role": "system", "content": system}, {"role": "user", "content": task}]


def edit_messages(prompt_dir: Path, prompt: str, ratios: list[str], ratio: str) -> list[dict]:
    """The edit request: the task text, then one labelled line per picture and the ask."""
    task = (prompt_dir / "edit/task_prompt.txt").read_text(encoding="utf-8").strip()
    lines = [f"Reference Media: <Picture {index}>, aspect_ratio {shape}" for index, shape in enumerate(ratios, start=1)]
    lines.append(f"User Editing Instruction (JSON string): {json.dumps(prompt)}")
    lines.append(f"User Aspect Ratio Selection: {ratio}")
    return [{"role": "user", "content": task + "\n\n" + "\n".join(lines)}]


def caption_reply(text: str, ratio_key: str, fallback_ratio: str | None = None) -> dict:
    """The caption and the ratio the enhancer chose, or the one the request asked for."""
    answer = last_json_object(text)
    caption = str(answer.get(CAPTION_KEY) or "").strip()
    ratio = str(answer.get(ratio_key) or "").strip() or fallback_ratio
    if not caption:
        raise ValueError("The prompt enhancer wrote an empty caption.")
    return {"prompt": caption, "ratio": ratio}
