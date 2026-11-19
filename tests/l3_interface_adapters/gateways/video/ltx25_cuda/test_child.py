import io
import json
import pathlib
import sys
import tracemalloc
import types
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.video.ltx25_cuda import ltx25_cuda_child as child


class EmptyModule:
    def __init__(self):
        self.compiled = []

    def parameters(self):
        return []

    def compile_repeated_blocks(self, **options):
        self.compiled.append(options)

    def buffers(self):
        return []


class FakePipe:
    def __init__(self):
        self.transformer: object = EmptyModule()
        self.text_encoder = EmptyModule()
        self.connectors = EmptyModule()
        self.vae = EmptyModule()
        self.vocoder = SimpleNamespace(config=SimpleNamespace(output_sampling_rate=48000))
        self.device = None
        self.calls = []
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "connectors": self.connectors,
            "vae": self.vae,
            "scheduler": SimpleNamespace(),
        }

    def to(self, device):
        self.device = device
        return self

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        callback = kwargs.get("callback_on_step_end")
        if callback is not None:
            for index in range(child.DISTILLED_STEPS):
                callback(self, index, None, {})
        return ([[np.zeros((2, 2, 3), dtype=np.uint8)]], np.zeros((1, 2, 2000)), None, None)


def fake_world(monkeypatch, pipe, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(is_available=lambda: available, synchronize=Mock(), empty_cache=Mock()),
        raising=False,
    )
    monkeypatch.setattr(
        torch, "Generator", lambda device=None: SimpleNamespace(manual_seed=lambda seed: seed), raising=False
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    diffusers = types.ModuleType("diffusers")

    class Condition:
        def __init__(self, frames, index, strength):
            self.frames, self.index, self.strength = frames, index, strength

    ltx2 = types.ModuleType("diffusers.pipelines.ltx2")
    monkeypatch.setattr(ltx2, "LTX2VideoCondition", Condition, raising=False)
    monkeypatch.setitem(sys.modules, "diffusers.pipelines", types.ModuleType("diffusers.pipelines"))
    monkeypatch.setitem(sys.modules, "diffusers.pipelines.ltx2", ltx2)
    monkeypatch.setattr(
        diffusers, "LTX2DFRPipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "diffusers", diffusers)

    encoder = types.ModuleType("diffusers.utils.export_utils")

    def encode_video(frames, rate, output_path, *, audio, audio_sample_rate):
        pathlib.Path(output_path).write_bytes(b"mp4-bytes")

    monkeypatch.setattr(encoder, "encode_video", encode_video, raising=False)
    monkeypatch.setitem(sys.modules, "diffusers.utils", types.ModuleType("diffusers.utils"))
    monkeypatch.setitem(sys.modules, "diffusers.utils.export_utils", encoder)


def test_prepare_environment_sets_ptxas_only_when_present(monkeypatch, tmp_path):
    ptxas = tmp_path / "ptxas"
    ptxas.write_text("")
    monkeypatch.setattr(child, "PTXAS", ptxas)
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    child.prepare_environment()
    assert child.os.environ["TRITON_PTXAS_PATH"] == str(ptxas)
    assert child.os.environ["HF_HUB_DISABLE_XET"] == "1"

    monkeypatch.setattr(child, "PTXAS", tmp_path / "absent")
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    child.prepare_environment()
    assert "TRITON_PTXAS_PATH" not in child.os.environ


def test_move_by_way_of_memory_clones_a_group_once_and_lands_it():
    """One round trip per group of aliased weights, and the aliases keep sharing it."""

    class Tensor:
        def __init__(self):
            self.clones = 0
            self.device = None

        def clone(self):
            self.clones += 1
            return Tensor()

        def to(self, device):
            self.device = device
            return self

        def data_ptr(self):
            return id(self)

    shared = Tensor()
    a, b = SimpleNamespace(data=shared), SimpleNamespace(data=shared)

    child.move_by_way_of_memory(SimpleNamespace(parameters=lambda: [a, b], buffers=lambda: []))

    assert shared.clones == 1
    assert a.data is b.data
    assert a.data.device == "cuda"


def test_load_materializes_and_moves_to_the_device(monkeypatch, capsys):
    pipe = FakePipe()
    fake_world(monkeypatch, pipe)
    assert child.load("me/pack") is pipe
    assert pipe.device == "cuda"
    assert "loaded me/pack" in capsys.readouterr().err


def test_load_compiles_the_repeated_transformer_block_once(monkeypatch):
    """Eager, the transformer took 60.4 s of a 768 x 768, 97-frame clip; compiled, 43.0 s."""
    pipe = FakePipe()
    transformer = EmptyModule()
    pipe.transformer = transformer
    fake_world(monkeypatch, pipe)

    child.load("me/pack")

    assert transformer.compiled == [{"fullgraph": False, "dynamic": False}]


def test_load_sends_each_weight_through_memory_first(monkeypatch):
    log = []

    class Tensor:
        def clone(self):
            log.append("clone")
            return self

        def to(self, device):
            log.append(f"to {device}")
            return self

        def data_ptr(self):
            return 1

    pipe = FakePipe()
    moved = SimpleNamespace(
        parameters=lambda: [SimpleNamespace(data=Tensor())],
        buffers=lambda: [],
        compile_repeated_blocks=lambda **options: None,
    )
    pipe.transformer = moved
    pipe.components["transformer"] = moved
    fake_world(monkeypatch, pipe)

    child.load("me/pack")

    assert log == ["clone", "to cuda"]


def test_a_run_reports_steps_and_returns_an_mp4(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe())
    reply = child.run(
        FakePipe(), {"prompt": "a fox", "width": 768, "height": 512, "frames": 97, "frame_rate": 24, "seed": 1}
    )
    assert reply["mp4"] == "bXA0LWJ5dGVz"
    assert (reply["width"], reply["height"], reply["frames"]) == (768, 512, 1)
    assert reply["steps"] == child.DISTILLED_STEPS


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe(), available=False)
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe())
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"prompt": "a fox", "width": 8, "height": 8, "frames": 2, "frame_rate": 24, "seed": 1}),
                    "",
                    json.dumps({"seed": 1}),
                ]
            )
        ),
    )
    assert child.main() == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "mp4" in lines[0]
    assert lines[1]["error"].startswith("KeyError")
    # Each job hands its cached memory back, the failed one too: a long clip keeps about
    # 21 GiB in PyTorch's cache, and the next clip starts that much closer to the limit.
    assert sys.modules["torch"].cuda.empty_cache.call_count == 2


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0


def test_an_enhanced_run_passes_the_flag_and_a_flat_frame_list(monkeypatch):
    class Enhanced(FakePipe):
        def __call__(self, **kwargs):
            self.calls.append(kwargs)
            kwargs["callback_on_step_end"](self, 1, None, {})
            return ([np.zeros((2, 2, 3), dtype=np.uint8)], np.zeros((1, 2, 2000)), None, None)

    pipe = Enhanced()
    fake_world(monkeypatch, pipe)
    reply = child.run(
        pipe, {"prompt": "a fox", "width": 8, "height": 8, "frames": 1, "frame_rate": 24, "seed": 1, "enhance": True}
    )
    assert pipe.calls[0]["enable_prompt_enhancement"] is True
    assert reply["frames"] == 1


def test_load_skips_a_component_the_pipeline_does_not_carry(monkeypatch):
    pipe = FakePipe()
    del pipe.connectors
    fake_world(monkeypatch, pipe)
    assert child.load("me/pack") is pipe
    assert pipe.device == "cuda"


def test_unpack_handles_an_array_and_a_nested_list():
    import numpy as np

    array = np.zeros((1, 3, 4, 4, 3), dtype=np.uint8)
    assert child.unpack(array).shape == (3, 4, 4, 3)
    assert len(child.unpack([np.zeros((2, 2, 3))])) == 1
    nested = [[np.zeros((2, 2, 3)), np.zeros((2, 2, 3))]]
    assert len(child.unpack(nested)) == 2
    assert len(child.unpack(np.zeros((3, 4, 4, 3), dtype=np.uint8))) == 3


def test_local_snapshot_prefers_the_cached_directory(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pack"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")
    (root / "snapshots" / "abc123").mkdir(parents=True)

    assert child.local_snapshot("me/pack") == str(root / "snapshots" / "abc123")


def test_local_snapshot_keeps_an_id_that_is_not_cached(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/pack") == "me/pack"


def test_local_snapshot_keeps_an_id_whose_snapshot_is_gone(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pack"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")

    assert child.local_snapshot("me/pack") == "me/pack"


def png():
    import base64

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_a_keyframe_becomes_a_pipeline_condition(monkeypatch):
    pipe = FakePipe()
    fake_world(monkeypatch, pipe)

    child.run(
        pipe,
        {
            "prompt": "a fox",
            "width": 768,
            "height": 512,
            "frames": 97,
            "frame_rate": 24,
            "seed": 1,
            "references": [{"png_base64": png(), "frame_index": 0, "strength": 0.8}],
        },
    )

    condition = pipe.calls[-1]["conditions"][0]
    assert (condition.index, condition.strength) == (0, 0.8)
    assert (condition.frames.size, condition.frames.mode) == ((4, 3), "RGB")


def test_a_run_without_keyframes_sends_no_conditions(monkeypatch):
    pipe = FakePipe()
    fake_world(monkeypatch, pipe)

    child.run(pipe, {"prompt": "a fox", "width": 768, "height": 512, "frames": 97, "frame_rate": 24, "seed": 1})

    assert "conditions" not in pipe.calls[-1]


@pytest.mark.parametrize("include_audio", [True, False])
def test_a_controller_job_preserves_audio_through_serialization_and_encoding(monkeypatch, include_audio):
    from studio.l3_interface_adapters.controllers.video_controller import video_job
    from studio.l3_interface_adapters.gateways.video.ltx25_cuda.capabilities import ltx25_cuda_capabilities
    from studio.l3_interface_adapters.gateways.video.ltx25_cuda.ltx25_cuda_backend_gateway import clip_payload

    pipe = FakePipe()
    fake_world(monkeypatch, pipe)
    encoder = Mock(return_value=b"mp4")
    monkeypatch.setattr(child, "encode", encoder)
    request = video_job(
        {
            "prompt": "The river is quiet.",
            "width": 768,
            "height": 512,
            "num_frames": 97,
            "frame_rate": 24,
            "seed": 19,
            "include_audio": include_audio,
        },
        ltx25_cuda_capabilities(),
    )

    child.run(pipe, json.loads(json.dumps(clip_payload(request))))

    _, rate, audio, sample_rate = encoder.call_args.args
    assert rate == 24
    if include_audio:
        np.testing.assert_array_equal(audio, np.zeros((2, 2000)))
        assert sample_rate == 48000
    else:
        assert audio is None
        assert sample_rate is None


def test_missing_generated_audio_fails_instead_of_returning_a_silent_clip(monkeypatch):
    pipe = FakePipe()
    fake_world(monkeypatch, pipe)
    monkeypatch.setattr(FakePipe, "__call__", lambda *args, **kwargs: ([np.zeros((2, 2, 3))], None, None, None))

    with pytest.raises(ValueError, match="returned no audio"):
        child.run(pipe, {"prompt": "a fox", "width": 8, "height": 8, "seed": 1})


@pytest.mark.parametrize("failure", [False, True])
def test_encode_forwards_both_streams_and_removes_scratch_files(monkeypatch, tmp_path, failure):
    module = types.ModuleType("diffusers.utils.export_utils")
    calls = []

    def encode_video(frames, rate, output_path, *, audio, audio_sample_rate):
        calls.append((np.concatenate(list(frames)), rate, pathlib.Path(output_path), audio, audio_sample_rate))
        pathlib.Path(output_path).write_bytes(b"encoded")
        if failure:
            raise RuntimeError("encoder failed")

    monkeypatch.setattr(module, "encode_video", encode_video, raising=False)
    monkeypatch.setitem(sys.modules, "diffusers.utils", types.ModuleType("diffusers.utils"))
    monkeypatch.setitem(sys.modules, "diffusers.utils.export_utils", module)
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(from_numpy=lambda frame: frame))
    monkeypatch.setenv("SPEECH_GEN_SCRATCH", str(tmp_path))
    frames = np.zeros((3, 8, 8, 3), dtype=np.float32)
    audio = np.zeros((2, 6000), dtype=np.float32)

    if failure:
        with pytest.raises(RuntimeError, match="encoder failed"):
            child.encode(frames, 24, audio, 48000)
    else:
        assert child.encode(frames, 24, audio, 48000) == b"encoded"

    actual_frames, rate, target, actual_audio, audio_sample_rate = calls[0]
    np.testing.assert_array_equal(actual_frames, frames)
    assert (rate, audio_sample_rate) == (24, 48000)
    assert actual_audio is audio
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("values", [[0.0, 0.5, 1.0], [0, 1, 0]])
def test_video_chunks_keep_exporter_rounding_without_clip_sized_copies(monkeypatch, values):
    frames = np.tile(np.asarray(values), (97, 64, 64, 1))
    expected = (frames * 255).round().astype("uint8")
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(from_numpy=lambda frame: frame))
    tracemalloc.start()
    chunks = child.video_chunks(frames)
    assert not isinstance(chunks, np.ndarray)
    for index, frame in enumerate(chunks):
        np.testing.assert_array_equal(frame, expected[index : index + 1])
        assert frame.nbytes == expected[0].nbytes
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < frames.nbytes // 2


@pytest.mark.parametrize("value", [-0.1, 1.1, float("nan")])
def test_video_chunks_leave_exporter_fallback_unchanged(value):
    frames = np.array([[[[value, 0.0, 1.0]]]])
    assert child.video_chunks(frames) is frames


def test_video_chunks_leave_empty_input_to_exporter():
    frames = np.empty((0, 8, 8, 3))
    assert child.video_chunks(frames) is frames
