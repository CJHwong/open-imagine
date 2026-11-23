"""Decode one imported still in memory for browsers without a HEIF decoder."""

import base64
import io
import warnings

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import is_supported, open_heif

from studio.l1_entities.errors import InvalidJob, UnreadableImage

MAX_IMAGE_IMPORT_BYTES = 64 * 1024 * 1024
MAX_IMAGE_IMPORT_PIXELS = 64_000_000
# The page draws a JPEG again at this quality, so the two encodes agree.
BROWSER_JPEG_QUALITY = 92


class ImageImportController:
    def normalize(self, contents: bytes, *, convert_profile: bool = True) -> bytes:
        """Lossless PNG bytes, because an engine reads these as its reference."""
        return self._encoded(contents, convert_profile, browser=False)[0]

    def for_browser(self, contents: bytes) -> tuple[bytes, str]:
        """Bytes a browser can show, and their media type.

        A phone photo as PNG measured 13.4 MB for a 9.2 MB HEIC, and the phone downloads it
        and decodes it before the person sees anything. A picture with no transparency
        goes back as JPEG; one with transparency stays PNG, because a JPEG has no alpha.
        """
        contents, format = self._encoded(contents, True, browser=True)
        return contents, f"image/{format.lower()}"

    def _encoded(self, contents: bytes, convert_profile: bool, *, browser: bool) -> tuple[bytes, str]:
        if len(contents) > MAX_IMAGE_IMPORT_BYTES:
            raise InvalidJob("Choose an image smaller than 64 MB.")
        try:
            with self._open(contents) as source:
                self._check_pixels(source.size)
                image = self._pixels(source, convert_profile)
            format = "JPEG" if browser and image.mode == "RGB" else "PNG"
            output = io.BytesIO()
            image.save(output, format=format, quality=BROWSER_JPEG_QUALITY)
        except InvalidJob:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, ImageCms.PyCMSError):
            raise UnreadableImage("Could not read that image.") from None
        return output.getvalue(), format

    @staticmethod
    def _pixels(source: Image.Image, convert_profile: bool) -> Image.Image:
        # Three full-size pictures must not be alive at once: a 64 megapixel source is
        # 192 MB in RGB and 256 MB in RGBA. Convert first, close the source (the caller's
        # `with` closes it again, which is nothing), and transpose the converted image,
        # which carries the EXIF the rotation reads. The peak is then two pictures, not
        # three, and the second one is the one that leaves here.
        profile = source.info.get("icc_profile")
        converted = source.convert("RGBA" if source.has_transparency_data else "RGB")
        source.close()
        # `exif_transpose` returns a copy, the documentation says so, so the converted
        # picture can go as soon as the upright one exists.
        image = ImageOps.exif_transpose(converted)
        converted.close()
        if profile and convert_profile:
            ImageCms.profileToProfile(
                image,
                ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                ImageCms.createProfile("sRGB"),
                outputMode=image.mode,
                inPlace=True,
            )
        image.info.clear()
        return image

    def _open(self, contents: bytes) -> Image.Image:
        stream = io.BytesIO(contents)
        if not is_supported(stream):
            # The product checks dimensions before load and uses a lower pixel limit.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", Image.DecompressionBombWarning)
                return Image.open(stream)
        heif = open_heif(stream, convert_hdr_to_8bit=True)
        self._check_pixels(heif.size)
        return heif.to_pillow()

    @staticmethod
    def _check_pixels(size: tuple[int, int]) -> None:
        if size[0] * size[1] > MAX_IMAGE_IMPORT_PIXELS:
            raise InvalidJob("Choose an image with at most 64 megapixels.")


def decode_image_base64(encoded: str, *, validate: bool = False) -> bytes:
    if not isinstance(encoded, str):
        raise ValueError("The reference image must use base64 text.")
    if len(encoded) > 4 * ((MAX_IMAGE_IMPORT_BYTES + 2) // 3):
        raise InvalidJob("Choose an image smaller than 64 MB.")
    return base64.b64decode(encoded, validate=validate)
