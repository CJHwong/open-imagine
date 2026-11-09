"""Read image geometry and options for calibrated memory estimators."""

import base64
import binascii
import io
import json
from collections.abc import Mapping

from PIL import Image, UnidentifiedImageError

from studio.l1_entities.errors import InvalidJob


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
