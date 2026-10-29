"""Published Music examples obey the same validation as real requests."""

import base64
from copy import deepcopy

import pytest

from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase
from studio.l3_interface_adapters.api.openapi_examples import music_examples, operation_examples
from studio.l3_interface_adapters.controllers.music_controller import music_job
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities

EXAMPLES = ("generate", "instrumental", "plan", "render_score", "transcribe", "cover")


def with_reference_bytes(payload):
    request = deepcopy(payload)
    if "reference_audio" in request:
        assert request["reference_audio"].startswith("<replace with base64")
        request["reference_audio"] = base64.b64encode(b"reference transport fixture").decode("ascii")
    return request


@pytest.mark.parametrize("name", EXAMPLES)
def test_music_example_passes_real_request_validation(name):
    example = music_examples()[name]
    request = with_reference_bytes(example["value"])
    job = music_job(request, yue2_capabilities())
    assert example["summary"] and example["description"]
    assert job.mode == {"instrumental": "generate", "render_score": "generate"}.get(name, name)
    assert job.seed == request["seed"]
    if name == "instrumental":
        assert job.instrumental and not job.lyrics and job.cot != "off"
    if name == "render_score":
        assert job.abc == request["abc"] and "V: Vocal" in job.abc and "V: Ins" in job.abc
    if name in ("transcribe", "cover"):
        assert job.reference_audio == b"reference transport fixture" and not job.abc
        assert "Replace" in example["description"]
    else:
        assert not job.reference_audio


@pytest.mark.parametrize("name", EXAMPLES)
def test_music_operation_examples_pass_real_request_validation(name):
    example = operation_examples()["music_" + name]
    request = with_reference_bytes(example["value"])
    assert request["kind"] == "music"
    assert music_job(request, yue2_capabilities()).mode == request["mode"]


def test_music_batch_example_normalizes_defaults_and_keeps_distinct_seeds():
    request = operation_examples()["music_batch"]["value"]
    items = PrepareBatchUseCase().execute(request)
    jobs = [music_job(with_reference_bytes(item), yue2_capabilities()) for item in items]
    assert len(jobs) == 2
    assert [job.seed for job in jobs] == [7, 8]
    assert all(item["kind"] == "music" and item["backend"] == "yue2" for item in items)
    assert all(job.mode == "generate" and job.style == request["style"] for job in jobs)
    assert all(job.lyrics == request["lyrics"] for job in jobs)


def test_music_examples_are_fresh_for_each_request():
    examples = music_examples()
    examples["generate"]["value"]["style"] = "changed by a client"
    assert music_examples()["generate"]["value"]["style"] != "changed by a client"
