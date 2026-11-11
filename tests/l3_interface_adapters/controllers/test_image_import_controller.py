"""Imported images become browser-readable PNG bytes without a file copy."""

import io

import pytest
from PIL import Image, ImageCms
from pillow_heif import from_pillow

from studio.l1_entities.errors import InvalidJob, UnreadableImage
from studio.l3_interface_adapters.controllers import image_import_controller
from studio.l3_interface_adapters.controllers.image_import_controller import ImageImportController


def encoded_image(format="PNG", mode="RGB", size=(64, 48), **save_options):
    output = io.BytesIO()
    colour = (210, 30, 20, 128) if mode == "RGBA" else (210, 30, 20)
    image = Image.new(mode, size, colour)
    if format == "HEIF":
        from_pillow(image).save(output, **save_options)
    else:
        image.save(output, format=format, **save_options)
    return output.getvalue()


@pytest.mark.parametrize("format", ["PNG", "JPEG", "WEBP", "HEIF"])
def test_import_decodes_real_image_bytes_to_png(format):
    result = ImageImportController().normalize(encoded_image(format))

    with Image.open(io.BytesIO(result)) as image:
        assert image.format == "PNG"
        assert image.size == (64, 48)
        pixel = image.getpixel((32, 24))
        assert isinstance(pixel, tuple)
        red, green, blue = pixel
        assert red > green + 100 and red > blue + 100
        assert image.info == {}


@pytest.mark.parametrize("format", ["PNG", "HEIF"])
def test_import_keeps_transparency(format):
    result = ImageImportController().normalize(encoded_image(format, mode="RGBA"))

    with Image.open(io.BytesIO(result)) as image:
        assert image.mode == "RGBA"
        pixel = image.getpixel((32, 24))
        assert isinstance(pixel, tuple)
        assert pixel[3] == 128


def test_import_applies_exif_rotation_and_removes_metadata():
    exif = Image.Exif()
    exif[274] = 6
    exif[270] = "Synthetic metadata to remove"
    result = ImageImportController().normalize(encoded_image("JPEG", exif=exif))

    with Image.open(io.BytesIO(result)) as image:
        assert image.size == (48, 64)
        assert image.info == {}


def test_import_converts_grayscale_to_rgb():
    contents = io.BytesIO()
    Image.new("L", (8, 6), 100).save(contents, format="PNG")

    result = ImageImportController().normalize(contents.getvalue())

    with Image.open(io.BytesIO(result)) as image:
        assert image.mode == "RGB"
        assert image.getpixel((4, 3)) == (100, 100, 100)


def test_import_converts_icc_colour_to_srgb_before_removing_metadata():
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    result = ImageImportController().normalize(encoded_image(icc_profile=profile))

    with Image.open(io.BytesIO(result)) as image:
        assert image.getpixel((32, 24)) == (210, 30, 20)
        assert image.info == {}


def test_import_rejects_an_unreadable_colour_profile():
    with pytest.raises(UnreadableImage, match="Could not read that image"):
        ImageImportController().normalize(encoded_image(icc_profile=b"invalid profile"))


def test_heic_import_does_not_register_a_global_pillow_decoder():
    Image.init()
    before = dict(Image.OPEN)

    ImageImportController().normalize(encoded_image("HEIF"))

    assert before == Image.OPEN


@pytest.mark.parametrize("contents", [b"", b"not an image", b"\x00\x00\x00\x18ftypheic"])
def test_import_rejects_unreadable_images_without_echoing_contents(contents):
    with pytest.raises(UnreadableImage, match="Could not read that image"):
        ImageImportController().normalize(contents)


def test_import_bounds_encoded_bytes_before_decoding(monkeypatch):
    monkeypatch.setattr(image_import_controller, "MAX_IMAGE_IMPORT_BYTES", 3)

    with pytest.raises(InvalidJob, match="64 MB"):
        ImageImportController().normalize(b"four")


def test_import_bounds_pixels_before_loading(monkeypatch):
    monkeypatch.setattr(image_import_controller, "MAX_IMAGE_IMPORT_PIXELS", 100)

    with pytest.raises(InvalidJob, match="64 megapixels"):
        ImageImportController().normalize(encoded_image(size=(11, 10)))


def test_heic_import_bounds_pixels_before_decoding(monkeypatch):
    monkeypatch.setattr(image_import_controller, "MAX_IMAGE_IMPORT_PIXELS", 100)

    with pytest.raises(InvalidJob, match="64 megapixels"):
        ImageImportController().normalize(encoded_image("HEIF", size=(11, 10)))
