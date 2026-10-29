import base64
import io
import json
import runpy
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import soundfile

from studio.l3_interface_adapters.gateways.music.yue2 import yue2_mlx_child as child


def song():
    return SimpleNamespace(
        audio=np.zeros((48, 2), dtype=np.float32),
        sample_rate=48000,
        abc="X:1",
        truncated={"abc": False, "semantic": False},
        config={},
        weights={},
        timing={},
        request_identity="identity",
    )


def job():
    return {"style": "piano", "lyrics": "[Verse]\nhello", "seed": 7, "cot": "full", "abc": ""}


def test_worker_preserves_stereo_score_and_identity():
    engine = Mock(return_value=song())
    reply = child.answer(engine, job())
    audio, rate = soundfile.read(io.BytesIO(base64.b64decode(reply["wav"])), always_2d=True)
    assert audio.shape == (48, 2) and rate == 48000 and reply["score"] == "X:1"
    assert reply["metadata"]["request_identity"] == "identity"
    assert engine.call_args.kwargs["abc"] is None
    child.answer(engine, {**job(), "abc": "  \n"})
    assert engine.call_args.kwargs["abc"] is None
    engine.return_value.abc = None
    assert child.answer(engine, {**job(), "abc": "X:1"})["score"] == ""
    assert engine.call_args.kwargs["abc"] == "X:1"
    engine.return_value.truncated["semantic"] = True
    assert child.answer(engine, job())["kind"] == "input"


@pytest.mark.parametrize(
    "rate,shape,nan", [(24000, (48, 2), False), (48000, (48,), False), (48000, (48, 1), False), (48000, (48, 2), True)]
)
def test_worker_rejects_bad_engine_audio(rate, shape, nan):
    result = song()
    result.sample_rate = rate
    result.audio = np.full(shape, np.nan if nan else 0)
    with pytest.raises(ValueError, match="invalid stereo"):
        child.answer(Mock(return_value=result), job())


def test_main_protocol_keeps_engine_logs_out_of_json(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["worker", "--model-dir", "model", "--vae-dir", "vae"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(job()) + "\ninvalid\n"))
    monkeypatch.setattr(child, "load_engine", lambda args: Mock(return_value=song()))
    child.main()
    captured = capsys.readouterr()
    replies = [json.loads(line) for line in captured.out.splitlines()]
    assert len(replies) == 2 and "wav" in replies[0] and "error" in replies[1]
    assert "ready" in captured.err and "JSONDecodeError" in captured.err


def snapshot(tmp_path):
    root = tmp_path / "snapshot"
    (root / "vae/licenses").mkdir(parents=True)
    (root / "vae/config.json").write_text("{}")
    (root / "vae/licenses/license.txt").write_text("license")
    (root / "ar-8bit.safetensors").write_bytes(b"q8")
    (root / "licenses").mkdir()
    (root / "licenses/license.txt").write_text("generator license")
    (root / "conversion.json").write_text(
        json.dumps({"files": {"ar-8bit.safetensors": {}, "licenses/license.txt": {}}})
    )
    (root / ".gitattributes").write_text("not a model artifact")
    return root


def test_download_entrypoint_never_starts_gpu(monkeypatch, tmp_path):
    monkeypatch.setattr(
        sys,
        "argv",
        ["worker", "--model-dir", str(tmp_path / "model"), "--vae-dir", str(tmp_path / "vae"), "--download"],
    )
    monkeypatch.setitem(
        sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=Mock(return_value=str(snapshot(tmp_path))))
    )
    runpy.run_path(child.__file__, run_name="__main__")
    download = Mock()
    monkeypatch.setattr(child, "download_weights", download)
    child.main()
    download.assert_called_once()


def test_mlx_download_is_pinned_and_keeps_decoder_and_cache_outside_model(monkeypatch, tmp_path):
    download = Mock(return_value=str(snapshot(tmp_path)))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    model, vae = tmp_path / "model", tmp_path / "vae"
    child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(vae)))
    download.assert_called_once_with("vanch007/mlx-Yue2-3B", revision=child.MODEL_REVISION)
    assert {p.name for p in model.iterdir()} == {"ar-8bit.safetensors", "conversion.json", "licenses"}
    assert (model / "ar-8bit.safetensors").read_bytes() == b"q8"
    assert (vae / "licenses/license.txt").read_text() == "license"
    with pytest.raises(ValueError, match="outside"):
        child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(model / "vae")))
    assert download.call_count == 1
    # A repeat download accepts only the exact model tree; never erase extras.
    child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(vae)))
    extra = model / ".cache"
    extra.mkdir()
    with pytest.raises(ValueError, match="empty model_dir"):
        child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(vae)))
    assert extra.is_dir()
    extra.rmdir()
    extra = model / "unexpected.txt"
    extra.write_text("keep me")
    with pytest.raises(ValueError, match="existing files were kept"):
        child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(vae)))
    assert extra.read_text() == "keep me"
    extra.unlink()
    weight = model / "ar-8bit.safetensors"
    weight.unlink()
    weight.symlink_to(tmp_path / "snapshot/ar-8bit.safetensors")
    with pytest.raises(ValueError, match="empty model_dir"):
        child.download_weights(SimpleNamespace(model_dir=str(model), vae_dir=str(vae)))


def test_mlx_load_uses_q8_local_files_and_reports_solver_steps(monkeypatch, capsys):
    pipeline = Mock()
    nar = SimpleNamespace(synthesize=lambda *a, on_progress, **kw: on_progress(2, 32))
    monkeypatch.setitem(sys.modules, "lyra", SimpleNamespace(YuE2Pipeline=pipeline, nar=nar))
    engine = child.load_engine(SimpleNamespace(model_dir="model", vae_dir="vae"))
    assert engine is pipeline.from_pretrained.return_value
    assert pipeline.from_pretrained.call_args.kwargs == {
        "vae": "vae",
        "precision": "8bit",
        "local_files_only": True,
        "progress": False,
    }
    child.load_engine(SimpleNamespace(model_dir="model", vae_dir="vae"))
    callback = Mock()
    nar.synthesize(on_progress=callback)
    callback.assert_called_once_with(2, 32)
    nar.synthesize()
    assert "step 2/32" in capsys.readouterr().err


def test_mlx_token_callback_exposes_indeterminate_progress(capsys):
    def engine(**kwargs):
        for token in range(32):
            kwargs["on_token"]("abc", token)
        return song()

    reply = child.answer(engine, job())
    assert reply["metadata"]["generated_tokens"] == 32
    assert reply["metadata"]["engine"] == "mlx-q8"
    stderr = capsys.readouterr().err
    assert "step 1/0" in stderr and "step 16/0" in stderr and "step 32/0" in stderr


def plan():
    return SimpleNamespace(
        abc='X:1\nK:C\n"C"C4|',
        truncated=False,
        request=SimpleNamespace(to_dict=lambda: {"style": "piano", "lyrics": "hello"}),
        abc_ids=[1, 2],
        prefix=[3, 4],
        timing={"seconds": 0.5},
    )


def test_plan_returns_full_exact_planner_tokens_without_audio():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Config:
        ode_steps: int = 32

    engine = Mock(generation_config=Config(), weights={"mot": "pinned"})
    engine.plan.return_value = plan()
    engine.effective_config.return_value = {"cfg_scale": 2}
    reply = child.answer(engine, {**job(), "mode": "plan", "steps": 8, "cfg_scale": 2})
    assert reply["wav"] == "" and reply["score"] == plan().abc
    json.dumps(reply)  # No ndarray or model object escapes the JSON-pipe protocol.
    assert reply["metadata"]["plan"]["abc_ids"] == [1, 2]
    assert reply["metadata"]["plan"]["prefix"] == [3, 4]
    assert reply["metadata"]["weights"] == {"mot": "pinned"}
    assert engine.generation_config.ode_steps == 8
    assert engine.plan.call_args.kwargs["cfg_scale"] == 2
    engine.assert_not_called()
    engine.plan.return_value.truncated = True
    assert child.answer(engine, {**job(), "mode": "plan"})["kind"] == "input"
    engine.plan.return_value.truncated = False
    engine.plan.return_value.abc = None
    assert child.answer(engine, {**job(), "mode": "plan"})["score"] == ""


def test_worker_retains_only_one_generator_and_releases_it_before_transcribing(monkeypatch):
    engine = Mock()
    load = Mock(return_value=engine)
    monkeypatch.setattr(child, "load_engine", load)
    native = Mock(return_value=("X:1", {"transcription": "report"}))
    monkeypatch.setattr(child, "transcribe", native)
    args = SimpleNamespace(transcription_cache_dir="/cache")
    worker = child.Worker(args)
    worker.release()
    load.assert_not_called()
    assert worker.generator() is engine and worker.generator() is engine
    load.assert_called_once_with(args)
    assert worker.transcribe(job())[0] == "X:1"
    engine.close.assert_called_once()
    assert worker.engine is None
    native.assert_called_once_with(job(), "/cache")
    assert worker.generator() is engine
    assert load.call_count == 2
    worker.release()
    worker.release()
    assert engine.close.call_count == 2


def fake_transcriber(monkeypatch, result=None, error=None):
    from unittest.mock import MagicMock

    mx = SimpleNamespace(clear_cache=Mock())
    monkeypatch.setitem(sys.modules, "mlx", SimpleNamespace(core=mx))
    monkeypatch.setitem(sys.modules, "mlx.core", mx)
    guard = Mock()
    manager = MagicMock()
    manager.__enter__.return_value = guard
    factory = Mock(return_value=manager)
    monkeypatch.setitem(sys.modules, "lyra.measure", SimpleNamespace(GPUExecution=factory))
    paths = []

    def native(source, output, **kwargs):
        assert source.read_bytes() == b"reference"
        assert output.parent == source.parent
        assert kwargs["offline"] is True and kwargs["cache_dir"] == "/cache"
        assert kwargs["task"] == "full"
        assert kwargs["cancelled"]() is False
        kwargs["progress"]({"stage": "encoding", "window": 1, "windows": 2})
        kwargs["progress"]({"stage": "decoding", "tokens": 100})
        paths.append(source.parent)
        if error:
            raise error
        return result

    monkeypatch.setitem(sys.modules, "lyra.transcription.pipeline", SimpleNamespace(transcribe=native))
    return mx, guard, factory, paths


def transcription_job():
    return {**job(), "reference_audio": base64.b64encode(b"reference").decode(), "transcription_task": "full"}


def transcription_result(**overrides):
    return {
        "status": "complete",
        "truncated": False,
        "abc": "X:1\nK:C\nC4|",
        "midis": {"transcription": b"MThd"},
        "midi": b"MThd",
        "labs": {"key": "0\t4\tC\n"},
        "events": [{"time": 0}],
        "warnings": [],
        **overrides,
    }


def test_transcription_preserves_score_midi_labels_and_events_and_removes_upload(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    mx, guard, factory, paths = fake_transcriber(monkeypatch, transcription_result())
    score, metadata = child.transcribe(transcription_job(), "/cache")
    json.dumps(metadata)  # MIDI bytes must only appear as base64 artifacts.
    assert score == transcription_result()["abc"]
    assert metadata["transcription"]["events"] == [{"time": 0}]
    assert "midi" not in metadata["transcription"] and "midis" not in metadata["transcription"]
    assert [(item["name"], base64.b64decode(item["base64"])) for item in metadata["artifacts"]] == [
        ("transcription.mid", b"MThd"),
        ("key.lab", b"0\t4\tC\n"),
    ]
    assert paths[0].parent == tmp_path and not paths[0].exists()
    factory.assert_called_once_with(memory_budget_gib=16)
    guard.check.assert_called_once()
    mx.clear_cache.assert_called_once()
    assert "step 1/2" in capsys.readouterr().err


@pytest.mark.parametrize("overrides", [{"status": "failed"}, {"truncated": True}, {"abc": ""}])
def test_transcription_rejects_partial_or_empty_scores_and_releases_models(monkeypatch, overrides):
    mx, _, _, paths = fake_transcriber(monkeypatch, transcription_result(**overrides))
    with pytest.raises(ValueError, match="incomplete"):
        child.transcribe(transcription_job(), "/cache")
    mx.clear_cache.assert_called_once()
    assert not paths[0].exists()


def test_transcription_cleans_up_failures_and_rejects_empty_upload(monkeypatch):
    mx, _, _, paths = fake_transcriber(monkeypatch, error=RuntimeError("transcriber stopped"))
    with pytest.raises(RuntimeError, match="transcriber stopped"):
        child.transcribe(transcription_job(), "/cache")
    assert not paths[0].exists()
    mx.clear_cache.assert_called_once()
    with pytest.raises(ValueError, match="Upload reference"):
        child.transcribe({**transcription_job(), "reference_audio": ""}, "/cache")


@pytest.mark.parametrize("task,expected_cot", [("full", "full"), ("melody-vocal", "melody"), (None, "melody")])
def test_cover_uses_transcribed_notation_and_task_without_loading_both_models(monkeypatch, task, expected_cot):
    engine = Mock(return_value=song())
    monkeypatch.setattr(child, "load_engine", lambda args: engine)
    monkeypatch.setattr(child, "transcribe", lambda *args: ("transcribed ABC", {"artifacts": ["midi"]}))
    worker = child.Worker(SimpleNamespace(transcription_cache_dir="cache"))
    request = {**job(), "mode": "cover"}
    if task is not None:
        request["transcription_task"] = task
    reply = child.answer(worker, request)
    assert reply["metadata"]["artifacts"] == ["midi"]
    assert engine.call_args.kwargs["abc"] == "transcribed ABC"
    assert engine.call_args.kwargs["cot"] == expected_cot
    engine.close.assert_not_called()
    # A transcription request releases a retained generator and returns no audio.
    reply = child.answer(worker, {**transcription_job(), "mode": "transcribe"})
    assert reply["wav"] == "" and reply["score"] == "transcribed ABC"
    engine.close.assert_called_once()
    assert worker.engine is None


def test_instrumental_score_uses_pinned_converter_and_only_section_tags(monkeypatch):
    converter = Mock(return_value=("X:1\n% verse\nV:Ins\nC4|\n% outro\n", {"preserved": True}))
    monkeypatch.setitem(
        sys.modules, "lyra.music_tools.instrumental_support.instrumentalize", SimpleNamespace(convert_score=converter)
    )
    converted, lyrics, report = child.instrumental_score("source")
    converter.assert_called_once_with("source", overlap="vocal", keep_chords=True)
    assert converted.startswith("X:1") and lyrics == "[Verse]\n\n[Outro]" and report == {"preserved": True}
    converter.return_value = ("X:1", {})
    assert child.instrumental_score("source")[1] == ""
    monkeypatch.setitem(sys.modules, "lyra.music_tools.instrumental_support.instrumentalize", None)
    with pytest.raises(ValueError, match="setup_yue2_workflows"):
        child.instrumental_score("source")


@pytest.mark.parametrize("style,supplied", [("piano", False), ("Instrumental, piano", True)])
def test_instrumental_generation_transfers_melody_before_rendering(monkeypatch, style, supplied):
    engine = Mock(return_value=song())
    engine.plan.return_value = plan()
    convert = Mock(return_value=("instrumental ABC", "[Verse]", {"preserved": True}))
    monkeypatch.setattr(child, "instrumental_score", convert)
    reply = child.answer(engine, {**job(), "style": style, "instrumental": True, "abc": "supplied" if supplied else ""})
    assert reply["metadata"]["instrumental_transfer"] == {"preserved": True}
    assert engine.call_args.kwargs["style"] == "Instrumental, piano"
    assert engine.call_args.kwargs["lyrics"] == "[Verse]"
    assert engine.call_args.kwargs["abc"] == "instrumental ABC"
    convert.assert_called_once_with("supplied" if supplied else plan().abc)
    assert engine.plan.call_count == int(not supplied)
    with pytest.raises(ValueError, match="requires melody"):
        child.answer(engine, {**job(), "instrumental": True, "cot": "off"})
    engine.plan.return_value.truncated = True
    assert child.answer(engine, {**job(), "instrumental": True})["kind"] == "input"


def test_worker_protocol_reports_engine_crashes_and_releases_engine_on_eof(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["worker", "--model-dir", "model", "--vae-dir", "vae"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("{}\n{}\n"))
    engine = Mock()
    monkeypatch.setattr(child, "Worker", Mock(return_value=engine))
    monkeypatch.setattr(
        child, "answer", Mock(side_effect=[RuntimeError("engine crashed"), ImportError("install extras")])
    )
    child.main()
    captured = capsys.readouterr()
    replies = [json.loads(line) for line in captured.out.splitlines()]
    assert "check the engine installation" in replies[0]["error"]
    assert replies[1] == {"error": "install extras", "kind": "input"}
    engine.release.assert_called_once()


def test_instrumental_score_only_plan_returns_transferred_composition(monkeypatch):
    engine = Mock()
    original, transferred = plan(), plan()
    transferred.abc = "transferred instrumental ABC"
    engine.plan.side_effect = [original, transferred]
    engine.effective_config.return_value = {}
    engine.weights = {}
    monkeypatch.setattr(child, "instrumental_score", lambda score: (transferred.abc, "[Verse]", {"preserved": True}))
    reply = child.answer(engine, {**job(), "mode": "plan", "instrumental": True})
    assert reply["wav"] == "" and reply["score"] == transferred.abc
    assert engine.plan.call_count == 2
    assert engine.plan.call_args.kwargs["abc"] == transferred.abc
    engine.assert_not_called()


def titled_score():
    return (
        "X:1\nT:Original verification melody\nM:4/4\nL:1/4\nQ:1/4=100\n"
        'V: Vocal clef=treble name="Vocal Melody"\nV: Ins clef=treble name="Instrumental"\nK:C\n'
        '% verse\nV: Vocal\n"C"C2E2|"Am"G2E2|"F"F2A2|"G"G4|\n'
        "V: Ins\nC,2G,2|A,2E,2|F,2C2|G,4|\n"
    )


def test_instrumental_header_changes_only_display_labels_and_preserves_title_in_report(monkeypatch):
    original = titled_score()
    converted = "X:1\n% verse\nV:Ins\nC4|\n"
    converter = Mock(return_value=(converted, {"preserved": True}))
    monkeypatch.setitem(
        sys.modules, "lyra.music_tools.instrumental_support.instrumentalize", SimpleNamespace(convert_score=converter)
    )
    score, lyrics, report = child.instrumental_score(original)
    normalized = converter.call_args.args[0]
    assert normalized.splitlines()[1] == "T:"
    assert normalized.splitlines()[5:7] == [
        'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"',
        'V: Ins clef=treble name="Ins Melody" snm="Inst."',
    ]
    assert normalized.splitlines()[8:] == original.splitlines()[8:]
    assert normalized.splitlines()[2:5] == original.splitlines()[2:5]
    assert report == {"preserved": True, "original_title": "Original verification melody"}
    assert score == converted and lyrics == "[Verse]"
    json.dumps(report)


def test_instrumental_header_accepts_display_whitespace_and_does_not_create_missing_title():
    source = titled_score().replace("T:Original verification melody", "T:")
    source = source.replace(
        'V: Vocal clef=treble name="Vocal Melody"', '  V:  Vocal clef = treble name = "Lead" snm = "V"  '
    )
    normalized, title = child.instrumental_header(source.rstrip("\n"))
    assert title == "" and not normalized.endswith("\n")
    assert normalized.splitlines()[5] == 'V: Vocal clef=treble name="Vocal Melody" snm="Vocal"'
    normalized, title = child.instrumental_header(titled_score().replace("T:Original verification melody", "P:verse"))
    assert title == "" and normalized.splitlines()[1] == "P:verse"


@pytest.mark.parametrize(
    "replacement",
    ["clef=bass", "clef=treble octave=-1", "clef=treble transpose=12", "clef=treble foo=1", "clef=treble8", ""],
)
def test_instrumental_header_rejects_voice_attributes_with_unverified_musical_meaning(replacement):
    source = titled_score().replace("clef=treble", replacement, 1)
    with pytest.raises(ValueError, match="Normalize other clefs, octave or transposition"):
        child.instrumental_header(source)


def test_transcription_cache_reuses_audio_and_task_without_releasing_generator(monkeypatch):
    engine = Mock()
    load = Mock(return_value=engine)
    native = Mock(return_value=("X:1", {"transcription": {"elapsed_seconds": 5}, "artifacts": [{"name": "score.mid"}]}))
    monkeypatch.setattr(child, "load_engine", load)
    monkeypatch.setattr(child, "transcribe", native)
    worker = child.Worker(SimpleNamespace(transcription_cache_dir="/cache"))
    original = {**transcription_job(), "transcription_task": "melody-full"}
    original.pop("transcription_task")
    first = worker.transcribe(original)
    assert first[1]["transcription_cache_hit"] is False
    first[1]["artifacts"][0]["name"] = "changed"
    worker.generator()
    second = worker.transcribe(
        {
            **original,
            "transcription_task": "melody-full",
            "seed": 99,
            "style": "jazz",
            "lyrics": "new words",
            "reference_name": "renamed.wav",
        }
    )
    assert second[0] == "X:1"
    assert second[1]["transcription_cache_hit"] is True
    assert second[1]["artifacts"][0]["name"] == "score.mid"
    second[1]["artifacts"][0]["name"] = "changed again"
    assert worker.transcribe(original)[1]["artifacts"][0]["name"] == "score.mid"
    native.assert_called_once_with(original, "/cache")
    engine.close.assert_not_called()
    assert worker.generator() is engine
    load.assert_called_once()


@pytest.mark.parametrize(
    "changed",
    [
        {"reference_audio": base64.b64encode(b"other recording").decode()},
        {"transcription_task": "melody-vocal"},
    ],
)
def test_transcription_cache_replaces_one_entry_when_audio_or_task_changes(monkeypatch, changed):
    engine = Mock()
    native = Mock(return_value=("X:1", {}))
    monkeypatch.setattr(child, "load_engine", lambda args: engine)
    monkeypatch.setattr(child, "transcribe", native)
    worker = child.Worker(SimpleNamespace(transcription_cache_dir="/cache"))
    original = transcription_job()
    worker.transcribe(original)
    worker.generator()
    assert worker.transcribe({**original, **changed})[1]["transcription_cache_hit"] is False
    engine.close.assert_called_once()
    assert worker.engine is None
    assert worker.transcribe(original)[1]["transcription_cache_hit"] is False
    assert native.call_count == 3


def test_transcription_cache_does_not_store_failures_and_release_clears_it(monkeypatch):
    native = Mock(side_effect=[ValueError("incomplete"), ("X:1", {}), ("X:1", {})])
    monkeypatch.setattr(child, "transcribe", native)
    worker = child.Worker(SimpleNamespace(transcription_cache_dir="/cache"))
    with pytest.raises(ValueError, match="incomplete"):
        worker.transcribe(transcription_job())
    assert worker.transcribe(transcription_job())[1]["transcription_cache_hit"] is False
    assert worker.transcribe(transcription_job())[1]["transcription_cache_hit"] is True
    worker.release()
    assert worker.transcribe(transcription_job())[1]["transcription_cache_hit"] is False
    assert native.call_count == 3


def test_transcription_cache_rejects_invalid_base64_before_releasing_generator(monkeypatch):
    engine = Mock()
    native = Mock()
    monkeypatch.setattr(child, "load_engine", lambda args: engine)
    monkeypatch.setattr(child, "transcribe", native)
    worker = child.Worker(SimpleNamespace(transcription_cache_dir="/cache"))
    worker.generator()
    with pytest.raises(ValueError):
        worker.transcribe({**transcription_job(), "reference_audio": "not valid base64!"})
    native.assert_not_called()
    engine.close.assert_not_called()
