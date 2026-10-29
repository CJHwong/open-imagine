import base64
from dataclasses import replace
from unittest.mock import Mock

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l3_interface_adapters.controllers.music_controller import MusicController, music_job
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities

CAPS = yue2_capabilities()
PAYLOAD = {"style": "piano pop", "lyrics": "[Verse]\nA quiet road", "seed": 7}


def test_music_input_preserves_lyrics_score_and_seed():
    job = music_job({**PAYLOAD, "abc": "X:1\nK:C\nCDEF|", "cot": "melody"}, CAPS)
    assert job.style == "piano pop" and job.lyrics == PAYLOAD["lyrics"]
    assert job.seed == 7 and job.cot == "melody" and job.abc.startswith("X:1")
    assert 0 <= music_job({**PAYLOAD, "seed": None}, CAPS).seed < 2**32
    assert 0 <= music_job({**PAYLOAD, "seed": ""}, CAPS).seed < 2**32


@pytest.mark.parametrize(
    "patch",
    [
        {"style": ""},
        {"style": 4},
        {"style": "a" * 4001},
        {"lyrics": " "},
        {"lyrics": None},
        {"lyrics": "a" * 20001},
        {"abc": 3},
        {"abc": "a" * 100001},
        {"cot": "bad"},
        {"cot": "off", "abc": "X:1"},
        {"mode": "edit"},
        {"backend": "other"},
        {"seed": True},
        {"seed": -1},
        {"seed": 2**32},
        {"seed": 3.2},
        {"seed": "1"},
    ],
)
def test_bad_composition_never_reaches_model(patch):
    with pytest.raises(InvalidJob):
        music_job({**PAYLOAD, **patch}, CAPS)


def test_controller_catalog_and_batch_validation():
    run, catalog, switch = Mock(), Mock(), Mock()
    catalog.active_id.return_value = "yue2"
    catalog.visible_ids.return_value = ("yue2",)
    catalog.get.return_value.capabilities.return_value = CAPS
    controller = MusicController(run, catalog, switch)
    assert controller.active_id() == "yue2"
    assert controller.backends() == [{"id": "yue2", "name": "YuE2 (MLX Q8)"}]
    assert controller.capabilities()["channels"] == 2
    assert controller.model_capabilities() == CAPS
    for backend in (None, 4):
        with pytest.raises(InvalidJob):
            controller.model_capabilities(backend)
    for backend in (None, "", 4):
        with pytest.raises(InvalidJob):
            controller.run({**PAYLOAD, "backend": backend})
    controller.switch({"backend": "yue2"})
    switch.execute.assert_called_once_with("yue2")
    controller.run(PAYLOAD)
    assert run.execute.call_args.args == (music_job(PAYLOAD, CAPS), "yue2")
    controller.run_batch([PAYLOAD, {**PAYLOAD, "seed": 8}], Mock(), Mock(), Mock())
    assert [job.seed for job in run.execute_batch.call_args.args[0]] == [7, 8]
    catalog.get.return_value.capabilities.return_value = replace(CAPS, max_batch=1)
    with pytest.raises(InvalidJob, match="at most 1"):
        controller.run_batch([PAYLOAD, PAYLOAD], Mock(), Mock(), Mock())


@pytest.mark.parametrize("mode", ["generate", "plan", "transcribe", "cover"])
def test_all_music_workflows_validate_before_loading(mode):
    payload = {**PAYLOAD, "mode": mode, "steps": 8, "cfg_scale": 2.5}
    if mode in ("transcribe", "cover"):
        payload.update(reference_audio=base64.b64encode(b"audio").decode(), reference_name="source.wav")
    if mode == "transcribe":
        payload.update(style="", lyrics="")
    job = music_job(payload, CAPS)
    assert job.mode == mode and job.steps == 8 and job.cfg_scale == 2.5
    assert job.reference_audio == (b"audio" if mode in ("transcribe", "cover") else b"")


def test_instrumental_does_not_require_lyrics_and_supplied_score_keeps_its_bytes():
    score = "\nX:1\nK:C\nCDEF|\n\n"
    job = music_job({**PAYLOAD, "lyrics": "", "instrumental": True, "abc": score}, CAPS)
    assert job.lyrics == "" and job.instrumental and job.abc == score


@pytest.mark.parametrize(
    "patch",
    [
        {"instrumental": 1},
        {"mode": "plan", "cot": "off"},
        {"instrumental": True, "cot": "off"},
        {"steps": 4},
        {"steps": True},
        {"steps": 8.0},
        {"cfg_scale": True},
        {"cfg_scale": -1},
        {"cfg_scale": 6},
        {"cfg_scale": float("nan")},
        {"cfg_scale": float("inf")},
        {"cfg_scale": "1"},
        {"transcription_task": "vocal"},
        {"reference_name": 4},
        {"reference_name": "x" * 256},
        {"reference_name": "bad\x00name"},
        {"reference_audio": 3},
        {"reference_audio": "!bad!"},
        {"reference_audio": "é"},
        {"reference_audio": "YXVkaW8="},
        {"mode": "cover"},
        {"mode": "transcribe"},
    ],
)
def test_unsupported_or_incomplete_workflow_never_reaches_model(patch):
    with pytest.raises(InvalidJob):
        music_job({**PAYLOAD, **patch}, CAPS)


def test_reference_limit_applies_to_encoded_and_decoded_bytes():
    caps = replace(CAPS, max_reference_bytes=1)
    for reference in ("YWI=", "YWJjZA=="):
        with pytest.raises(InvalidJob, match="32 MiB"):
            music_job({**PAYLOAD, "mode": "cover", "reference_audio": reference}, caps)


@pytest.mark.parametrize("mode", ["cover", "transcribe"])
def test_reference_workflows_refuse_a_conflicting_supplied_score(mode):
    with pytest.raises(InvalidJob, match="cannot be used together"):
        music_job({**PAYLOAD, "mode": mode, "abc": "X:1", "reference_audio": "YXVkaW8="}, CAPS)


def test_whitespace_only_score_is_absent():
    assert music_job({**PAYLOAD, "abc": "  \n", "cot": "off"}, CAPS).abc == ""
