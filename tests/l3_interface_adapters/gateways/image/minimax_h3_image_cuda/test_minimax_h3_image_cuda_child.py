import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import minimax_h3_image_cuda_child as child


class FakeImage:
    width, height = 8, 6

    def save(self, buffer, format):
        buffer.write(b"png-bytes")


class FakePipe:
    def __init__(self):
        self.dtype = None
        self.device_map = None
        self.loads = []
        self.calls = []
        self.moved = []
        self.transformer = SimpleNamespace(parameters=lambda: [], buffers=lambda: [], to=self.moved.append)
        self.text_encoder = SimpleNamespace(parameters=lambda: [], buffers=lambda: [], to=lambda device: None)
        self.components = {"transformer": self.transformer, "text_encoder": self.text_encoder}

    def __call__(self, prompt, height, width, generator, output, callback_on_step_end=None):
        self.calls.append({"prompt": prompt, "height": height, "width": width, "output": output})
        if callback_on_step_end is not None:
            callback_on_step_end(self, 0, None, {})
        return [FakeImage()]

    def load_components(self, names=None, dtype=None, device_map=None):
        self.loads.append({"names": names, "dtype": dtype, "device_map": device_map})
        self.dtype = dtype
        self.device_map = device_map


class NoCallbackPipe:
    """A pipeline whose call takes no step hook."""

    def __init__(self):
        self.dtype = None
        self.device_map = None
        self.loads = []
        self.calls = []
        self.transformer = SimpleNamespace(parameters=lambda: [], buffers=lambda: [], to=lambda device: None)
        self.text_encoder = SimpleNamespace(parameters=lambda: [], buffers=lambda: [], to=lambda device: None)
        self.components = {"transformer": self.transformer, "text_encoder": self.text_encoder}

    def __call__(self, prompt, height, width, generator, output):
        self.calls.append({"prompt": prompt, "height": height, "width": width, "output": output})
        return [FakeImage()]

    def load_components(self, names=None, dtype=None, device_map=None):
        self.loads.append({"names": names, "dtype": dtype, "device_map": device_map})
        self.dtype = dtype
        self.device_map = device_map


def fake_torch(monkeypatch, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(torch, "float8_e4m3fn", "fp8", raising=False)
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(is_available=lambda: available, synchronize=Mock(), empty_cache=Mock()),
        raising=False,
    )
    monkeypatch.setattr(torch, "Generator", lambda: SimpleNamespace(manual_seed=lambda seed: seed), raising=False)
    monkeypatch.setitem(sys.modules, "torch", torch)


def fake_diffusers(monkeypatch, pipe):
    module = types.ModuleType("diffusers")
    monkeypatch.setattr(module, "ModularPipeline", SimpleNamespace(from_pretrained=lambda model: pipe), raising=False)
    monkeypatch.setitem(sys.modules, "diffusers", module)


def fake_torchao(monkeypatch, record, name="NVFP4DynamicActivationNVFP4WeightConfig"):
    quantize = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(quantize, "quantize_", lambda module, config: record.append((module, config)), raising=False)
    monkeypatch.setattr(quantize, "Float8WeightOnlyConfig", lambda: "fp8-config", raising=False)
    monkeypatch.setattr(quantize, "NVFP4WeightOnlyConfig", lambda: "nvfp4-wo-config", raising=False)
    config = types.ModuleType("torchao.prototype.mx_formats")
    monkeypatch.setattr(config, name, object, raising=False)
    monkeypatch.setattr(config, "NVFP4WeightOnlyConfig", lambda: "nvfp4-wo-config", raising=False)
    monkeypatch.setitem(sys.modules, "torchao", types.ModuleType("torchao"))
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantize)
    monkeypatch.setitem(sys.modules, "torchao.prototype", types.ModuleType("torchao.prototype"))
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats", config)


def test_supports_reads_the_pipeline_signature():
    assert child.supports(FakePipe(), "callback_on_step_end") is True
    assert child.supports(NoCallbackPipe(), "callback_on_step_end") is False
    assert child.supports(FakePipe(), "nothing") is False


class MappingOnly:
    """A pipeline that exposes its parts only as a mapping."""

    def __init__(self, part):
        self.components = {"transformer": part}


def test_component_falls_back_to_the_mapping():
    pipe = MappingOnly(object())
    assert child.component(pipe, "transformer") is pipe.components["transformer"]


def test_materialize_clones_once_and_keeps_shared_storage_shared():
    class Tensor:
        def __init__(self, name):
            self.name, self.clones = name, 0

        def clone(self):
            self.clones += 1
            return Tensor(self.name + "-clone")

        def data_ptr(self):
            return id(self)

    shared = Tensor("tied")
    holder_a, holder_b = SimpleNamespace(data=shared), SimpleNamespace(data=shared)
    module = SimpleNamespace(parameters=lambda: [holder_a, holder_b], buffers=lambda: [])
    child.materialize(module)
    assert shared.clones == 1 and holder_a.data is holder_b.data


def test_load_packs_the_encoder_first_then_the_transformer(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    assert child.load("me/pack", "nvfp4") is pipe
    assert next(item["names"] for item in pipe.loads) == ["text_encoder"]
    assert recorded[0] == (pipe.text_encoder, "nvfp4-wo-config")
    assert recorded[1][0] is pipe.transformer
    assert "as nvfp4" in capsys.readouterr().err


def test_the_transformer_moves_straight_to_the_device_without_a_host_copy(monkeypatch):
    """62 GiB of host copy beside 62 GiB of device copy is more than this machine holds.

    Measured 2026-11-14: the materialized order died with CUDA_ERROR_OUT_OF_MEMORY at
    110 GiB resident. This pins the order that fits.
    """
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    child.load("me/pack", "nvfp4")

    assert [item["names"] for item in pipe.loads][1] == ["transformer", "vae", "processor", "tokenizer", "scheduler"]
    assert pipe.loads[1]["device_map"] == "cuda"
    assert pipe.moved == []


def test_load_can_ask_for_fp8_or_bf16(monkeypatch):
    fake_torch(monkeypatch)
    fake_diffusers(monkeypatch, FakePipe())
    recorded = []
    fake_torchao(monkeypatch, recorded)
    assert child.load("me/pack", "fp8") is not None
    assert recorded[1][1] == "fp8-config"


def test_bf16_loads_everything_at_once_and_quantizes_nothing(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)
    child.load("me/pack", "bf16")
    assert len(pipe.loads) == 1 and pipe.loads[0]["names"] is None
    assert pipe.loads[0]["device_map"] == "cuda"
    assert recorded == []


def test_an_unknown_quantizer_stops_the_child(monkeypatch):
    fake_torch(monkeypatch)
    fake_diffusers(monkeypatch, FakePipe())
    with pytest.raises(SystemExit, match="nvfp4, fp8 or bf16"):
        child.load("me/pack", "int4")


def test_a_run_reports_steps_and_returns_png_bytes(monkeypatch, capsys):
    fake_torch(monkeypatch)

    reply = child.run(FakePipe(), {"prompt": "a fox", "height": 512, "width": 768, "steps": 6, "seed": 9})

    assert reply["png_base64"] == "cG5nLWJ5dGVz"
    assert (reply["width"], reply["height"], reply["steps"]) == (8, 6, 1)
    assert "step 1/6" in capsys.readouterr().err


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_torch(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_torch(monkeypatch)
    fake_diffusers(monkeypatch, NoCallbackPipe())
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "bf16"])
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"prompt": "a fox", "height": 8, "width": 8, "steps": 6, "seed": 1}),
                    "",
                    json.dumps({"prompt": "no steps"}),
                ]
            )
        ),
    )

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "png_base64" in lines[0]
    assert lines[1]["error"].startswith("KeyError")


class ExplodingCall:
    @property
    def __call__(self):
        raise TypeError("no signature here")


def test_supports_answers_no_when_the_call_cannot_be_inspected():
    assert child.supports(ExplodingCall(), "callback_on_step_end") is False


def test_the_script_enters_through_its_main_guard(monkeypatch):
    """The `__main__` guard is the path uv runs, so prove it answers."""
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")

    assert exited.value.code == 0
