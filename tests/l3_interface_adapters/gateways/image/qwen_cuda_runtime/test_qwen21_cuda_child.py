import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.image.qwen_cuda_runtime import qwen21_cuda_child as child


class FakeImage:
    width, height = 8, 6

    def __init__(self):
        self.saved = None

    def save(self, buffer, format):
        self.saved = format
        buffer.write(b"png-bytes")


class EmptyModule:
    def parameters(self):
        return []

    def buffers(self):
        return []


class FakePipe:
    def __init__(self):
        self.device = None
        self.calls = []
        self.transformer = EmptyModule()
        self.text_encoder = EmptyModule()
        self.vae = EmptyModule()

    def to(self, device):
        self.device = device
        return self

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["callback_on_step_end"](self, 0, None, {})
        return SimpleNamespace(images=[FakeImage()])


def fake_torch(monkeypatch, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(is_available=lambda: available, synchronize=Mock(), empty_cache=Mock()),
        raising=False,
    )
    monkeypatch.setattr(
        torch, "Generator", lambda device: SimpleNamespace(seed=None, manual_seed=lambda seed: seed), raising=False
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def fake_diffusers(monkeypatch, pipe):
    module = types.ModuleType("diffusers")
    monkeypatch.setattr(
        module, "QwenImage21Pipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "diffusers", module)


def fake_torchao(monkeypatch, record):
    quantize = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(
        quantize, "quantize_", lambda model, config: record.append(("quantize", model, config)), raising=False
    )

    class Config:
        pass

    config = types.ModuleType("torchao.prototype.mx_formats")
    monkeypatch.setattr(config, "NVFP4DynamicActivationNVFP4WeightConfig", Config, raising=False)
    package = types.ModuleType("torchao")
    prototype = types.ModuleType("torchao.prototype")
    monkeypatch.setitem(sys.modules, "torchao", package)
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantize)
    monkeypatch.setitem(sys.modules, "torchao.prototype", prototype)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats", config)


def test_load_quantizes_the_transformer_and_reports_ready(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    loaded = child.load("me/pack", "nvfp4")

    assert loaded is pipe
    assert pipe.device == "cuda"
    assert recorded[0][1] is pipe.transformer
    assert "loaded me/pack as nvfp4" in capsys.readouterr().err


def test_load_keeps_bf16_when_asked(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    assert child.load("me/pack", "bf16") is pipe
    assert recorded == []


def test_an_unknown_quantizer_stops_the_child(monkeypatch):
    fake_torch(monkeypatch)
    fake_diffusers(monkeypatch, FakePipe())

    with pytest.raises(SystemExit, match="nvfp4 or bf16"):
        child.load("me/pack", "int8")


def test_a_run_reports_steps_and_returns_png_bytes(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()

    reply = child.run(pipe, {"prompt": "a fox", "height": 512, "width": 768, "steps": 3, "seed": 9, "guidance": 2.5})

    assert reply["width"] == 8 and reply["height"] == 6 and reply["steps"] == 3
    assert reply["png_base64"] == "cG5nLWJ5dGVz"
    call = pipe.calls[0]
    assert (call["prompt"], call["height"], call["width"], call["num_inference_steps"]) == ("a fox", 512, 768, 3)
    assert call["negative_prompt"] is None and call["true_cfg_scale"] == 2.5
    assert "step 1/3" in capsys.readouterr().err


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_torch(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "bf16"])
    jobs = [
        json.dumps({"prompt": "a fox", "height": 8, "width": 8, "steps": 1, "seed": 1}),
        "",
        json.dumps({"prompt": "no steps"}),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs)))

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "png_base64" in lines[0]
    assert lines[1]["error"].startswith("KeyError")


class FakeTensor:
    def __init__(self, name):
        self.name = name
        self.clones = 0
        self.device = "cpu"

    def clone(self):
        self.clones += 1
        return FakeTensor(self.name + "-clone")

    def to(self, device):
        self.device = device
        return self

    def data_ptr(self):
        return id(self)


class Holder:
    def __init__(self, tensor):
        self.data = tensor


class Module:
    def __init__(self, parameters, buffers=()):
        self._parameters = list(parameters)
        self._buffers = list(buffers)

    def parameters(self):
        return self._parameters

    def buffers(self):
        return self._buffers


def test_move_by_way_of_memory_clones_once_and_keeps_shared_storage_shared():
    shared = FakeTensor("tied")
    alone = FakeTensor("alone")
    buffer = FakeTensor("rotary")
    module = Module([Holder(shared), Holder(shared), Holder(alone)], [Holder(buffer)])

    child.move_by_way_of_memory(module, "cuda")

    assert shared.clones == 1 and alone.clones == 1 and buffer.clones == 1
    first, second, third = module.parameters()
    assert first.data is second.data
    assert first.data is not third.data
    assert module.buffers()[0].data.name == "rotary-clone"
    assert first.data.device == "cuda"


def test_the_script_enters_through_its_main_guard(monkeypatch):
    """The `__main__` guard is the path uv runs, so prove it answers."""
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")

    assert exited.value.code == 0


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


def test_an_edit_run_sends_every_reference_as_an_image(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    encoded = png()

    reply = child.run(
        pipe,
        {
            "mode": "edit",
            "prompt": "make it night",
            "output_resolution": 1024,
            "steps": 2,
            "seed": 4,
            "guidance": 1.0,
            "references": [encoded, encoded],
        },
    )

    assert reply["steps"] == 2 and reply["png_base64"] == "cG5nLWJ5dGVz"
    call = pipe.calls[0]
    assert [image.size for image in call["image"]] == [(4, 3), (4, 3)]
    assert call["true_cfg_scale"] == 1.0 and call["output_resolution"] == 1024
    assert "height" not in call and "width" not in call
    assert "step 1/2" in capsys.readouterr().err
