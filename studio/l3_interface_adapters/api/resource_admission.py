"""Estimate a request's memory need before the API reserves model work."""

import base64
import binascii
import io
import json
import sys
from collections.abc import Callable, Mapping

from PIL import Image, UnidentifiedImageError

from studio.l1_entities.errors import InsufficientMemory, InvalidJob, ResourceEstimateUnavailable
from studio.l1_entities.video_estimate import tokens

GIB = 1024**3
OS_RESERVE_GIB = 8.0
# Every estimate below was measured on this macOS machine configuration.
CALIBRATED_PLATFORM = "darwin"
CALIBRATED_TOTAL_MEMORY_GIB = 64.0
# Office M5 Pro, BF16 Qwen Turbo: 53.1 GiB at 1328 square.
# A two-reference edit reached 10% free before cancellation took effect, so edits fail closed.
QWEN_TURBO_WEIGHTS_GIB = 30_000_000_000 / GIB
QWEN_TURBO_GENERATE_PEAK_GIB = 53.1
QWEN_TURBO_CALIBRATED_QUANTIZE = None
# The 384 square, 25 frame LTX run used 25 GiB of system headroom. A 1920 by
# 1088, 97 frame run stayed within 64 GiB. Keep 10 GiB for host overhead there.
LTX_SMALL_CLIP_PEAK_GIB = 25.0
LTX_LARGE_CLIP_CEILING_GIB = 54.0
LTX_SMALL_TOKENS = tokens(384, 384, 25)
LTX_LARGE_TOKENS = tokens(1920, 1088, 97)
# Calibrated only on the office M5 Pro, macOS, 64 GiB, with the pinned 8-bit
# MLX checkpoint. Completed scripts of 44, 483, 979 and 2,008 characters
# showed 41.6 to 44.8 GiB less available memory in coarse pressure samples.
# Keep 2.2 GiB above that largest drop. Re-measure after any setup change.
DRAMA_CALIBRATED_PEAK_GIB = 47.0
DRAMA_TEXT_GIB_PER_CHARACTER = 0.00015
# YuE2's active weight files total 9.7 GB. A short 8-step song used 4.5 GiB
# of system headroom. The weight floor and input terms below are conservative.
YUE2_WEIGHT_FLOOR_GIB = 10.0
YUE2_TRANSCRIPTION_LIMIT_GIB = 16.0
# Office M5 Pro, the int8 Krea 2 Turbo weights, through Krea2Model with no other
# GPU job. The largest drop in free memory from a baseline before the load:
# 29.4 to 33.9 GiB at 512 square, text or one reference; 40.3 to 46.7 GiB from
# 768 square to 1024 square, for text, one reference, Match from a 1600 by 900
# photo, a 4032 by 3024 reference and two images in a row. MLX's own peak was
# 28.0 and 35.2 GiB; the rest is the page cache of the 22 GB of weights. 768
# square already reached 44.8 GiB, so every size above 512 square takes the top.
KREA2_SMALL_PEAK_GIB = 34.0
KREA2_SMALL_PIXELS = 512 * 512
KREA2_PEAK_GIB = 47.0
KREA2_MAX_PIXELS = 1024 * 1024
KREA2_DEFAULT_SIZE = "1024x1024"


class ResourceAdmission:
    def __init__(self, memory_headroom: Callable[[], tuple[int, int]], qwen_turbo_quantize: int | None = None):
        self._memory_headroom = memory_headroom
        self._qwen_turbo_quantize = qwen_turbo_quantize

    def __call__(self, payload: Mapping[str, object]) -> None:
        self.check(payload)

    def check(self, payload: Mapping[str, object]) -> None:
        total_bytes, available_bytes = self._memory_headroom()
        estimate_gib = estimate_peak_gib(payload, total_bytes / GIB, qwen_turbo_quantize=self._qwen_turbo_quantize)
        if estimate_gib is None:
            raise ResourceEstimateUnavailable(
                "No safe memory estimate is available for this model setup. The operation was not started."
            )
        available_gib = available_bytes / GIB
        required_gib = estimate_gib + OS_RESERVE_GIB
        if required_gib > available_gib:
            raise InsufficientMemory(
                f"This request needs about {estimate_gib:.1f} GiB plus an {OS_RESERVE_GIB:.0f} GiB reserve. "
                f"macOS reports about {available_gib:.1f} GiB free. Reduce the request or free memory."
            )


def estimate_peak_gib(
    payload: Mapping[str, object], total_memory_gib: float, *, qwen_turbo_quantize: int | None = None
) -> float | None:
    if sys.platform != CALIBRATED_PLATFORM or total_memory_gib != CALIBRATED_TOTAL_MEMORY_GIB:
        return None
    items = payload.get("items")
    if not isinstance(items, list):
        return _estimate_one(payload, qwen_turbo_quantize)
    estimates = []
    shared = {key: value for key, value in payload.items() if key != "items"}
    for item in items:
        if not isinstance(item, Mapping):
            return None
        estimate = _estimate_one({**shared, **item}, qwen_turbo_quantize)
        if estimate is None:
            return None
        estimates.append(estimate)
    if not estimates:
        return None
    # Batches retain finished media while the next item runs.
    return max(estimates) + max(0, len(estimates) - 1) * 0.125


def _estimate_one(payload: Mapping[str, object], qwen_turbo_quantize: int | None) -> float | None:
    kind = payload.get("kind")
    backend = payload.get("backend")
    mode = payload.get("mode") or "generate"
    if kind == "image" and backend == "qwen21_turbo":
        return _qwen_turbo_peak(payload, str(mode), qwen_turbo_quantize)
    if kind == "image" and backend == "krea2":
        return _krea2_peak(payload, str(mode))
    if kind == "video" and backend == "ltx25_mlx":
        return _ltx25_peak(payload, str(mode))
    if kind == "voice" and backend == "drama3":
        return _drama_peak(payload, str(mode))
    if kind == "music" and backend == "yue2":
        return _yue2_peak(payload, str(mode))
    return None


def _qwen_turbo_peak(payload: Mapping[str, object], mode: str, quantize: int | None) -> float | None:
    if quantize != QWEN_TURBO_CALIBRATED_QUANTIZE:
        return None
    if _has_loras(payload.get("loras")):
        return None
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None:
        return None
    if mode != "generate":
        return None
    if references or payload.get("mask") or payload.get("each_reference"):
        return None
    width, height = _image_size(payload.get("size", "512x512"))
    if width is None or height is None:
        return None
    megapixels = width * height / 1_000_000
    if megapixels > 1328 * 1328 / 1_000_000:
        return None
    if megapixels >= 1.0:
        return QWEN_TURBO_GENERATE_PEAK_GIB
    workspace = QWEN_TURBO_GENERATE_PEAK_GIB - QWEN_TURBO_WEIGHTS_GIB
    return QWEN_TURBO_WEIGHTS_GIB + workspace * megapixels / (1328 * 1328 / 1_000_000)


def _krea2_peak(payload: Mapping[str, object], mode: str) -> float | None:
    """Text to image or one starting image, up to the 1 MP the measurement reached."""
    if mode != "generate" or _has_loras(payload.get("loras")):
        return None
    if payload.get("mask") or payload.get("each_reference"):
        return None
    references = _reference_sizes(payload.get("references"), payload.get("reference_sizes"))
    if references is None or len(references) > 1:
        return None
    # Match sizes the output from the reference at about 1 MP; _image_size reads it as 1024 square.
    width, height = _image_size(payload.get("size", KREA2_DEFAULT_SIZE))
    if width is None or height is None or width * height > KREA2_MAX_PIXELS:
        return None
    return KREA2_SMALL_PEAK_GIB if width * height <= KREA2_SMALL_PIXELS else KREA2_PEAK_GIB


def _ltx25_peak(payload: Mapping[str, object], mode: str) -> float | None:
    if mode != "generate":
        return None
    if payload.get("audio") or payload.get("has_audio") or payload.get("loras") or payload.get("reference_count", 0):
        return None
    if payload.get("references") or payload.get("fast_mode"):
        return None
    if payload.get("enhance", True) is not True:
        return None
    width = _positive_integer(payload.get("width", 384))
    height = _positive_integer(payload.get("height", 384))
    frames = _positive_integer(payload.get("num_frames", 25))
    if width is None or height is None or frames is None:
        return None
    if max(width, height) > 1920 or width * height > 1920 * 1088 or frames > 97:
        return None
    token_count = tokens(width, height, frames)
    if token_count > LTX_LARGE_TOKENS:
        return None
    fraction = max(0.0, token_count - LTX_SMALL_TOKENS) / (LTX_LARGE_TOKENS - LTX_SMALL_TOKENS)
    return LTX_SMALL_CLIP_PEAK_GIB + (LTX_LARGE_CLIP_CEILING_GIB - LTX_SMALL_CLIP_PEAK_GIB) * fraction


def _drama_peak(payload: Mapping[str, object], mode: str) -> float | None:
    if mode != "generate" or payload.get("reference"):
        return None
    text = payload.get("text", payload.get("prompt", ""))
    if not isinstance(text, str):
        return None
    return DRAMA_CALIBRATED_PEAK_GIB + len(text) * DRAMA_TEXT_GIB_PER_CHARACTER


def _yue2_peak(payload: Mapping[str, object], mode: str) -> float | None:
    if mode == "transcribe":
        return YUE2_TRANSCRIPTION_LIMIT_GIB
    if mode not in ("generate", "plan", "cover"):
        return None
    lyrics = payload.get("lyrics", "")
    style = payload.get("style", "")
    score = payload.get("abc", "")
    if not isinstance(lyrics, str) or not isinstance(style, str) or not isinstance(score, str):
        return None
    if len(lyrics) > 20_000 or len(style) > 4_000 or len(score) > 100_000:
        return None
    sampling = payload.get("sampling") or {}
    if not isinstance(sampling, Mapping):
        return None
    default_tokens = 4096 if mode == "plan" else 9000
    max_tokens = sampling.get("max_tokens", default_tokens)
    if type(max_tokens) is not int or not 1 <= max_tokens <= 16_000:
        return None
    generation_peak = (
        YUE2_WEIGHT_FLOOR_GIB + len(lyrics) * 0.00025 + len(style) * 0.0001 + len(score) * 0.00005 + max_tokens * 0.0001
    )
    if payload.get("instrumental") is True:
        generation_peak += 2.0
    if mode == "cover":
        return max(YUE2_TRANSCRIPTION_LIMIT_GIB, generation_peak)
    return generation_peak


def _image_size(value: object) -> tuple[int | None, int | None]:
    if not isinstance(value, str):
        return None, None
    if value == "match":
        return 1024, 1024
    width, separator, height = value.partition("x")
    if not separator or not width.isdigit() or not height.isdigit():
        return None, None
    return int(width), int(height)


def _has_loras(raw: object) -> bool:
    if raw in (None, "", [], ()):
        return False
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return True
    return bool(raw)


def _reference_sizes(raw_references: object, raw_sizes: object) -> tuple[tuple[int, int], ...] | None:
    if raw_references in (None, ""):
        return None if raw_sizes is not None else ()
    if isinstance(raw_references, str):
        try:
            raw_references = json.loads(raw_references)
        except json.JSONDecodeError:
            return None
    if not isinstance(raw_references, list):
        return None
    sizes = []
    for reference in raw_references:
        encoded = reference
        if isinstance(reference, Mapping):
            encoded = reference.get("png_base64") or reference.get("data")
        if not isinstance(encoded, str):
            return None
        if encoded.startswith("data:") and "base64," in encoded:
            encoded = encoded.split("base64,", 1)[1]
        try:
            raw = base64.b64decode(encoded, validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                sizes.append(image.size)
        except (binascii.Error, UnidentifiedImageError, OSError, ValueError):
            raise InvalidJob("A reference image is not readable.") from None
    return tuple(sizes)


def _positive_integer(value: object) -> int | None:
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and value.isdigit() and int(value) > 0:
        return int(value)
    return None
