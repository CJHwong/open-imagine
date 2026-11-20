import base64
import io
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda import minimax_h3_cuda_child as child


def fake_module(name: str, **attributes) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def png(color=(255, 0, 0)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class Linear:
    def __init__(self, dtype="bfloat16"):
        self.weight = SimpleNamespace(dtype=dtype)


class Module:
    """A component: named submodules, no weights, and a record of the hooks it was given."""

    def __init__(self, layers=None):
        self.layers = layers or {}
        self.hooks = []
        self.lm_head = "head"
        self.model = SimpleNamespace(language_model=SimpleNamespace(layers=list(range(64))))

    def named_modules(self):
        return list(self.layers.items())

    def parameters(self):
        return []

    def buffers(self):
        return []

    def register_forward_pre_hook(self, hook):
        self.hooks.append(hook)


class FakePipe:
    text_encoder_layer = 50
    audio_sampling_rate = 32000
    component_names = (
        "image_processor",
        "text_encoder",
        "tokenizer",
        "vae",
        "audio_vae",
        "transformer_ref",
        "transformer",
    )

    def __init__(self):
        self.components = {}
        self.loads = []
        self.calls = []

    def load_components(self, names, dtype, device_map):
        self.loads.append(tuple(names))
        for name in names:
            linears = {"block.linear": Linear(), "visual.proj": Linear(), "norm": Linear("float32")}
            self.components[name] = Module(linears if name in child.QUANTIZED else None)

    def __getattr__(self, name):
        if name in self.__dict__.get("components", {}):
            return self.components[name]
        raise AttributeError(name)

    def __call__(self, **arguments):
        self.calls.append(arguments)
        for _ in range(arguments["num_inference_steps"] - 1):
            for hook in self.components["transformer"].hooks:
                hook()
        frames = [Image.new("RGB", (arguments["width"], arguments["height"])) for _ in range(arguments["num_frames"])]
        return {"videos": [frames], "audio": ["generated sound"], "sampling_rate": 32000}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Every engine package the child imports, faked, and a record of what each was asked."""
    record = SimpleNamespace(quantized=[], encoded=[], downloads=[], pipe=FakePipe(), hub=tmp_path / "hub")

    torch = fake_module(
        "torch",
        bfloat16="bfloat16",
        nn=SimpleNamespace(Linear=Linear, Identity=lambda: "identity"),
        cuda=SimpleNamespace(is_available=lambda: True, synchronize=Mock(), empty_cache=Mock()),
        Generator=lambda: SimpleNamespace(manual_seed=lambda seed: ("generator", seed)),
        from_numpy=lambda array: ("tensor", array.shape),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    mx = fake_module("torchao.prototype.mx_formats", NVFP4DynamicActivationNVFP4WeightConfig=lambda: "nvfp4")
    quantization = fake_module(
        "torchao.quantization", quantize_=lambda layer, config: record.quantized.append((layer, config))
    )
    for name, module in (
        ("torchao", types.ModuleType("torchao")),
        ("torchao.prototype", types.ModuleType("torchao.prototype")),
        ("torchao.prototype.mx_formats", mx),
        ("torchao.quantization", quantization),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    diffusers = fake_module("diffusers", ModularPipeline=SimpleNamespace(from_pretrained=lambda path: record.pipe))
    references = fake_module(
        "diffusers.modular_pipelines.minimax_h3",
        MiniMaxH3ImageReference=lambda image: ("picture", image.size),
        MiniMaxH3AudioReference=lambda audio, sample_rate: ("track", audio, sample_rate),
    )

    def encode_video(frames, fps, output_path, audio, audio_sample_rate):
        record.encoded.append((len(frames), fps, audio, audio_sample_rate))
        Path(output_path).write_bytes(b"mp4")

    exporter = fake_module("diffusers.utils.export_utils", encode_video=encode_video)
    for name, module in (
        ("diffusers", diffusers),
        ("diffusers.modular_pipelines", types.ModuleType("diffusers.modular_pipelines")),
        ("diffusers.modular_pipelines.minimax_h3", references),
        ("diffusers.utils", types.ModuleType("diffusers.utils")),
        ("diffusers.utils.export_utils", exporter),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    def snapshot_download(model, revision, allow_patterns):
        record.downloads.append((model, revision, tuple(allow_patterns)))
        return "/downloaded"

    hub = fake_module(
        "huggingface_hub",
        constants=SimpleNamespace(HF_HUB_CACHE=str(record.hub)),
        snapshot_download=snapshot_download,
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setattr(child, "move_by_way_of_memory", lambda module, device="cuda": None)
    return record


def fake_av(monkeypatch, planes):
    """PyAV with one decoded frame, whose resampled planes are `planes`, then the flush."""

    class Container:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def decode(self, audio):
            return ["frame"] if planes is not None else []

    class Resampler:
        def __init__(self, format, layout, rate):
            self.settings = (format, layout, rate)

        def resample(self, frame):
            if frame is None or planes is None:
                return []
            return [SimpleNamespace(to_ndarray=lambda: planes)]

    monkeypatch.setitem(sys.modules, "av", fake_module("av", open=Container, AudioResampler=Resampler))


def test_prepare_environment_sets_ptxas_only_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    monkeypatch.setattr(child, "PTXAS", tmp_path / "absent")
    child.prepare_environment()
    assert "TRITON_PTXAS_PATH" not in child.os.environ
    assert child.os.environ["HF_HUB_DISABLE_XET"] == "1"
    (tmp_path / "ptxas").write_text("")
    monkeypatch.setattr(child, "PTXAS", tmp_path / "ptxas")
    child.prepare_environment()
    assert child.os.environ["TRITON_PTXAS_PATH"] == str(tmp_path / "ptxas")


def test_the_pinned_snapshot_is_used_from_the_cache_without_the_hub(world):
    cached = world.hub / "models--MiniMaxAI--MiniMax-H3" / "snapshots" / "abc"
    (cached / "transformer").mkdir(parents=True)
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc") == "/downloaded"
    assert world.downloads[0][:2] == ("MiniMaxAI/MiniMax-H3", "abc")
    assert "transformer_ref/*" in world.downloads[0][2]
    (cached / "transformer_ref").mkdir()
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc") == str(cached)
    assert len(world.downloads) == 1


def test_a_local_folder_is_read_as_it_is(world, tmp_path):
    assert child.snapshot(str(tmp_path), "abc") == str(tmp_path)
    assert world.downloads == []


def test_component_reads_an_attribute_then_the_mapping():
    assert child.component(SimpleNamespace(vae="vae", components={}), "vae") == "vae"
    assert child.component(SimpleNamespace(components={"vae": "mapped"}), "vae") == "mapped"


def test_move_by_way_of_memory_lands_a_group_once_and_skips_what_is_there():
    class Tensor:
        def __init__(self, device="cpu"):
            self.device = SimpleNamespace(type=device)
            self.clones = 0

        def clone(self):
            self.clones += 1
            return self

        def to(self, device):
            return Tensor(device)

        def data_ptr(self):
            return id(self)

    shared, landed = Tensor(), Tensor("cuda")
    first, second, third = (SimpleNamespace(data=shared), SimpleNamespace(data=shared), SimpleNamespace(data=landed))
    module = SimpleNamespace(parameters=lambda: [first, second], buffers=lambda: [third])

    child.move_by_way_of_memory(module)

    assert shared.clones == 1
    assert first.data is second.data and first.data.device.type == "cuda"
    assert third.data is landed


def test_land_in_nvfp4_quantizes_bf16_linears_and_keeps_the_named_ones(world):
    module = Module({"block.linear": Linear(), "visual.proj": Linear(), "norm": Linear("float32"), "act": object()})
    child.land_in_nvfp4(module, kept=("visual",))
    assert world.quantized == [(module.layers["block.linear"], "nvfp4")]


def test_load_takes_one_large_component_at_a_time_and_hooks_both_transformers(world, capsys):
    pipe = child.load("MiniMaxAI/MiniMax-H3", "/local")

    assert pipe is world.pipe
    assert pipe.loads == [
        ("image_processor", "tokenizer", "vae", "audio_vae"),
        ("text_encoder",),
        ("transformer",),
        ("transformer_ref",),
    ]
    encoder = pipe.components["text_encoder"]
    assert len(encoder.model.language_model.layers) == 51 and encoder.lm_head == "identity"
    assert all(len(pipe.components[name].hooks) == 1 for name in child.TRANSFORMERS)
    # The encoder keeps its vision tower in bf16; the transformers have none to keep.
    quantized = [layer for layer, _ in world.quantized]
    assert encoder.layers["visual.proj"] not in quantized and encoder.layers["block.linear"] in quantized
    assert all(pipe.components[name].layers["visual.proj"] in quantized for name in child.TRANSFORMERS)
    assert {config for _, config in world.quantized} == {"nvfp4"}
    assert "loaded MiniMaxAI/MiniMax-H3" in capsys.readouterr().err


def test_text_runs_the_pipeline_and_reports_each_transformer_call_as_a_step(world, capsys):
    pipe = child.load("m", "/local")
    reply = child.run(pipe, {"prompt": "a fox", "width": 64, "height": 32, "frames": 124, "steps": 5, "seed": 3})

    call = pipe.calls[-1]
    assert (call["num_inference_steps"], call["num_frames"], call["generator"]) == (5, 124, ("generator", 3))
    assert "image" not in call and "references" not in call
    assert (reply["width"], reply["height"], reply["frames"], reply["steps"]) == (64, 32, 124, 4)
    assert base64.b64decode(reply["mp4"]) == b"mp4"
    assert world.encoded[-1] == (124, 24, "generated sound", 32000)
    err = capsys.readouterr().err
    assert "step 0/0" in err and "step 4/4" in err


def test_a_silent_clip_writes_no_sound(world):
    pipe = child.load("m", "/local")
    child.run(
        pipe, {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "seed": 0, "include_audio": False}
    )
    assert world.encoded[-1][2:] == (None, None)


def test_keyframes_go_in_as_the_first_and_last_image(world):
    pipe = child.load("m", "/local")
    child.run(pipe, {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "seed": 0, "first": png()})
    assert pipe.calls[-1]["image"].size == (8, 8) and "last_image" not in pipe.calls[-1]
    child.run(pipe, {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "seed": 0, "last": png()})
    assert pipe.calls[-1]["last_image"].size == (8, 8) and "image" not in pipe.calls[-1]


def test_a_track_runs_the_reference_workflow_and_the_clip_keeps_the_track(world, monkeypatch):
    planes = np.ones((2, 32000 * 10), dtype=np.float32)
    fake_av(monkeypatch, planes)
    pipe = child.load("m", "/local")
    job = {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "seed": 0}
    child.run(pipe, {**job, "pictures": [png(), png((0, 0, 255))], "audio": base64.b64encode(b"wav").decode()})

    references = pipe.calls[-1]["references"]
    assert references[:2] == [("picture", (8, 8)), ("picture", (8, 8))]
    assert references[2][0] == "track" and references[2][2] == 32000
    # The track is cut to the clip: 124 frames at 24 fps.
    assert world.encoded[-1][2] == ("tensor", (2, round(124 / 24 * 32000)))


def test_a_track_with_no_sound_is_refused(world, monkeypatch):
    fake_av(monkeypatch, None)
    with pytest.raises(ValueError, match="holds no sound"):
        child.decode_track(base64.b64encode(b"wav").decode(), 32000)


def test_main_answers_each_job_and_turns_a_failure_into_an_error_reply(world, monkeypatch, capsys):
    jobs = [
        json.dumps({"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "seed": 0, "request_id": "a"}),
        "",
        json.dumps({"request_id": "b"}),
    ]
    monkeypatch.setattr(sys, "argv", ["child", "--model", "m", "--revision", "r"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs) + "\n"))
    monkeypatch.setattr(child, "snapshot", lambda model, revision: "/local")

    assert child.main() == 0

    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert replies[0]["request_id"] == "a" and "mp4" in replies[0]
    assert replies[1]["request_id"] == "b" and replies[1]["error"].startswith("KeyError")


def test_main_refuses_a_host_without_cuda(world, monkeypatch):
    sys.modules["torch"].cuda.is_available = lambda: False
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0
