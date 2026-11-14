import base64
from unittest.mock import Mock

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.qwen21_cuda_backend_gateway import (
    Qwen21CudaBackendGateway,
    generate_payload,
)


def job(**options):
    merged = {"size": "768x512", "steps": 6, "guidance": 2.5, "negative": "blur"}
    merged.update(options)
    return ImageJob(mode="generate", prompt="a fox", seed=11, options=merged)


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
