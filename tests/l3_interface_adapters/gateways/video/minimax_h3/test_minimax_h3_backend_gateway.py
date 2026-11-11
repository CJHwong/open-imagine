import base64
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l1_entities.video_estimate import estimate_clip
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import (
    BASE_FORWARDS,
    CAPABILITIES,
    FAST_FORWARDS,
    FAST_MAX_ROWS,
    FLASH,
    FLASH_CAPABILITIES,
    FLASH_FORWARDS,
    video_rows,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.construction import (
    FLASH_PROVIDER,
    PROVIDER,
    minimax_h3_backend,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway import MinimaxH3BackendGateway
from studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_flash_backend_gateway import (
    MinimaxH3FlashBackendGateway,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.runtime import (
    FLASH_PACK,
    MAX_RESULT_BYTES,
    model_files,
)
from studio.l3_interface_adapters.gateways.video.minimax_h3.storage_assets import flash_storage_assets
from studio.l4_frameworks_and_drivers.config import Config
from studio.plugins.video import Cancelled, InvalidJob, Lora, LoraUse, VideoAudio, VideoJob, VideoReference


def test_badge_preserves_precision_and_frame_rate_without_a_middle_dot():
    assert CAPABILITIES.badge == "Q8, 24 fps"


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
    return SimpleNamespace(
        settings={"engine_dir": str(engine), "model_dir": str(models)},
        run_process=Mock(),
        capabilities=None,
        lora_paths={},
    )


@pytest.fixture
def offered(ready, tmp_path):
    """The context that the host builds from two [[minimax_h3.loras]] tables."""
    folder = tmp_path / "private-loras"
    folder.mkdir()
    for name in ("motion", "detail"):
        (folder / f"private-{name}.safetensors").write_bytes(b"fixture adapter")
    ready.capabilities = replace(
        CAPABILITIES,
        loras=(Lora("motion", "Motion", trigger="test motion"), Lora("detail", "Detail")),
        max_loras=2,
    )
    ready.lora_paths = {name: str(folder / f"private-{name}.safetensors") for name in ("motion", "detail")}
    return ready


def test_builtin_provider_and_factory_load_no_engine_or_model():
    gateway = minimax_h3_backend(Config("", (), "", (), {}), execute_process=Mock())

    assert gateway.capabilities() == CAPABILITIES
    assert PROVIDER.rewriter is None
    # The host reads the LoRA tables, so the record itself declares none.
    assert not CAPABILITIES.loras and not CAPABILITIES.loras_with_audio
    assert CAPABILITIES.estimate is None
    assert not CAPABILITIES.templates and not CAPABILITIES.can_skip_audio
    # Fast mode is fewer steps, so the form shows H3's own note and not LTX's float16 one.
    assert CAPABILITIES.fast_mode and "half the denoise steps" in CAPABILITIES.fast_mode_note
    assert FAST_FORWARDS * 2 == BASE_FORWARDS
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
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway.secrets.randbelow",
        lambda _: 23,
    )

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
        ({"references": (still(0), still(24), still(48), still(72))}, "at most 3 H3 keyframes"),
        ({"references": (still(36), still(36))}, "its own frame"),
        ({"references": (still(73),)}, "its own frame"),
        ({"references": (still(-1),)}, "its own frame"),
        ({"num_frames": 175, "references": (still(175),)}, "its own frame"),
        ({"references": (still(True),)}, "its own frame"),
        ({"references": (still(0, strength=0.5),)}, "no strength setting"),
        ({"include_audio": False}, "always includes its sound"),
        ({"width": 528}, "32 pixel grid"),
        ({"width": 224}, "256-1280 pixels a side"),
        ({"width": 1280, "height": 960}, "at most 901120 pixels"),
        ({"num_frames": 125}, "H3 size"),
        ({"num_frames": 74}, "H3 size"),
        ({"num_frames": 56}, "a 73-175 frame clip"),
        ({"num_frames": 192}, "a 73-175 frame clip"),
        ({"frame_rate": 30}, "at 24 fps"),
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


@pytest.mark.parametrize("size", [(640, 480), (480, 640), (1024, 768), (1280, 704)])
def test_gateway_runs_a_size_of_any_ratio_up_to_the_largest_shape(ready, size):
    """A clip from a 4:3 picture keeps 4:3. The shapes are the page's menu, not a limit."""
    width, height = size

    def execute(_command, **options):
        request = json.loads(options["input_bytes"])
        assert (request["width"], request["height"]) == size
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute

    result = MinimaxH3BackendGateway(ready).run(job(width=width, height=height))

    assert (result.width, result.height) == size


def test_gateway_refuses_cancellation_before_reading_weights(ready):
    with pytest.raises(Cancelled):
        MinimaxH3BackendGateway(ready).run(job(), cancelled=lambda: True)

    ready.run_process.assert_not_called()


def test_gateway_refuses_missing_media_tools_before_starting_a_model(ready, monkeypatch):
    monkeypatch.setattr(
        "studio.l3_interface_adapters.gateways.video.minimax_h3.minimax_h3_backend_gateway.shutil.which", lambda _: None
    )
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


def test_gateway_offers_the_hosts_loras_and_sends_each_pick_as_its_file(offered):
    seen = []

    def execute(command, **options):
        seen.append((command, options))
        options["consume_output"](b"\0\0\0\x18ftypisom")

    offered.run_process = execute
    gateway = MinimaxH3BackendGateway(offered)

    gateway.run(job(loras=(LoraUse("detail", 0.4), LoraUse("motion", 0.7))))

    command, options = seen[0]
    request = json.loads(options["input_bytes"])
    assert gateway.capabilities() == offered.capabilities
    assert request["loras"] == [
        {"path": offered.lora_paths["detail"], "scale": 0.4},
        {"path": offered.lora_paths["motion"], "scale": 0.7},
    ]
    # The trigger words go after the prompt, as for every video model.
    assert request["prompt"] == "private test words, test motion"
    assert "private-" not in str(command) + str(options["environment"])


def test_gateway_sends_no_loras_when_none_are_picked(offered):
    def execute(_command, **options):
        request = json.loads(options["input_bytes"])
        assert request["loras"] == [] and request["prompt"] == "private test words"
        options["consume_output"](b"\0\0\0\x18ftypisom")

    offered.run_process = execute

    MinimaxH3BackendGateway(offered).run(job())


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"loras": (LoraUse("unknown", 1.0),)}, "no LoRA called unknown"),
        ({"loras": (LoraUse("motion", 1.0),), "audio": VideoAudio(b"RIFF", "voice.wav")}, "follows a track"),
    ],
)
def test_gateway_refuses_a_lora_it_cannot_apply_before_starting_a_child(offered, changes, reason):
    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3BackendGateway(offered).run(job(**changes))

    offered.run_process.assert_not_called()


def test_gateway_refuses_a_missing_lora_file_by_its_id_and_logs_nothing(offered, capsys):
    Path(offered.lora_paths["motion"]).unlink()

    with pytest.raises(InvalidJob, match="LoRA motion are not on disk") as refused:
        MinimaxH3BackendGateway(offered).run(job(loras=(LoraUse("motion", 1.0),)))

    offered.run_process.assert_not_called()
    assert "private-" not in str(refused.value)
    assert capsys.readouterr() == ("", "")


def test_gateway_refuses_a_lora_in_a_folder_it_cannot_read_by_its_id(offered):
    folder = Path(offered.lora_paths["motion"]).parent
    folder.chmod(0)
    try:
        with pytest.raises(InvalidJob, match="LoRA motion are not on disk") as refused:
            MinimaxH3BackendGateway(offered).run(job(loras=(LoraUse("motion", 1.0),)))
    finally:
        folder.chmod(0o755)

    # The error of a folder that cannot be read names the path, and a failure shows on the page.
    offered.run_process.assert_not_called()
    assert "private-" not in str(refused.value)


@pytest.mark.parametrize(
    "applied,unaccounted,reason",
    [
        (0, 0, "no layer that it can load in LoRA motion"),
        (0, 12, "No part of LoRA motion matches a layer"),
        (208, 51, "LoRA motion has 51 parts with no matching layer"),
        # The real engine counts one adaLN pair this way, on a file with one fc2 pair beside it.
        (1, 1, "LoRA motion has 1 part with no matching layer"),
    ],
)
def test_gateway_names_the_lora_that_the_engine_could_not_apply(offered, applied, unaccounted, reason):
    def execute(_command, **options):
        event = {"event": "lora_unfit", "index": 1, "applied": applied, "unaccounted": unaccounted}
        options["consume"](json.dumps(event) + "\n")
        raise AssertionError("the gateway kept reading after an unfit LoRA")

    offered.run_process = execute

    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3BackendGateway(offered).run(job(loras=(LoraUse("detail", 1.0), LoraUse("motion", 0.5))))


@pytest.mark.parametrize(
    "event",
    [
        {"event": "lora_unfit", "index": 1, "applied": 0, "unaccounted": 0},
        {"event": "lora_unfit", "index": -1, "applied": 0, "unaccounted": 0},
        {"event": "lora_unfit", "index": True, "applied": 0, "unaccounted": 0},
        {"event": "lora_unfit", "index": 0, "applied": "0", "unaccounted": 0},
        {"event": "lora_unfit", "index": 0, "applied": 0},
    ],
)
def test_gateway_ignores_a_malformed_lora_event(offered, event):
    def execute(_command, **options):
        options["consume"](json.dumps(event) + "\n")
        options["consume_output"](b"\0\0\0\x18ftypisom")

    offered.run_process = execute

    result = MinimaxH3BackendGateway(offered).run(job(loras=(LoraUse("motion", 1.0),)))

    assert result.mp4[4:8] == b"ftyp"


@pytest.mark.parametrize("fast", [False, True])
def test_gateway_runs_fast_mode_as_half_the_forwards_and_reports_its_steps(ready, fast):
    seen = []
    forwards = FAST_FORWARDS if fast else BASE_FORWARDS

    def execute(_command, **options):
        seen.append(json.loads(options["input_bytes"]))
        # A total from the other schedule is not this run's progress.
        options["consume"](f'{{"event":"step","step":1,"total":{forwards}}}\n{{"event":"step","step":1,"total":12}}\n')
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute
    progress = Mock()

    MinimaxH3BackendGateway(ready).run(job(fast_mode=fast), progress)

    assert seen[0]["forwards"] == forwards
    progress.assert_called_once_with(1, forwards, 7)


def test_fast_mode_takes_the_measured_clip_and_its_rows_cap_matches_it():
    # The measured clip came from one still, and each still adds one latent frame of rows.
    assert video_rows(1024, 576, 124, 1) == FAST_MAX_ROWS
    assert video_rows(1024, 576, 124, 0) < FAST_MAX_ROWS < video_rows(1024, 576, 124, 2)
    assert video_rows(1280, 704, 73, 2) <= FAST_MAX_ROWS < video_rows(1024, 576, 141, 0)


@pytest.mark.parametrize(
    "width,height,frames,stills,taken",
    [
        (512, 288, 175, 3, True),
        (512, 512, 175, 0, True),
        (1024, 576, 124, 0, True),
        (1024, 576, 124, 1, True),
        (576, 1024, 124, 1, True),
        (1280, 704, 73, 2, True),
        (1024, 576, 124, 2, False),
        (1024, 576, 124, 3, False),
        (1280, 704, 73, 3, False),
        (1024, 576, 141, 0, False),
        (1280, 704, 90, 0, False),
        (704, 1280, 175, 0, False),
    ],
)
def test_gateway_refuses_fast_mode_past_the_measured_clip_before_starting_a_child(
    ready, width, height, frames, stills, taken
):
    def execute(_command, **options):
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = Mock(side_effect=execute)
    references = tuple(still(frame) for frame in (0, frames // 2, frames - 1)[:stills])
    clip = job(fast_mode=True, width=width, height=height, num_frames=frames, references=references)

    if taken:
        MinimaxH3BackendGateway(ready).run(clip)
        ready.run_process.assert_called_once()
    else:
        with pytest.raises(InvalidJob, match="up to the size of 1024 x 576 at 124 frames with one keyframe"):
            MinimaxH3BackendGateway(ready).run(clip)
        ready.run_process.assert_not_called()
        # The same clip at the base schedule runs.
        MinimaxH3BackendGateway(ready).run(replace(clip, fast_mode=False))


@pytest.fixture
def flash_ready(ready):
    """The model folder of `ready`, with a converted Flash transformer beside the base one."""
    models = Path(ready.settings["model_dir"])
    for path in model_files(models, FLASH_PACK):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture weights")
    (models / FLASH_PACK / "quant_config.json").write_text('{"bits":8,"group_size":64}')
    (models / FLASH_PACK / "model.safetensors.index.json").write_text(
        '{"weight_map":{"test.weight":"model-1.safetensors"}}'
    )
    (models / FLASH_PACK / "model-1.safetensors").write_bytes(b"fixture weights")
    (models / FLASH_PACK / "flash.json").write_text('{"hyperflow_gate":0.25,"dropped_blocks":[6,21,22]}')
    return ready


def test_flash_is_a_second_model_on_the_h3_settings_with_its_own_record():
    config = Config("", (), "", (), {"minimax_h3": {"model_dir": "/weights/h3", "loras": [{"id": "x"}]}})
    gateway = FLASH_PROVIDER.create(config, execute_process=Mock())

    assert FLASH_PROVIDER.backend_id == "minimax_h3_flash" and FLASH_PROVIDER.kind == "video"
    assert gateway.capabilities() == FLASH_CAPABILITIES == FLASH.capabilities
    # Flash offers what was tried on its weights: text and keyframes. It reads no LoRA table.
    generate = FLASH_CAPABILITIES.mode("generate")
    assert not generate.accepts_audio and generate.max_references == 3
    assert not FLASH_CAPABILITIES.fast_mode and not FLASH_CAPABILITIES.fast_mode_note
    assert not FLASH_CAPABILITIES.loras
    # The sizes and the lengths are the ones of base H3, so one set of checks serves both.
    assert FLASH_CAPABILITIES.shapes == CAPABILITIES.shapes
    assert (FLASH_CAPABILITIES.min_frames, FLASH_CAPABILITIES.max_frames) == (73, 175)
    assert FLASH_CAPABILITIES.estimate is not None and FLASH_CAPABILITIES.estimate.forwards == FLASH_FORWARDS == 6
    assert FLASH_PROVIDER.estimator is not None and PROVIDER.estimator is not None
    assert FLASH_PROVIDER.estimator(config) is PROVIDER.estimator(config)
    # Flash owns only its transformer, inside the model folder of base H3.
    assert [asset.location for asset in flash_storage_assets(config)] == ["/weights/h3/h3-flash-dit-q8"]
    assert flash_storage_assets(Config("", (), "", (), {})) == ()
    assert FLASH_PROVIDER.storage_assets is flash_storage_assets


def test_flash_runs_six_forwards_on_its_own_pack(flash_ready):
    seen = []

    def execute(command, **options):
        seen.append(json.loads(options["input_bytes"]))
        options["consume"]('{"event":"step","step":1,"total":6}\n{"event":"step","step":1,"total":8}\n')
        options["consume_output"](b"\0\0\0\x18ftypisom")

    flash_ready.run_process = execute
    progress = Mock()

    MinimaxH3FlashBackendGateway(flash_ready).run(job(references=(still(0), still(72))), progress)

    assert seen[0]["flash"] is True and seen[0]["forwards"] == 6 and seen[0]["loras"] == []
    assert [keyframe["frame"] for keyframe in seen[0]["keyframes"]] == [0, 72]
    progress.assert_called_once_with(1, 6, 7)


def test_base_h3_tells_the_worker_that_it_is_not_flash(ready):
    seen = []

    def execute(command, **options):
        seen.append(json.loads(options["input_bytes"]))
        options["consume_output"](b"\0\0\0\x18ftypisom")

    ready.run_process = execute

    MinimaxH3BackendGateway(ready).run(job())

    assert seen[0]["flash"] is False and seen[0]["forwards"] == 8


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"fast_mode": True}, "H3 Flash has no Fast mode"),
        ({"audio": VideoAudio(b"private track", "private.wav")}, "H3 Flash takes no audio track"),
        ({"loras": (LoraUse("motion", 0.8),)}, "H3 Flash takes no LoRA"),
    ],
)
def test_flash_refuses_what_was_not_tried_on_its_weights(flash_ready, changes, reason):
    with pytest.raises(InvalidJob, match=reason):
        MinimaxH3FlashBackendGateway(flash_ready).run(job(**changes))
    flash_ready.run_process.assert_not_called()


@pytest.mark.parametrize("missing", ["flash.json", "model-1.safetensors"])
def test_flash_names_its_own_weights_when_its_pack_is_incomplete(flash_ready, missing):
    (Path(flash_ready.settings["model_dir"]) / FLASH_PACK / missing).unlink()

    with pytest.raises(InvalidJob, match="H3 Flash weights are incomplete"):
        MinimaxH3FlashBackendGateway(flash_ready).run(job())
    # The base pack is whole, so base H3 still runs.
    flash_ready.run_process = lambda command, **options: options["consume_output"](b"\0\0\0\x18ftypisom")
    assert MinimaxH3BackendGateway(flash_ready).run(job()).mp4


@pytest.mark.parametrize(
    "width,height,frames,measured",
    [(512, 288, 73, 59), (512, 512, 124, 170), (768, 448, 124, 247), (768, 448, 175, 388), (1024, 576, 124, 511)],
)
def test_the_flash_estimate_stays_near_the_runs_it_was_fitted_to(width, height, frames, measured):
    figure = estimate_clip(FLASH_CAPABILITIES.estimate, width, height, frames)

    # The figure is to the nearest 10 s, so it can stand 10 s from a run that the fit is 6 s from.
    assert figure.basis == "provisional" and figure.steps == 6
    assert figure.total_seconds == pytest.approx(measured, abs=10)


@pytest.mark.parametrize("text", ['{"hyperflow_gate":0.25}', "[]", "not json"])
def test_flash_weights_are_incomplete_without_the_facts_of_the_pack(flash_ready, text):
    (Path(flash_ready.settings["model_dir"]) / FLASH_PACK / "flash.json").write_text(text)

    with pytest.raises(InvalidJob, match="H3 Flash weights are incomplete"):
        MinimaxH3FlashBackendGateway(flash_ready).run(job())
