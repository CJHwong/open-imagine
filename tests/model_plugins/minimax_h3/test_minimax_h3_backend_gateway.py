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
from studio.plugins.video import Cancelled, InvalidJob, VideoJob


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
    assert not CAPABILITIES.templates and not CAPABILITIES.max_references and not CAPABILITIES.fast_mode
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


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"references": (object(),)}, "text only"),
        ({"edit": object()}, "text only"),
        ({"audio": object()}, "text only"),
        ({"loras": (object(),)}, "text only"),
        ({"fast_mode": True}, "base schedule"),
        ({"include_audio": False}, "base schedule"),
        ({"width": 256}, "offered H3 size"),
        ({"num_frames": 125}, "offered H3 size"),
        ({"num_frames": 74}, "offered H3 size"),
        ({"frame_rate": 30}, "offered H3 size"),
        ({"seed": -1}, "H3 seed"),
        ({"seed": True}, "H3 seed"),
    ],
)
def test_gateway_refuses_unsupported_inputs_before_starting_a_child(ready, changes, reason):
    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3BackendGateway(ready).run(job(**changes))

    ready.run_process.assert_not_called()


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
        assert abs(shape.width / shape.height / (a / b) - 1) < 0.01


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
