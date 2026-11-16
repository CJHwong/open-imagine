import base64
from dataclasses import replace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.image_job import ImageJob, ReferenceImage
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.capabilities import EDIT_SIZE, SIZE
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.minimax_h3_image_cuda_backend_gateway import (
    MinimaxH3ImageCudaBackendGateway,
    edit_payload,
    generate_payload,
    match_size,
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


def edit_job(**options):
    merged = {"size": "match", "steps": 6}
    merged.update(options)
    return ImageJob(
        mode="edit",
        prompt="Make it <Picture 1> at night.",
        seed=4,
        options=merged,
        references=(ReferenceImage(png=b"one", width=1024, height=576),),
    )


def test_an_edit_payload_matches_the_first_reference_size():
    payload = edit_payload(edit_job())

    assert payload["mode"] == "edit"
    assert (payload["width"], payload["height"]) == (1024, 576)
    assert payload["steps"] == 6
    assert payload["references"] == [base64.b64encode(b"one").decode()]


@pytest.mark.parametrize(("width", "height"), [(1024, 576), (1030, 575), (2048, 2048), (4096, 1024)])
def test_match_preserves_the_reference_size(width, height):
    assert match_size(width, height) == (width, height)


@pytest.mark.parametrize(("width", "height"), [(100, 200), (8000, 2000), (4096, 255), (4097, 256)])
def test_match_rejects_reference_sizes_outside_engine_limits(width, height):
    with pytest.raises(InvalidJob, match=r"256.*4096"):
        match_size(width, height)


@pytest.mark.parametrize(("width", "height"), [(2049, 2048), (4096, 1025), (1025, 4096)])
def test_match_rejects_a_reference_over_four_megapixels(width, height):
    with pytest.raises(InvalidJob, match="4,194,304"):
        match_size(width, height)


@pytest.mark.parametrize(("width", "height"), [(1025, 256), (256, 1025)])
def test_match_rejects_a_reference_wider_than_four_to_one(width, height):
    with pytest.raises(InvalidJob, match="4:1"):
        match_size(width, height)


def test_edit_reference_at_the_aspect_limit_is_allowed():
    reference = ReferenceImage(png=b"one", width=1024, height=256)
    requested = replace(edit_job(size="1024x1024"), references=(reference,))
    assert edit_payload(requested)["references"] == [base64.b64encode(b"one").decode()]


def test_edit_offers_every_generate_size_and_an_accurate_match_label():
    assert {choice.value for choice in EDIT_SIZE.choices} == {choice.value for choice in SIZE.choices} | {"match"}
    match = next(choice for choice in EDIT_SIZE.choices if choice.value == "match")
    assert "4 MP" in match.label
    assert "4:1" in match.label


def test_an_edit_payload_takes_a_named_size():
    payload = edit_payload(edit_job(size="2048x2048"))

    assert (payload["width"], payload["height"]) == (2048, 2048)


def test_a_run_sends_the_edit_payload_for_an_edit():
    child = Mock()
    child.request.return_value = {
        "png_base64": base64.b64encode(b"png").decode(),
        "width": 2048,
        "height": 1152,
        "steps": 6,
    }
    gateway = MinimaxH3ImageCudaBackendGateway(child, badge="fp8")
    on_step, should_stop = Mock(), Mock()

    result = gateway.run(edit_job(), on_step, should_stop)

    assert (result.width, result.height) == (2048, 1152)
    child.request.assert_called_once_with(edit_payload(edit_job()), on_step, should_stop)
