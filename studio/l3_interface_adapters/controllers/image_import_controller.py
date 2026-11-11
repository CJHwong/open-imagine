"""Decode one imported still in memory for browsers without a HEIF decoder."""

import io

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError
from pillow_heif import is_supported, open_heif

from studio.l1_entities.errors import InvalidJob, UnreadableImage

MAX_IMAGE_IMPORT_BYTES = 64 * 1024 * 1024
MAX_IMAGE_IMPORT_PIXELS = 64_000_000


class ImageImportController:
    def normalize(self, contents: bytes) -> bytes:
        if len(contents) > MAX_IMAGE_IMPORT_BYTES:
            raise InvalidJob("Choose an image smaller than 64 MB.")
        try:
            with self._open(contents) as source:
                self._check_pixels(source.size)
                upright = ImageOps.exif_transpose(source)
                image = upright.convert("RGBA" if upright.has_transparency_data else "RGB")
                profile = upright.info.get("icc_profile")
                if profile:
                    ImageCms.profileToProfile(
                        image,
                        ImageCms.ImageCmsProfile(io.BytesIO(profile)),
                        ImageCms.createProfile("sRGB"),
                        outputMode=image.mode,
                        inPlace=True,
                    )
                image.info.clear()
                output = io.BytesIO()
                image.save(output, format="PNG")
        except InvalidJob:
            raise
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, ImageCms.PyCMSError):
            raise UnreadableImage("Could not read that image.") from None
        return output.getvalue()

    def _open(self, contents: bytes) -> Image.Image:
        stream = io.BytesIO(contents)
        if not is_supported(stream):
            return Image.open(stream)
        heif = open_heif(stream, convert_hdr_to_8bit=True)
        self._check_pixels(heif.size)
        return heif.to_pillow()

    @staticmethod
    def _check_pixels(size: tuple[int, int]) -> None:
        if size[0] * size[1] > MAX_IMAGE_IMPORT_PIXELS:
            raise InvalidJob("Choose an image with at most 64 megapixels.")
