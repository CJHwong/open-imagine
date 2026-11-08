import base64
import io
import json

import pytest
from PIL import Image

from studio.l1_entities.errors import InsufficientMemory, InvalidJob, ResourceEstimateUnavailable
from studio.l3_interface_adapters.api import resource_admission
from studio.l3_interface_adapters.api.resource_admission import GIB, ResourceAdmission, estimate_peak_gib


@pytest.fixture(autouse=True)
def calibrated_mac_estimate_platform(monkeypatch):
    monkeypatch.setattr(resource_admission.sys, "platform", "darwin")


def encoded_png(width, height):
    image = Image.new("RGB", (width, height), (90, 120, 150))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    return base64.b64encode(encoded.getvalue()).decode("ascii")


def estimate(kind, backend, mode="generate", **options):
    return estimate_peak_gib({"kind": kind, "backend": backend, "mode": mode, **options}, 64)


def test_qwen_generation_uses_the_measured_high_resolution_peak_from_one_megapixel():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "1024x1024",
        },
        64,
    )

    assert estimate == 53.1


def test_qwen_estimate_fails_closed_for_an_unmeasured_quantization():
    payload = {"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"}

    assert estimate_peak_gib(payload, 64, qwen_turbo_quantize=8) is None


def test_admission_fails_closed_when_qwen_quantization_is_not_calibrated():
    admission = ResourceAdmission(lambda: (64 * GIB, 64 * GIB), qwen_turbo_quantize=8)

    with pytest.raises(ResourceEstimateUnavailable):
        admission({"kind": "image", "backend": "qwen21_turbo", "size": "1024x1024"})


def test_yue2_uses_the_engine_default_token_budget_for_each_mode():
    plan = estimate("music", "yue2", mode="plan")
    generate = estimate("music", "yue2", mode="generate")

    assert plan == pytest.approx(10.4096)
    assert generate == pytest.approx(10.9)


def test_qwen_generation_blocks_when_free_memory_cannot_hold_the_peak_and_reserve():
    admission = ResourceAdmission(lambda: (64 * GIB, 59 * GIB))

    with pytest.raises(InsufficientMemory):
        admission(
            {
                "kind": "image",
                "backend": "qwen21_turbo",
                "mode": "generate",
                "size": "1024x1024",
            }
        )


def test_qwen_generation_fails_closed_for_an_unmeasured_lora():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "512x512",
            "loras": [{"id": "extra-weights"}],
        },
        64,
    )

    assert estimate is None


def test_qwen_edit_uses_the_image_size_instead_of_a_client_size_hint():
    image = Image.new("RGB", (1024, 1024), (90, 120, 150))
    encoded = io.BytesIO()
    image.save(encoded, format="PNG")
    reference = base64.b64encode(encoded.getvalue()).decode("ascii")

    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "edit",
            "resolution": "match",
            "references": [{"png_base64": reference}],
            "reference_sizes": [[512, 512]],
        },
        64,
    )

    assert estimate is None


def test_qwen_edit_does_not_estimate_from_sizes_without_reference_images():
    estimate = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "edit",
            "resolution": "match",
            "reference_sizes": [[512, 512]],
        },
        64,
    )

    assert estimate is None


def test_supported_default_workflows_keep_their_declared_bounds():
    image = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "mode": "generate",
            "size": "512x512",
        },
        64,
    )
    video = estimate_peak_gib(
        {
            "kind": "video",
            "backend": "ltx25_mlx",
            "mode": "generate",
            "width": 384,
            "height": 384,
            "num_frames": 25,
        },
        64,
    )

    assert image == pytest.approx(31.7, abs=0.1)
    assert video == 25.0


def test_admission_accepts_a_request_that_fits_with_the_reserve():
    admission = ResourceAdmission(lambda: (64 * GIB, 50 * GIB))

    assert admission({"kind": "image", "backend": "qwen21_turbo", "size": "512x512"}) is None


def test_admission_rejects_a_request_without_a_safe_model_estimate():
    admission = ResourceAdmission(lambda: (64 * GIB, 64 * GIB))

    with pytest.raises(ResourceEstimateUnavailable):
        admission({"kind": "image", "backend": "optional-model"})


def test_batch_estimate_uses_the_largest_item_and_output_reserve():
    result = estimate_peak_gib(
        {
            "kind": "image",
            "backend": "qwen21_turbo",
            "items": [{"size": "512x512"}, {"size": "768x768"}],
        },
        64,
    )

    assert result == pytest.approx(36.48, abs=0.01)


@pytest.mark.parametrize("items", ([], ["bad"], [{"size": "not-a-size"}]))
def test_batch_estimate_fails_closed_for_empty_or_unmeasured_items(items):
    assert estimate_peak_gib({"kind": "image", "backend": "qwen21_turbo", "items": items}, 64) is None


@pytest.mark.parametrize(
    ("kind", "backend"),
    (
        ("image", "other-image"),
        ("video", "other-video"),
        ("voice", "other-voice"),
        ("music", "other-music"),
        ("other", "qwen21_turbo"),
    ),
)
def test_unmeasured_backends_and_kinds_fail_closed(kind, backend):
    assert estimate(kind, backend) is None


@pytest.mark.parametrize("loras", (None, "", "[]", []))
def test_qwen_generation_accepts_empty_lora_selections(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is not None


@pytest.mark.parametrize("loras", ([{"id": "extra"}], "[{}]", "not-json"))
def test_qwen_generation_fails_closed_for_nonempty_or_invalid_loras(loras):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=loras) is None


@pytest.mark.parametrize("flag", ("mask", "each_reference"))
def test_qwen_generation_fails_closed_for_reference_modes(flag):
    assert estimate("image", "qwen21_turbo", size="512x512", **{flag: True}) is None


@pytest.mark.parametrize("size", (None, 512, "bad-size", "2048x2048"))
def test_qwen_generation_fails_closed_for_invalid_or_oversized_shapes(size):
    assert estimate("image", "qwen21_turbo", size=size) is None


def test_qwen_generation_uses_the_pixel_area_below_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="1024x576") == pytest.approx(36.4, abs=0.1)


def test_qwen_does_not_estimate_unsupported_modes():
    assert estimate("image", "qwen21_turbo", "plan", size="512x512") is None


def test_qwen_generate_fails_closed_when_a_reference_is_present():
    reference = {"png_base64": encoded_png(1, 1)}
    assert estimate("image", "qwen21_turbo", references=[reference]) is None


def test_qwen_edit_requires_one_or_two_readable_references():
    assert estimate("image", "qwen21_turbo", "edit", references=[]) is None
    reference = encoded_png(512, 512)
    assert estimate("image", "qwen21_turbo", "edit", references=[reference] * 3) is None


@pytest.mark.parametrize("flag", ("mask", "each_reference"))
def test_qwen_edit_fails_closed_for_mask_or_each_reference(flag):
    reference = {"png_base64": encoded_png(512, 512)}
    assert estimate("image", "qwen21_turbo", "edit", references=[reference], **{flag: True}) is None


@pytest.mark.parametrize("resolution", ("768", 768, "bad"))
def test_qwen_edit_fails_closed_for_unmeasured_resolutions(resolution):
    reference = {"png_base64": encoded_png(512, 512)}
    assert estimate("image", "qwen21_turbo", "edit", references=[reference], resolution=resolution) is None


def test_qwen_edits_fail_closed_until_a_safe_peak_is_measured():
    reference = {"png_base64": encoded_png(512, 512)}

    one = estimate("image", "qwen21_turbo", "edit", references=[reference], resolution="match")
    two = estimate("image", "qwen21_turbo", "edit", references=[reference, reference], resolution=512)

    assert one is None
    assert two is None
    with pytest.raises(ResourceEstimateUnavailable):
        ResourceAdmission(lambda: (64 * GIB, 64 * GIB))(
            {
                "kind": "image",
                "backend": "qwen21_turbo",
                "mode": "edit",
                "resolution": "match",
                "references": [reference, reference],
            }
        )


@pytest.mark.parametrize(
    "changes",
    (
        {"mode": "edit"},
        {"audio": "reference"},
        {"has_audio": True},
        {"loras": [{"id": "lora"}]},
        {"reference_count": 1},
        {"references": [{}]},
        {"fast_mode": True},
        {"enhance": False},
        {"width": "bad"},
        {"height": 0},
        {"num_frames": 0},
        {"width": 1921},
        {"height": 1921},
        {"width": 1920, "height": 1089},
        {"num_frames": 98},
    ),
)
def test_ltx_fails_closed_for_unmeasured_modes_and_inputs(changes):
    request = {"width": 384, "height": 384, "num_frames": 25, **changes}
    assert estimate("video", "ltx25_mlx", **request) is None


def test_ltx_estimates_its_largest_declared_clip():
    assert estimate("video", "ltx25_mlx", width=1920, height=1088, num_frames=97) == 54.0


def test_ltx_fails_closed_when_token_shape_exceeds_the_measured_limit(monkeypatch):
    monkeypatch.setattr(resource_admission, "tokens", lambda *args: resource_admission.LTX_LARGE_TOKENS + 1)

    assert estimate("video", "ltx25_mlx", width=384, height=384, num_frames=25) is None


def test_drama_uses_the_measured_mac_peak_and_prompt_length(monkeypatch):
    monkeypatch.setattr(resource_admission.sys, "platform", "darwin")

    assert estimate("voice", "drama3", text="") == pytest.approx(47.0)
    assert estimate("voice", "drama3", prompt="word") > estimate("voice", "drama3", text="")


@pytest.mark.parametrize(
    "payload",
    (
        {"kind": "image", "backend": "qwen21_turbo", "size": "512x512"},
        {"kind": "video", "backend": "ltx25_mlx", "width": 384, "height": 384, "num_frames": 25},
        {"kind": "voice", "backend": "drama3", "text": "hello"},
        {"kind": "music", "backend": "yue2", "style": "piano"},
    ),
)
@pytest.mark.parametrize(
    ("platform", "total_memory_gib"),
    (("linux", 64), ("darwin", 128), ("darwin", 32)),
)
def test_all_mode_estimates_fail_closed_outside_the_calibrated_mac_setup(
    monkeypatch, payload, platform, total_memory_gib
):
    monkeypatch.setattr(resource_admission.sys, "platform", platform)

    result = estimate_peak_gib(payload, total_memory_gib)

    assert result is None


@pytest.mark.parametrize("payload", ({"mode": "clone"}, {"reference": {"wav_base64": "audio"}}, {"text": 7}))
def test_drama_fails_closed_for_references_modes_or_bad_text(payload):
    assert estimate("voice", "drama3", **payload) is None


def test_yue_transcription_uses_its_fixed_limit():
    assert estimate("music", "yue2", "transcribe") == 16.0


@pytest.mark.parametrize(
    "payload",
    (
        {"mode": "clone"},
        {"lyrics": 7},
        {"style": 7},
        {"abc": 7},
        {"lyrics": "x" * 20_001},
        {"style": "x" * 4_001},
        {"abc": "x" * 100_001},
        {"sampling": "bad"},
        {"sampling": {"max_tokens": True}},
        {"sampling": {"max_tokens": 0}},
        {"sampling": {"max_tokens": 16_001}},
    ),
)
def test_yue_fails_closed_for_unknown_or_oversized_inputs(payload):
    assert estimate("music", "yue2", **payload) is None


def test_yue_counts_text_sampling_instrumental_and_cover_work():
    regular = estimate("music", "yue2", "generate", style="piano", sampling={"max_tokens": 100})
    instrumental = estimate("music", "yue2", "generate", style="piano", instrumental=True, sampling={"max_tokens": 100})
    cover = estimate("music", "yue2", "cover", style="piano", sampling={"max_tokens": 100})
    long_cover = estimate(
        "music", "yue2", "cover", lyrics="x" * 20_000, instrumental=True, sampling={"max_tokens": 16_000}
    )

    assert regular is not None and instrumental == pytest.approx(regular + 2.0)
    assert cover == 16.0
    assert long_cover is not None and long_cover > 16.0


@pytest.mark.parametrize("value", (None, 7, "bad", "12x", "x12"))
def test_bad_image_sizes_fail_closed(value):
    assert estimate("image", "qwen21_turbo", size=value) is None


def test_match_image_size_uses_one_megapixel():
    assert estimate("image", "qwen21_turbo", size="match") == pytest.approx(53.1)


@pytest.mark.parametrize("raw", (None, "", [], (), "[]"))
def test_empty_lora_values_are_not_extra_weights(raw):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=raw) is not None


@pytest.mark.parametrize("raw", ("not-json", "[{}]", [{"id": "extra"}]))
def test_nonempty_lora_values_are_unmeasured(raw):
    assert estimate("image", "qwen21_turbo", size="512x512", loras=raw) is None


@pytest.mark.parametrize("reference", (7, {}, {"png_base64": None}))
def test_reference_sizes_reject_invalid_entries(reference):
    assert estimate("image", "qwen21_turbo", "edit", references=[reference]) is None


@pytest.mark.parametrize("encoded", ("%%%", base64.b64encode(b"not a png").decode("ascii")))
def test_reference_sizes_raise_for_unreadable_images(encoded):
    with pytest.raises(InvalidJob, match="not readable"):
        estimate("image", "qwen21_turbo", "edit", references=[{"png_base64": encoded}])


def test_reference_sizes_read_json_and_data_uri_inputs():
    encoded = encoded_png(512, 512)
    assert (
        estimate(
            "image",
            "qwen21_turbo",
            "edit",
            references=json_list_reference(encoded),
            resolution="match",
        )
        is None
    )
    assert (
        estimate(
            "image",
            "qwen21_turbo",
            "edit",
            references=[{"data": "data:image/png;base64," + encoded}],
            resolution="match",
        )
        is None
    )


def json_list_reference(encoded):
    return json.dumps([{"png_base64": encoded}])


def test_reference_sizes_reject_bad_json_and_non_list_shapes():
    assert estimate("image", "qwen21_turbo", "edit", references="not-json") is None
    assert estimate("image", "qwen21_turbo", "edit", references={"png_base64": encoded_png(512, 512)}) is None


@pytest.mark.parametrize("value", (1, "12"))
def test_positive_integer_accepts_positive_integer_values(value):
    assert estimate("video", "ltx25_mlx", width=value, height=384, num_frames=25) == 25.0


@pytest.mark.parametrize("value", (True, 0, -1, 1.5, "0", "bad"))
def test_positive_integer_rejects_bad_dimensions(value):
    assert estimate("video", "ltx25_mlx", width=value, height=384, num_frames=25) is None


@pytest.mark.parametrize(
    ("options", "peak"),
    (
        ({}, 47.0),  # the form's own default, 1024 square
        ({"size": "512x512"}, 34.0),
        ({"size": "768x432"}, 47.0),  # above 512 square, where 768 square already reached 44.8
        ({"size": "1024x1024"}, 47.0),
        ({"size": "1152x864"}, 47.0),
        ({"size": "match", "references": [encoded_png(1600, 900)]}, 47.0),
        ({"size": "512x512", "references": [encoded_png(4032, 3024)]}, 34.0),
        ({"loras": "[]"}, 47.0),
    ),
)
def test_krea2_uses_its_measured_peak_for_text_and_one_reference(options, peak):
    assert estimate("image", "krea2", **options) == peak


@pytest.mark.parametrize(
    ("mode", "options"),
    (
        ("edit", {}),
        ("generate", {"size": "1280x1024"}),  # above the 1 MP the measurement reached
        ("generate", {"size": "not-a-size"}),
        ("generate", {"loras": [{"id": "warm"}]}),
        ("generate", {"mask": True}),
        ("generate", {"each_reference": True}),
        ("generate", {"reference_sizes": [[512, 512], [512, 512]]}),
        ("generate", {"reference_sizes": [[512, 512]]}),  # sizes with no references
    ),
)
def test_krea2_fails_closed_outside_what_was_measured(mode, options):
    assert estimate("image", "krea2", mode, **options) is None


def test_krea2_needs_its_peak_and_the_reserve_free():
    fits = ResourceAdmission(lambda: (64 * GIB, 55 * GIB))
    short = ResourceAdmission(lambda: (64 * GIB, 54 * GIB))

    assert fits({"kind": "image", "backend": "krea2", "size": "1024x1024"}) is None
    with pytest.raises(InsufficientMemory, match=r"about 47\.0 GiB"):
        short({"kind": "image", "backend": "krea2", "size": "1024x1024"})
