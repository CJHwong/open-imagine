"""A voice or music plan: the job's settings and its time, with no run."""

from dataclasses import replace

from studio.l1_entities.estimate_stages import Stage
from studio.l1_entities.music_job import MusicJob
from studio.l1_entities.voice_job import SpeechJob
from studio.l2_use_cases.plan_audio_use_case import plan_song, plan_speech
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.capabilities import drama_cuda_capabilities

FIRST_RUN = (Stage("compile", 20.0),)


def test_a_voice_plan_holds_the_job_s_settings_and_the_declared_load():
    capabilities = replace(drama_cuda_capabilities(), load_seconds=45.0, may_add=FIRST_RUN)
    job = SpeechJob("generate", "x" * 100, 7, {"temperature": 0.7})

    response = plan_speech("drama3_cuda", capabilities, job)

    assert (response.backend, response.mode, response.count) == ("drama3_cuda", "generate", 1)
    assert response.effective_options == {"temperature": 0.7}
    assert (response.loras, response.offers_loras) == ((), False)
    # 100 characters at 0.077 s is 7.7 s of speech: 0.28 + 1.383 x 7.7.
    assert response.estimate.total_seconds == 10.9
    assert (response.estimate.load_seconds, response.estimate.may_add) == (45.0, FIRST_RUN)


def test_a_music_plan_holds_the_settings_but_not_the_words_or_the_media():
    capabilities = replace(yue2_capabilities(), load_seconds=90.0)
    job = MusicJob("pop", "la la", 7, cot="melody", abc="X:1", steps=16, reference_audio=b"RIFF")

    response = plan_song("yue2", capabilities, job)

    assert response.effective_options == {
        "instrumental": False,
        "cot": "melody",
        "steps": 16,
        "cfg_scale": 1.0,
        "transcription_task": "melody-full",
        "sampling": {},
    }
    assert response.estimate.basis == "constants"
    assert response.estimate.load_seconds == 90.0
    assert [stage.name for stage in response.estimate.stages] == ["fixed", "generation"]
