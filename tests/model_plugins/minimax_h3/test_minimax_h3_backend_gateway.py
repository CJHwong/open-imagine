import base64
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from open_imagine_h3 import plugin
from open_imagine_h3.capabilities import CAPABILITIES
from open_imagine_h3.minimax_h3_backend_gateway import MinimaxH3BackendGateway
from open_imagine_h3.runtime import MAX_RESULT_BYTES, model_files

from studio.plugins import PluginContext
from studio.plugins.video import Cancelled, InvalidJob, VideoAudio, VideoJob, VideoReference


def job(**changes):
    return replace(VideoJob("private test words", 512, 288, 73, 24, 7), **changes)


@pytest.fixture
def ready(tmp_path, media_tools):
    engine = tmp_path / "engine"
    models = tmp_path / "models"
    for path in (engine / ".venv/bin/python", engine / "scripts/generate_staged.py", *model_files(models)):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture weights")
    (models / "h3-dit-q8/quant_config.json").write_text('{"bits":8,"group_size":64}')
    (models / "h3-dit-q8/model.safetensors.index.json").write_text(
        '{"weight_map":{"test.weight":"model-1.safetensors"}}'
    )
    (models / "h3-dit-q8/model-1.safetensors").write_bytes(b"fixture weights")
    return SimpleNamespace(settings={"engine_dir": str(engine), "model_dir": str(models)}, run_process=Mock())


def test_plugin_declaration_and_factory_load_no_engine_or_model():
    gateway = plugin.create(PluginContext({}, Mock()))

    assert plugin.capabilities == gateway.capabilities() == CAPABILITIES
    assert plugin.rewriter is None
    assert CAPABILITIES.estimate is None
    assert not CAPABILITIES.templates and not CAPABILITIES.fast_mode and not CAPABILITIES.can_skip_audio
    assert CAPABILITIES.duration_presets == (73, 124, 175) and CAPABILITIES.max_frames == 175
    # The engine encodes 17n+5 frames. It snaps any other count up, and the worker then refuses
    # the clip only after the models load.
    assert CAPABILITIES.frame_step == 17
    assert all((frames - 5) % 17 == 0 for frames in (CAPABILITIES.min_frames, CAPABILITIES.max_frames))
    generate = CAPABILITIES.mode("generate")
    assert CAPABILITIES.modes == (generate,) and not generate.needs_clip
    assert generate.accepts_audio and generate.max_references == CAPABILITIES.max_references == 3
    gateway.release()
    gateway.release()


def test_gateway_passes_private_input_and_binary_result_over_pipes(ready):
    seen = []
    clip = b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"

    def execute(command, **options):
        seen.append((command, options))
        options["consume"]('{"event":"step","step":1,')
        options["consume"]('"total":8}\nnot json\n[]\n{"event":"step","step":9,"total":8}\n')
        options["consume_output"](clip)

    ready.run_process = execute
    progress = Mock()

    result = MinimaxH3BackendGateway(ready).run(job(), progress)

    command, options = seen[0]
    assert "private test words" not in str(command) + str(options["environment"])
    assert json.loads(options["input_bytes"])["prompt"] == "private test words"
    assert options["terminate_group"] is True and options["timeout_seconds"] == 7200
    assert options["environment"]["HF_HUB_OFFLINE"] == "1"
    assert "private" not in options["failure_message"](2, ["private words"])
    assert result.mp4 == clip and result.seed == 7
    progress.assert_called_once_with(1, 8, 7)


def test_gateway_chooses_one_seed_and_can_run_without_a_progress_consumer(ready, monkeypatch):
    monkeypatch.setattr("open_imagine_h3.minimax_h3_backend_gateway.secrets.randbelow", lambda _: 23)

    def execute(_command, **options):
        options["consume"]('{"event":"step","step":1,"total":8}\n')
        options["consume_output"](b"\0\0\0\x18ftypisom")
        assert json.loads(options["input_bytes"])["seed"] == 23

    ready.run_process = execute

    result = MinimaxH3BackendGateway(ready).run(job(seed=None))

    assert result.seed == 23


def still(frame, name="private-still.png", strength=1.0):
    return VideoReference(name, b"\x89PNG private still " + str(frame).encode(), frame, strength)


def test_gateway_sends_keyframes_in_time_order_and_the_track_without_their_names(ready):
    seen = []

    def execute(command, **options):
        seen.append((command, options))
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute
    track = VideoAudio(b"RIFF private track", "private-voice.m4a")

    MinimaxH3BackendGateway(ready).run(job(references=(still(72), still(0), still(36)), audio=track))

    command, options = seen[0]
    request = json.loads(options["input_bytes"])
    assert [keyframe["frame"] for keyframe in request["keyframes"]] == [0, 36, 72]
    assert base64.b64decode(request["keyframes"][1]["png"]) == still(36).png
    assert base64.b64decode(request["audio"]) == track.data
    assert "private-" not in options["input_bytes"].decode() + str(command) + str(options["environment"])


def test_gateway_sends_no_keyframes_and_no_track_for_a_text_clip(ready):
    def execute(_command, **options):
        request = json.loads(options["input_bytes"])
        assert request["keyframes"] == [] and request["audio"] is None
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute

    MinimaxH3BackendGateway(ready).run(job())


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"edit": object()}, "no clip to change"),
        ({"loras": (object(),)}, "no clip to change"),
        ({"references": (still(0), still(24), still(48), still(72))}, "at most 3 H3 keyframes"),
        ({"references": (still(36), still(36))}, "its own frame"),
        ({"references": (still(73),)}, "its own frame"),
        ({"references": (still(-1),)}, "its own frame"),
        ({"num_frames": 175, "references": (still(175),)}, "its own frame"),
        ({"references": (still(True),)}, "its own frame"),
        ({"references": (still(0, strength=0.5),)}, "no strength setting"),
        ({"fast_mode": True}, "base schedule"),
        ({"include_audio": False}, "base schedule"),
        ({"width": 256}, "offered H3 size"),
        ({"num_frames": 125}, "offered H3 size"),
        ({"num_frames": 74}, "offered H3 size"),
        ({"num_frames": 56}, "a 73-175 frame clip"),
        ({"num_frames": 192}, "a 73-175 frame clip"),
        ({"frame_rate": 30}, "offered H3 size"),
        ({"seed": -1}, "H3 seed"),
        ({"seed": True}, "H3 seed"),
    ],
)
def test_gateway_refuses_unsupported_inputs_before_starting_a_child(ready, changes, reason):
    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3BackendGateway(ready).run(job(**changes))

    ready.run_process.assert_not_called()


@pytest.mark.parametrize("frames", range(73, 176, 17))
def test_gateway_runs_every_offered_length_with_a_still_on_its_last_frame(ready, frames):
    def execute(_command, **options):
        request = json.loads(options["input_bytes"])
        assert request["frames"] == frames
        assert [keyframe["frame"] for keyframe in request["keyframes"]] == [0, frames - 1]
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute

    result = MinimaxH3BackendGateway(ready).run(job(num_frames=frames, references=(still(0), still(frames - 1))))

    assert result.num_frames == frames


def test_gateway_refuses_cancellation_before_reading_weights(ready):
    with pytest.raises(Cancelled):
        MinimaxH3BackendGateway(ready).run(job(), cancelled=lambda: True)

    ready.run_process.assert_not_called()


def test_gateway_refuses_missing_media_tools_before_starting_a_model(ready, monkeypatch):
    monkeypatch.setattr("open_imagine_h3.minimax_h3_backend_gateway.shutil.which", lambda _: None)
    with pytest.raises(InvalidJob, match="ffmpeg and ffprobe"):
        MinimaxH3BackendGateway(ready).run(job())
    ready.run_process.assert_not_called()


def test_gateway_names_missing_engine_and_missing_weights(ready):
    python = Path(ready.settings["engine_dir"]) / ".venv/bin/python"
    python.unlink()
    with pytest.raises(InvalidJob, match="engine"):
        MinimaxH3BackendGateway(ready).run(job())
    python.touch()
    model_files(Path(ready.settings["model_dir"]))[0].unlink()
    with pytest.raises(InvalidJob, match="weights"):
        MinimaxH3BackendGateway(ready).run(job())


@pytest.mark.parametrize(
    "mode,reason",
    [
        ("empty", "did not return an MP4"),
        ("invalid", "did not return an MP4"),
        ("oversize", "output limit"),
        ("progress", "progress stream"),
    ],
)
def test_gateway_refuses_invalid_or_unbounded_worker_output(ready, mode, reason):
    def execute(_command, **options):
        if mode == "invalid":
            options["consume_output"](b"this is not an mp4")
        elif mode == "oversize":
            options["consume_output"](b"x" * (MAX_RESULT_BYTES + 1))
        elif mode == "progress":
            options["consume"]("x" * 16385)

    ready.run_process = execute

    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3BackendGateway(ready).run(job())


def test_shapes_keep_their_named_ratio_on_the_32_pixel_grid():
    for shape in CAPABILITIES.shapes:
        a, b = map(int, shape.ratio.split(":"))
        assert shape.width % 32 == shape.height % 32 == 0
        assert CAPABILITIES.min_dimension <= min(shape.width, shape.height)
        assert max(shape.width, shape.height) <= CAPABILITIES.max_dimension
        # 1280 x 704 is LTX's own 16:9 class, 2.3 percent wide, so a clip from either model has
        # the same frame. Every other size keeps its ratio within 1 percent.
        tolerance = 0.025 if {shape.width, shape.height} == {1280, 704} else 0.01
        assert abs(shape.width / shape.height / (a / b) - 1) < tolerance


@pytest.mark.parametrize(
    "filename,value",
    [
        ("quant_config.json", '{"bits":4,"group_size":64}'),
        ("quant_config.json", "[]"),
        ("quant_config.json", "invalid"),
        ("model.safetensors.index.json", "[]"),
        ("model.safetensors.index.json", '{"weight_map":{}}'),
        ("model.safetensors.index.json", '{"weight_map":{"weight":"missing.safetensors"}}'),
        ("model.safetensors.index.json", '{"weight_map":{"weight":"../outside.safetensors"}}'),
        ("model.safetensors.index.json", '{"weight_map":{"weight":3}}'),
    ],
)
def test_gateway_refuses_a_wrong_quantization_or_incomplete_pack(ready, filename, value):
    (Path(ready.settings["model_dir"]) / "h3-dit-q8" / filename).write_text(value)
    with pytest.raises(InvalidJob, match="weights"):
        MinimaxH3BackendGateway(ready).run(job())
    ready.run_process.assert_not_called()
