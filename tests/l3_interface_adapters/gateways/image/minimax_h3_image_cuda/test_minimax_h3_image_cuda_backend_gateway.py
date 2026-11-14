import base64
from unittest.mock import Mock

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.minimax_h3_image_cuda_backend_gateway import (
    MinimaxH3ImageCudaBackendGateway,
    generate_payload,
)


def job(**options):
    merged = {"size": "1024x576", "steps": 6}
    merged.update(options)
    return ImageJob(mode="generate", prompt="a fox", seed=11, options=merged)


def test_the_payload_carries_values_not_paths():
    assert generate_payload(job()) == {
        "mode": "generate",
        "prompt": "a fox",
        "width": 1024,
        "height": 576,
        "steps": 6,
        "seed": 11,
    }


def test_a_missing_step_count_takes_the_six_the_model_runs():
    assert (
        generate_payload(ImageJob(mode="generate", prompt="a fox", seed=1, options={"size": "1024x1024"}))["steps"] == 6
    )


def test_a_run_turns_the_child_reply_into_an_image_result():
    child = Mock()
    child.request.return_value = {
        "png_base64": base64.b64encode(b"png").decode(),
        "width": 1024,
        "height": 576,
        "steps": 6,
    }
    gateway = MinimaxH3ImageCudaBackendGateway(child, badge="nvfp4")
    on_step, should_stop = Mock(), Mock()

    result = gateway.run(job(), on_step, should_stop)

    assert (result.png, result.width, result.height, result.seed, result.steps) == (b"png", 1024, 576, 11, 6)
    child.request.assert_called_once_with(generate_payload(job()), on_step, should_stop)
    assert gateway.capabilities().badge == "nvfp4"


def test_load_waits_for_the_child_and_release_stops_it():
    child = Mock()
    gateway = MinimaxH3ImageCudaBackendGateway(child, badge="bf16")

    gateway.load()
    gateway.release()

    child.wait_ready.assert_called_once()
    child.stop.assert_called_once()
