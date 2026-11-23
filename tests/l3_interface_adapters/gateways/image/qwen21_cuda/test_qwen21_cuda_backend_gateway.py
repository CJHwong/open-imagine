import base64
from unittest.mock import Mock

from studio.l1_entities.image_job import ImageJob, ReferenceImage
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.qwen21_cuda_backend_gateway import (
    Qwen21CudaBackendGateway,
    edit_payload,
    generate_payload,
)


def job(**options):
    merged = {"size": "768x512", "steps": 6, "guidance": 2.5, "negative": "blur"}
    merged.update(options)
    return ImageJob(mode="generate", prompt="a fox", seed=11, options=merged)


def edit_job(**options):
    merged = {"resolution": "match", "steps": 8, "guidance": 1.0, "negative": ""}
    merged.update(options)
    return ImageJob(
        mode="edit",
        prompt="make it night",
        seed=5,
        options=merged,
        references=(
            ReferenceImage(png=b"one", width=640, height=480),
            ReferenceImage(png=b"two", width=640, height=480),
        ),
    )


def test_the_payload_carries_values_not_paths():
    payload = generate_payload(job())

    assert payload == {
        "mode": "generate",
        "prompt": "a fox",
        "negative": "blur",
        "width": 768,
        "height": 512,
        "steps": 6,
        "guidance": 2.5,
        "seed": 11,
    }


def test_an_absent_negative_is_an_empty_string_and_missing_options_take_the_defaults():
    payload = generate_payload(ImageJob(mode="generate", prompt="a fox", seed=3, options={"size": "1024x1024"}))

    assert payload["negative"] == ""
    assert payload["steps"] == 8
    assert payload["guidance"] == 1.0


def test_a_run_turns_the_child_reply_into_an_image_result():
    child = Mock()
    child.request.return_value = {
        "png_base64": base64.b64encode(b"png").decode(),
        "width": 768,
        "height": 512,
        "steps": 6,
    }
    gateway = Qwen21CudaBackendGateway(child, badge="nvfp4")
    on_step, should_stop = Mock(), Mock()

    result = gateway.run(job(), on_step, should_stop)

    assert (result.png, result.width, result.height, result.seed, result.steps) == (b"png", 768, 512, 11, 6)
    child.request.assert_called_once_with(generate_payload(job()), on_step, should_stop)
    assert gateway.capabilities().badge == "nvfp4"


def test_load_waits_for_the_child_and_release_stops_it():
    child = Mock()
    gateway = Qwen21CudaBackendGateway(child, badge="bf16")

    gateway.load()
    gateway.release()

    child.wait_ready.assert_called_once()
    child.stop.assert_called_once()


def test_an_edit_payload_aims_at_the_reference_area_when_it_matches():
    payload = edit_payload(edit_job())

    assert payload["mode"] == "edit"
    assert payload["output_resolution"] == 544
    assert payload["steps"] == 8 and payload["guidance"] == 1.0
    assert payload["references"] == [base64.b64encode(b"one").decode(), base64.b64encode(b"two").decode()]


def test_an_edit_payload_takes_a_named_resolution_as_its_area_side():
    payload = edit_payload(edit_job(resolution="1328"))

    assert payload["output_resolution"] == 1328


def test_an_edit_falls_back_to_the_turbo_schedule_and_guidance():
    job_with_no_options = ImageJob(
        mode="edit", prompt="p", seed=1, options={}, references=(ReferenceImage(b"x", 4, 4),)
    )

    payload = edit_payload(job_with_no_options)

    assert payload["steps"] == 8 and payload["guidance"] == 1.0 and payload["negative"] == ""
    assert payload["output_resolution"] == 32


def test_match_holds_a_large_reference_to_the_mlx_edit_area_cap():
    screenshot = ImageJob(
        mode="edit",
        prompt="p",
        seed=1,
        options={"resolution": "match"},
        references=(ReferenceImage(b"x", 2560, 1440),),
    )

    assert edit_payload(screenshot)["output_resolution"] == 1344


def test_a_run_sends_the_edit_payload_for_an_edit():
    child = Mock()
    child.request.return_value = {
        "png_base64": base64.b64encode(b"png").decode(),
        "width": 640,
        "height": 480,
        "steps": 8,
    }
    gateway = Qwen21CudaBackendGateway(child, badge="bf16")
    on_step, should_stop = Mock(), Mock()

    result = gateway.run(edit_job(), on_step, should_stop)

    assert (result.width, result.height, result.steps) == (640, 480, 8)
    child.request.assert_called_once_with(edit_payload(edit_job()), on_step, should_stop)


def start_job(size, width=1600, height=900):
    return ImageJob(
        mode="generate",
        prompt="a blue bike",
        seed=2,
        options={"size": size, "steps": 8, "guidance": 1.0, "strength": 0.55},
        references=(ReferenceImage(png=b"start", width=width, height=height),),
    )


def test_a_generate_from_a_picture_sends_it_with_its_strength():
    payload = generate_payload(start_job("768x512"))

    assert base64.b64decode(payload["start"]) == b"start" and payload["strength"] == 0.55
    assert (payload["width"], payload["height"]) == (768, 512)


def test_match_takes_the_starting_picture_s_shape_at_about_a_megapixel():
    wide = generate_payload(start_job("match"))
    tall = generate_payload(start_job("match", width=1200, height=1600))

    # 1360x768 and 880x1184 on MLX; this pipeline floors to 32, so the payload names its grid.
    assert (wide["width"], wide["height"]) == (1344, 768)
    assert (tall["width"], tall["height"]) == (896, 1184)


def test_match_without_a_picture_renders_a_megapixel_square():
    payload = generate_payload(job(size="match"))

    assert (payload["width"], payload["height"]) == (1024, 1024)
    assert "start" not in payload and "strength" not in payload
