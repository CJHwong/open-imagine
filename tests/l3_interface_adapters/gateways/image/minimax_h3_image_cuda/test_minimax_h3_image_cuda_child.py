import io
import json
import sys
import types
import weakref
from contextlib import nullcontext
from pathlib import Path
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
        self.vae = SimpleNamespace(parameters=lambda: [], buffers=lambda: [])
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "vae": self.vae,
        }

    def __call__(
        self, prompt, height, width, generator, output, min_generation_area, callback_on_step_end=None, image=None
    ):
        self.calls.append(
            {
                "prompt": prompt,
                "height": height,
                "width": width,
                "output": output,
                "image": image,
                "min_generation_area": min_generation_area,
            }
        )
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
        self.vae = SimpleNamespace(parameters=lambda: [], buffers=lambda: [])
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "vae": self.vae,
        }

    def __call__(self, prompt, height, width, generator, output, min_generation_area):
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
    monkeypatch.setattr(
        torch, "accelerator", SimpleNamespace(memory=SimpleNamespace(empty_host_cache=Mock())), raising=False
    )
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


def test_the_transformer_lands_on_the_host_first(monkeypatch):
    """The straight mapping to the device measured 0.19 GB/s; through ordinary memory 59.57.

    Loading the transformer with `device_map="cuda"` copies from the safetensors mapping
    and measured 511.7 s for 68.7 GB. The host first, then a clone and a move per tensor,
    is the order this pins.
    """
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    child.load("me/pack", "nvfp4")

    assert [item["names"] for item in pipe.loads][1] == ["transformer", "vae", "processor", "tokenizer", "scheduler"]
    assert pipe.loads[1]["device_map"] == "cpu"


class FakeTensor:
    """A weight's data, recording which route it took to the device."""

    def __init__(self, name, log):
        self.name = name
        self.log = log

    def data_ptr(self):
        return hash(self.name)

    def clone(self):
        self.log.append(("clone", self.name))
        return FakeTensor(self.name, self.log)

    def to(self, device):
        self.log.append(("to", self.name, device))
        return FakeTensor(self.name, self.log)


class FakeModule:
    def __init__(self, tensors):
        self.holders = [SimpleNamespace(data=tensor) for tensor in tensors]

    def parameters(self):
        return self.holders

    def buffers(self):
        return []


def test_each_weight_is_cloned_before_it_reaches_the_device():
    log = []
    module = FakeModule([FakeTensor("w1", log)])

    child.move_by_way_of_memory(module, "cuda")

    assert log == [("clone", "w1"), ("to", "w1", "cuda")]


def test_aliased_weights_move_once_and_stay_shared():
    log = []
    shared = FakeTensor("w", log)
    module = FakeModule([shared, shared])

    child.move_by_way_of_memory(module, "cuda")

    assert log == [("clone", "w"), ("to", "w", "cuda")]
    assert module.parameters()[0].data is module.parameters()[1].data


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


class Part:
    """A plain tensor, recording which route the pack took with it."""

    def __init__(self, name):
        self.name = name
        self.route = []
        self.device = SimpleNamespace(type="cuda")

    def cpu(self):
        self.route.append("cpu")
        return self

    def clone(self):
        return Part(self.name)

    def to(self, device, non_blocking=False):
        suffix = " (non-blocking)" if non_blocking else ""
        self.route.append(f"to {device}{suffix}")
        return self


class Float8Weight:
    """The shape of torchao's Float8Tensor, as the pack sees it."""

    def __init__(self, qdata, scale, block_size=None, dtype=None):
        self.qdata, self.scale = qdata, scale
        self.block_size, self.dtype = block_size, dtype


class NVFP4Weight:
    """The shape of torchao's NVFP4Tensor, as the pack sees it."""

    def __init__(
        self,
        qdata,
        scale,
        block_size,
        dtype,
        per_tensor_scale,
        act_per_tensor_scale,
        is_swizzled_scales,
        use_triton_kernel,
        act_quant_kwargs,
    ):
        self.qdata, self.scale = qdata, scale
        self.block_size, self.dtype = block_size, dtype
        self.per_tensor_scale, self.act_per_tensor_scale = per_tensor_scale, act_per_tensor_scale
        self.is_swizzled_scales, self.use_triton_kernel = is_swizzled_scales, use_triton_kernel
        self.act_quant_kwargs = act_quant_kwargs


class PackModule:
    def __init__(self, weights):
        self.weights = weights
        self.loaded = None

    def named_parameters(self):
        return [(name, SimpleNamespace(data=weight)) for name, weight in self.weights.items()]

    def named_buffers(self):
        return []

    def load_state_dict(self, state, strict=True, assign=False):
        self.loaded = (state, strict, assign)


def fake_pack_torchao(monkeypatch):
    fake_torchao(monkeypatch, [])
    quantize = sys.modules["torchao.quantization"]
    monkeypatch.setattr(quantize, "Float8Tensor", Float8Weight, raising=False)
    tensors = types.ModuleType("torchao.prototype.mx_formats.nvfp4_tensor")
    monkeypatch.setattr(tensors, "NVFP4Tensor", NVFP4Weight, raising=False)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats.nvfp4_tensor", tensors)
    workflow = types.ModuleType("torchao.prototype.mx_formats.inference_workflow")
    monkeypatch.setattr(workflow, "QuantizeTensorToNVFP4Kwargs", lambda **values: values, raising=False)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats.inference_workflow", workflow)


def fake_safetensors(monkeypatch, store):
    import contextlib

    module = types.ModuleType("safetensors")
    torch_part = types.ModuleType("safetensors.torch")

    def save_file(tensors, path):
        # The pack is assembled beside the published one and swapped in, so the store is
        # keyed by name and the file it stands for exists where the swap looks.
        Path(path).write_bytes(b"")
        store[Path(path).name] = dict(tensors)

    monkeypatch.setattr(torch_part, "save_file", save_file, raising=False)

    @contextlib.contextmanager
    def safe_open(path, framework="pt"):
        yield SimpleNamespace(get_tensor=lambda key: store[str(path)][key])

    monkeypatch.setattr(module, "safe_open", safe_open, raising=False)
    monkeypatch.setitem(sys.modules, "safetensors", module)
    monkeypatch.setitem(sys.modules, "safetensors.torch", torch_part)


def pack_pipe(transformer, encoder=None, vae=None):
    encoder = encoder or PackModule({})
    vae = vae or PackModule({})
    loads = []
    pipe = SimpleNamespace(
        transformer=transformer,
        text_encoder=encoder,
        vae=vae,
        components={"transformer": transformer, "text_encoder": encoder, "vae": vae},
        loads=loads,
    )
    pipe.load_components = lambda names=None, dtype=None, device_map=None: loads.append(
        {"names": names, "dtype": dtype, "device_map": device_map}
    )
    return pipe


def test_weight_kind_names_the_three_kinds(monkeypatch):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)

    assert child.weight_kind(Float8Weight(Part("q"), Part("s"))) == "fp8"
    assert child.weight_kind(NVFP4Weight(Part("q"), Part("s"), 16, None, None, None, True, True, None)) == "nvfp4"
    assert child.weight_kind(Part("plain")) == "plain"


def test_quantize_kwargs_reads_the_settings_a_weight_carries():
    weight = NVFP4Weight(Part("q"), Part("s"), 16, None, None, None, True, True, SimpleNamespace(block_size=16))
    assert child.quantize_kwargs(weight) == {"block_size": 16}
    assert child.quantize_kwargs(Part("plain")) is None


def test_host_copy_waits_for_the_device_before_return(monkeypatch):
    fake_torch(monkeypatch)
    events = []
    host = object()
    source = SimpleNamespace(
        device=SimpleNamespace(type="cuda"),
        to=lambda device, non_blocking: events.append((device, non_blocking)) or host,
    )
    sys.modules["torch"].cuda.synchronize.side_effect = lambda device: events.append(("synchronized", device))

    assert child.copy_to_host(source) is host
    assert events == [("cpu", True), ("synchronized", source.device)]


def test_host_copy_keeps_a_cpu_tensor_without_a_device_wait(monkeypatch):
    fake_torch(monkeypatch)
    source = SimpleNamespace(device=SimpleNamespace(type="cpu"), to=Mock())

    assert child.copy_to_host(source) is source
    source.to.assert_not_called()
    sys.modules["torch"].cuda.synchronize.assert_not_called()


def test_write_pack_stores_each_kind_and_its_manifest(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    store = {}
    fake_safetensors(monkeypatch, store)
    qdata, scale = Part("q"), Part("s")
    scalar = Part("scalar")
    transformer = PackModule(
        {
            "block.weight": Float8Weight(qdata, scale, block_size=[1, 256], dtype="torch.bfloat16"),
            "norm.weight": Part("plain"),
        }
    )
    encoder = PackModule(
        {
            "proj.weight": NVFP4Weight(
                Part("q2"),
                Part("s2"),
                16,
                "torch.bfloat16",
                scalar,
                None,
                True,
                True,
                SimpleNamespace(block_size=16),
            )
        }
    )
    manifest: dict = {"format": 1}

    child.write_pack(pack_pipe(transformer, encoder), tmp_path, manifest)

    stored = store["transformer.safetensors"]
    assert set(stored) == {
        "transformer.block.weight.qdata",
        "transformer.block.weight.scale",
        "transformer.norm.weight",
    }
    assert qdata.route == ["to cpu (non-blocking)"] and scale.route == ["to cpu (non-blocking)"]
    assert scalar.route == ["to cpu (non-blocking)"]
    assert transformer.weights["norm.weight"].route == ["to cpu (non-blocking)"]
    assert sys.modules["torch"].cuda.synchronize.call_count == 6
    assert manifest["tensors"]["transformer.block.weight"] == {
        "kind": "fp8",
        "block_size": [1, 256],
        "dtype": "torch.bfloat16",
    }
    assert manifest["tensors"]["transformer.norm.weight"] == {"kind": "plain"}
    assert manifest["tensors"]["text_encoder.proj.weight"]["kind"] == "nvfp4"
    assert manifest["tensors"]["text_encoder.proj.weight"]["per_tensor_scale"] is True
    assert json.loads((tmp_path / "pack.json").read_text())["tensors"] == manifest["tensors"]


def test_rebuild_restores_fp8(monkeypatch):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    store = {"pack.safetensors": {"layer.weight.qdata": Part("q"), "layer.weight.scale": Part("s")}}

    import contextlib

    @contextlib.contextmanager
    def handle(path, framework="pt"):
        yield SimpleNamespace(get_tensor=lambda key: store["pack.safetensors"][key])

    entry = {"kind": "fp8", "block_size": [1, 256], "dtype": "torch.bfloat16"}
    with handle("x") as opened:
        weight = child.rebuild(entry, "layer.weight", opened, "cuda")

    assert isinstance(weight, Float8Weight)
    assert weight.block_size == [1, 256] and weight.dtype == "bfloat16"


def test_rebuild_restores_nvfp4_with_its_scalar(monkeypatch):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    import contextlib

    tensors = {
        "layer.weight.qdata": Part("q"),
        "layer.weight.scale": Part("s"),
        "layer.weight.per_tensor_scale": Part("scalar"),
    }

    @contextlib.contextmanager
    def handle(path, framework="pt"):
        yield SimpleNamespace(get_tensor=lambda key: tensors[key])

    entry = {
        "kind": "nvfp4",
        "block_size": 16,
        "dtype": "torch.bfloat16",
        "is_swizzled_scales": True,
        "use_triton_kernel": True,
        "act_quant": {"block_size": 16},
        "per_tensor_scale": True,
    }
    with handle("x") as opened:
        weight = child.rebuild(entry, "layer.weight", opened, "cuda")

    assert isinstance(weight, NVFP4Weight)
    assert weight.per_tensor_scale.name == "scalar"
    assert weight.act_quant_kwargs == {"block_size": 16}


def test_rebuild_returns_a_plain_weight_as_it_stands(monkeypatch):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    import contextlib

    @contextlib.contextmanager
    def handle(path, framework="pt"):
        yield SimpleNamespace(get_tensor=lambda key: Part("plain"))

    with handle("x") as opened:
        weight = child.rebuild({"kind": "plain"}, "norm.weight", opened, "cuda")

    assert weight.name == "plain"


def test_load_packed_gives_each_component_its_weights(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    transformer = PackModule({"layer.weight": None})
    pipe = pack_pipe(transformer)
    fake_diffusers(monkeypatch, pipe)
    store = {
        str(tmp_path / "transformer.safetensors"): {"transformer.layer.weight": Part("plain")},
        str(tmp_path / "text_encoder.safetensors"): {},
        str(tmp_path / "vae.safetensors"): {},
    }
    fake_safetensors(monkeypatch, store)
    manifest = {"tensors": {"transformer.layer.weight": {"kind": "plain"}}}

    result = child.load_packed("me/pack", tmp_path, manifest)

    assert result is pipe
    assert transformer.loaded is not None
    state, strict, assign = transformer.loaded
    assert list(state) == ["layer.weight"] and strict is False and assign is True
    assert [item["device_map"] for item in pipe.loads] == ["meta", "cpu"]


def test_load_uses_a_matching_pack(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "build", lambda model, quantize: "built")
    monkeypatch.setattr(child, "load_packed", lambda model, directory, manifest: "packed")
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    files = {}
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
        files[f"{name}.safetensors"] = 0
    (tmp_path / "pack.json").write_text(
        json.dumps(
            {
                "format": 1,
                "model": "me/pack",
                "quantize": "fp8",
                "versions": {"torch": "2.15.0"},
                "source": "abc123",
                "files": files,
            }
        )
    )

    assert child.load("me/pack", "fp8", tmp_path) == "packed"


def test_load_rebuilds_when_a_component_file_is_missing(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    (tmp_path / "pack.json").write_text(
        json.dumps({"format": 1, "model": "me/pack", "quantize": "fp8", "versions": {"torch": "2.15.0"}})
    )

    assert child.load("me/pack", "fp8", tmp_path) == "built"
    assert built == ["fp8"]


def test_load_rebuilds_when_the_pack_versions_differ(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
    (tmp_path / "pack.json").write_text(
        json.dumps({"format": 1, "model": "me/pack", "quantize": "fp8", "versions": {"torch": "2.14.0"}})
    )

    assert child.load("me/pack", "fp8", tmp_path) == "built"


def test_bf16_never_uses_a_pack(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "build", lambda model, quantize: f"built {quantize}")

    assert child.load("me/pack", "bf16", tmp_path) == "built bf16"


def test_a_pack_needs_a_directory(monkeypatch):
    monkeypatch.setattr(child, "build", lambda model, quantize: f"built {quantize}")

    assert child.load("me/pack", "fp8") == "built fp8"


def test_versions_records_the_three_packages(monkeypatch):
    for name, version in (("torch", "2.15.0"), ("torchao", "0.18.0"), ("diffusers", "0.43.0")):
        module = sys.modules.get(name) or types.ModuleType(name)
        monkeypatch.setattr(module, "__version__", version, raising=False)
        monkeypatch.setitem(sys.modules, name, module)

    assert child.versions() == {"torch": "2.15.0", "torchao": "0.18.0", "diffusers": "0.43.0"}


def test_the_pack_directory_is_named_after_the_model(tmp_path):
    assert child.pack_directory(tmp_path, "a/b") == tmp_path / "a--b"


def test_a_manifest_is_read_or_absent(tmp_path):
    assert child.read_manifest(tmp_path) is None
    (tmp_path / "pack.json").write_text(json.dumps({"format": 1}))
    assert child.read_manifest(tmp_path) == {"format": 1}


def test_a_manifest_matches_only_what_it_carries(monkeypatch):
    assert child.manifest_matches({"format": 1, "model": "a"}, {"format": 1}) is True
    assert child.manifest_matches({"format": 2}, {"format": 1}) is False


def test_write_pack_leaves_out_a_missing_scalar(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    store = {}
    fake_safetensors(monkeypatch, store)
    module = PackModule(
        {
            "proj.weight": NVFP4Weight(
                Part("q"),
                Part("s"),
                16,
                "torch.bfloat16",
                None,
                None,
                True,
                True,
                SimpleNamespace(block_size=16),
            )
        }
    )
    manifest = {}

    child.write_pack(pack_pipe(module), tmp_path, manifest)

    stored = store["transformer.safetensors"]
    assert set(stored) == {"transformer.proj.weight.qdata", "transformer.proj.weight.scale"}
    assert manifest["tensors"]["transformer.proj.weight"]["per_tensor_scale"] is False


@pytest.mark.parametrize("save_fails", [False, True])
def test_write_pack_releases_host_copies_before_the_cache_on_success_or_failure(monkeypatch, tmp_path, save_fails):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    fake_safetensors(monkeypatch, {})
    pending = {"copy": False}
    captured = []
    references = []

    class HostTensor:
        pass

    def transfer(device, non_blocking):
        assert device == "cpu" and non_blocking
        pending["copy"] = True
        return HostTensor()

    def synchronize(device):
        pending["copy"] = False

    def save(tensors, path):
        assert not pending["copy"]
        captured.append(tensors)
        references.extend(weakref.ref(tensor) for tensor in tensors.values())
        if save_fails:
            raise OSError("disk full")
        Path(path).write_bytes(b"")

    def release():
        assert not captured[-1]
        assert all(reference() is None for reference in references)

    source = SimpleNamespace(device=SimpleNamespace(type="cuda"), to=transfer)
    torch = sys.modules["torch"]
    torch.cuda.synchronize.side_effect = synchronize
    torch.accelerator.memory.empty_host_cache.side_effect = release
    monkeypatch.setattr(sys.modules["safetensors.torch"], "save_file", save)
    expected = pytest.raises(OSError, match="disk full") if save_fails else nullcontext()

    with expected:
        child.write_pack(pack_pipe(PackModule({"weight": source})), tmp_path, {})

    assert torch.accelerator.memory.empty_host_cache.call_count == (1 if save_fails else 3)


def test_write_pack_releases_unused_device_cache_before_the_first_host_copy(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    fake_safetensors(monkeypatch, {})
    events = []
    source = SimpleNamespace(
        device=SimpleNamespace(type="cuda"),
        to=lambda device, non_blocking: events.append("copy") or object(),
    )
    sys.modules["torch"].cuda.empty_cache.side_effect = lambda: events.append("release device cache")

    child.write_pack(pack_pipe(PackModule({"weight": source})), tmp_path, {})

    assert events == ["release device cache", "copy"]


def test_an_unknown_weight_kind_stops_the_rebuild(monkeypatch):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)

    import contextlib

    @contextlib.contextmanager
    def handle(path, framework="pt"):
        yield SimpleNamespace(get_tensor=lambda key: Part("x"))

    with handle("x") as opened, pytest.raises(SystemExit, match="which this child cannot rebuild"):
        child.rebuild({"kind": "int4"}, "layer.weight", opened, "cuda")


def test_load_packed_fills_a_non_persistent_buffer(monkeypatch, tmp_path):
    """A rotary `inv_freq` is built at construction, so a meta build has none."""
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)

    class Buffer:
        def __init__(self, device):
            self.device = SimpleNamespace(type=device)
            self.name = None
            self.name = "landed"

    class Rotary:
        def __init__(self):
            self._buffers = {"inv_freq": Buffer("meta")}

        def named_buffers(self):
            return [("inv_freq", self._buffers["inv_freq"])]

    class Transformer(PackModule):
        def __init__(self):
            super().__init__({"layer.weight": None})
            self.rope = Rotary()

        def named_buffers(self):
            return [("rope.inv_freq", self.rope._buffers["inv_freq"])]

        def get_submodule(self, name):
            return self.rope

    transformer = Transformer()
    pipe = pack_pipe(transformer)
    fake_diffusers(monkeypatch, pipe)
    store = {
        str(tmp_path / "transformer.safetensors"): {
            "transformer.layer.weight": Part("plain"),
            "transformer.rope.inv_freq": Part("landed"),
        },
        str(tmp_path / "text_encoder.safetensors"): {},
        str(tmp_path / "vae.safetensors"): {},
    }
    fake_safetensors(monkeypatch, store)
    manifest = {
        "tensors": {
            "transformer.layer.weight": {"kind": "plain"},
            "transformer.rope.inv_freq": {"kind": "plain"},
        }
    }

    child.load_packed("me/pack", tmp_path, manifest)

    assert transformer.rope._buffers["inv_freq"].name == "landed"


def test_a_failed_pack_write_does_not_fail_the_run(monkeypatch, tmp_path, capsys):
    def refuse(pipe, directory, manifest):
        raise OSError("No space left on device")

    monkeypatch.setattr(child, "build", lambda model, quantize: "built")
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "write_pack", refuse)

    assert child.load("me/pack", "fp8", tmp_path) == "built"
    assert "could not write the pack: No space left on device" in capsys.readouterr().err


def test_load_packed_fills_a_buffer_on_the_component_itself(monkeypatch, tmp_path):
    """A buffer with no owner in its name belongs to the component, not a child of it."""
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)

    class Buffer:
        def __init__(self):
            self.device = SimpleNamespace(type="meta")
            self.name = None

    class Transformer(PackModule):
        def __init__(self):
            super().__init__({"layer.weight": None})
            self._buffers = {"inv_freq": Buffer()}

        def named_buffers(self):
            return [("inv_freq", self._buffers["inv_freq"])]

    transformer = Transformer()
    pipe = pack_pipe(transformer)
    fake_diffusers(monkeypatch, pipe)
    store = {
        str(tmp_path / "transformer.safetensors"): {
            "transformer.layer.weight": Part("plain"),
            "transformer.inv_freq": Part("landed"),
        },
        str(tmp_path / "text_encoder.safetensors"): {},
        str(tmp_path / "vae.safetensors"): {},
    }
    fake_safetensors(monkeypatch, store)
    manifest = {
        "tensors": {
            "transformer.layer.weight": {"kind": "plain"},
            "transformer.inv_freq": {"kind": "plain"},
            "transformer.landed": {"kind": "plain"},
        }
    }

    child.load_packed("me/pack", tmp_path, manifest)

    assert transformer._buffers["inv_freq"].name == "landed"


def test_load_packed_leaves_a_buffer_that_already_landed(monkeypatch, tmp_path):
    """Only a buffer still on meta needs the pack; one that came back with the module stays."""
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)

    class Buffer:
        def __init__(self, device):
            self.device = SimpleNamespace(type=device)
            self.name = None

    class Transformer(PackModule):
        def __init__(self):
            super().__init__({"layer.weight": None})
            self._buffers = {"inv_freq": Buffer("meta"), "landed": Buffer("cpu")}

        def named_buffers(self):
            return list(self._buffers.items())

    transformer = Transformer()
    landed = transformer._buffers["landed"]
    pipe = pack_pipe(transformer)
    fake_diffusers(monkeypatch, pipe)
    store = {
        str(tmp_path / "transformer.safetensors"): {
            "transformer.layer.weight": Part("plain"),
            "transformer.inv_freq": Part("filled"),
            "transformer.landed": Part("again"),
        },
        str(tmp_path / "text_encoder.safetensors"): {},
        str(tmp_path / "vae.safetensors"): {},
    }
    fake_safetensors(monkeypatch, store)
    manifest = {
        "tensors": {
            "transformer.layer.weight": {"kind": "plain"},
            "transformer.inv_freq": {"kind": "plain"},
            "transformer.landed": {"kind": "plain"},
        }
    }

    child.load_packed("me/pack", tmp_path, manifest)

    assert transformer._buffers["inv_freq"].name == "filled"
    assert transformer._buffers["landed"] is landed


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
            "prompt": "Make it <Picture 1> at night.",
            "height": 2048,
            "width": 2048,
            "steps": 6,
            "seed": 3,
            "references": [encoded, encoded],
        },
    )

    assert reply["png_base64"] == "cG5nLWJ5dGVz"
    call = pipe.calls[0]
    assert [image.size for image in call["image"]] == [(4, 3), (4, 3)]
    assert (call["height"], call["width"]) == (2048, 2048)


def test_a_generate_run_sends_no_image(monkeypatch):
    fake_torch(monkeypatch)

    child.run(FakePipe(), {"prompt": "a fox", "height": 512, "width": 512, "steps": 6, "seed": 1})


def test_generate_and_edit_use_the_selected_canvas_without_an_area_floor(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    for mode in ("generate", "edit"):
        child.run(
            pipe,
            {
                "mode": mode,
                "prompt": "a fox",
                "height": 576,
                "width": 1024,
                "steps": 6,
                "seed": 1,
                "references": [png()],
            },
        )
        assert pipe.calls[-1]["min_generation_area"] == 1024
        assert (pipe.calls[-1]["height"], pipe.calls[-1]["width"]) == (576, 1024)


def test_a_half_written_manifest_reads_as_no_pack(tmp_path, capsys):
    (tmp_path / "pack.json").write_text('{"format": 1, "tensors": {', encoding="utf-8")

    assert child.read_manifest(tmp_path) is None
    assert "built again" in capsys.readouterr().err


def test_a_pack_that_dies_while_it_is_written_is_not_published(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    fake_pack_torchao(monkeypatch)
    store = {}
    fake_safetensors(monkeypatch, store)
    directory = tmp_path / "pack"
    directory.mkdir()
    (directory / "pack.json").write_text('{"format": 1, "old": true}', encoding="utf-8")

    written = []

    def half_then_die(tensors, path):
        Path(path).write_bytes(b"")
        written.append(path)
        if len(written) == 2:
            raise OSError("the disk went away")

    monkeypatch.setattr(sys.modules["safetensors.torch"], "save_file", half_then_die, raising=False)
    transformer = PackModule({"norm.weight": Part("plain")})

    with pytest.raises(OSError, match="the disk went away"):
        child.write_pack(pack_pipe(transformer, PackModule({})), directory, {"format": 1})

    assert [one.name for one in directory.iterdir()] == ["pack.json"]
    assert json.loads((directory / "pack.json").read_text(encoding="utf-8"))["old"] is True


def test_the_pack_names_the_snapshot_the_model_resolves_to(monkeypatch, tmp_path):
    snapshot = tmp_path / "models--me--pack" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("me/pack") == "abc123"


def test_a_model_this_machine_cannot_name_reports_unknown():
    assert child.source_revision("org/not-cached") == "unknown"


def test_a_cache_with_two_snapshots_is_not_named_after_one(monkeypatch, tmp_path):
    """Two snapshots under one repository id is an ambiguous cache: neither commit is the
    identity of the weights, so the pack records what it can and no more."""
    for commit in ("abc123", "def456"):
        (tmp_path / "models--me--pack" / "snapshots" / commit).mkdir(parents=True)
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("me/pack") == "unknown"


def test_a_machine_without_the_cache_names_a_local_folder(monkeypatch, tmp_path):
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", None)
    folder = tmp_path / "checkpoint"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(b"1234")
    (folder / "sub").mkdir()  # a folder is not part of the identity

    assert child.source_revision(str(folder)).startswith("local:")


def test_the_first_pack_is_published_into_a_folder_that_does_not_exist_yet(tmp_path):
    staging = child.staging_directory(tmp_path / "pack")
    (staging / "pack.json").write_text("{}")

    child.publish(staging, tmp_path / "pack")

    assert (tmp_path / "pack" / "pack.json").is_file()
    assert not staging.exists()


def test_the_source_is_the_snapshot_the_cache_points_at(monkeypatch, tmp_path):
    """Two cached snapshots used to report `unknown`, so a pack built from one revision
    could serve the other. The cache names the revision it resolves to."""
    root = tmp_path / "models--me--pack"
    for commit in ("aaa111", "bbb222"):
        (root / "snapshots" / commit).mkdir(parents=True)
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("bbb222\n")
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("me/pack") == "bbb222"


def test_a_local_model_is_named_by_its_files_and_times(tmp_path):
    folder = tmp_path / "checkpoint"
    folder.mkdir()
    weight = folder / "model.safetensors"
    weight.write_bytes(b"1234")
    first = child.source_revision(str(folder))
    weight.write_bytes(b"4321")  # the same length, so a size alone would miss it

    assert first.startswith("local:")
    assert child.source_revision(str(folder)) != first


def test_a_manifest_that_is_not_an_object_reads_as_no_pack(tmp_path, capsys):
    (tmp_path / "pack.json").write_text("[]", encoding="utf-8")

    assert child.read_manifest(tmp_path) is None
    assert "not a pack manifest" in capsys.readouterr().err


def test_a_pack_whose_file_changed_size_is_built_again(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    files = {}
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
        files[f"{name}.safetensors"] = 0
    (tmp_path / "pack.json").write_text(
        json.dumps(
            {
                "format": 1,
                "model": "me/pack",
                "quantize": "fp8",
                "versions": {"torch": "2.15.0"},
                "source": "abc123",
                "files": files,
            }
        )
    )
    (tmp_path / "transformer.safetensors").write_text("truncated")

    assert child.load("me/pack", "fp8", tmp_path) == "built"
    assert built == ["fp8"]


def test_a_pack_that_will_not_load_is_moved_aside_and_built_once(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    files = {}
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
        files[f"{name}.safetensors"] = 0
    (tmp_path / "pack.json").write_text(
        json.dumps(
            {
                "format": 1,
                "model": "me/pack",
                "quantize": "fp8",
                "versions": {"torch": "2.15.0"},
                "source": "abc123",
                "files": files,
            }
        )
    )

    def refuse(model, directory, manifest):
        raise ValueError("the weights are truncated")

    monkeypatch.setattr(child, "load_packed", refuse)

    assert child.load("me/pack", "fp8", tmp_path) == "built"
    assert built == ["fp8"]
    assert not tmp_path.exists()
    assert list(tmp_path.parent.glob(f"{tmp_path.name}.corrupt-*")), "the bad pack is kept out of the way"


def test_a_pack_that_does_not_name_its_files_is_built_again(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
    (tmp_path / "pack.json").write_text(
        json.dumps(
            {"format": 1, "model": "me/pack", "quantize": "fp8", "versions": {"torch": "2.15.0"}, "source": "abc123"}
        )
    )

    assert child.load("me/pack", "fp8", tmp_path) == "built"
    assert built == ["fp8"]


def test_a_cache_that_names_no_snapshot_is_unknown(monkeypatch, tmp_path):
    root = tmp_path / "models--me--pack"
    for commit in ("aaa111", "bbb222"):
        (root / "snapshots" / commit).mkdir(parents=True)
    (root / "refs").mkdir()
    (root / "refs" / "main").write_text("gone\n")
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("me/pack") == "unknown"


def test_quarantine_leaves_a_missing_pack_alone(tmp_path):
    child.quarantine(tmp_path / "absent")

    assert not (tmp_path / "absent").exists()


def test_a_pack_left_under_its_old_name_is_put_back(tmp_path):
    """A publish that dies between its two renames leaves the pack under `.old`. The next
    start uses it instead of spending the quantization again."""
    directory = tmp_path / "pack"
    previous = tmp_path / "pack.old"
    previous.mkdir()
    (previous / "pack.json").write_text("{}")

    child.recover(directory)

    assert (directory / "pack.json").is_file()
    assert not previous.exists()


def test_recovery_leaves_a_published_pack_alone(tmp_path):
    directory = tmp_path / "pack"
    directory.mkdir()
    (directory / "pack.json").write_text("{}")
    (tmp_path / "pack.old").mkdir()

    child.recover(directory)

    assert (directory / "pack.json").is_file()
    assert (tmp_path / "pack.old").is_dir()


def test_two_builders_never_share_a_staging_folder(tmp_path):
    first = child.staging_directory(tmp_path / "pack")
    second = child.staging_directory(tmp_path / "pack")

    assert first != second
    assert first.is_dir() and second.is_dir()


def test_a_lock_left_by_a_dead_process_is_taken_over(tmp_path):
    lock = tmp_path / "pack.lock"
    lock.write_text("4194303")  # no such process

    with child.pack_lock(tmp_path / "pack"):
        assert lock.is_file()

    assert not lock.exists()


def test_a_second_builder_waiting_uses_what_the_first_published(monkeypatch, tmp_path):
    built = []
    monkeypatch.setattr(child, "build", lambda model, quantize: built.append(quantize) or "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    monkeypatch.setattr(child, "load_packed", lambda model, directory, manifest: "packed")
    reasons = iter(["there is no readable pack", None])
    monkeypatch.setattr(child, "pack_state", lambda directory, expected: next(reasons, None))

    assert child.load("me/pack", "fp8", tmp_path) == "packed"
    assert built == [], "the waited-for pack is used instead of building again"


def test_a_lock_with_no_holder_and_an_old_stamp_is_left_over(tmp_path):
    import os

    lock = tmp_path / "pack.lock"
    lock.write_text("garbage")
    old = lock.stat().st_mtime - 120
    os.utime(lock, (old, old))

    with child.pack_lock(tmp_path / "pack"):
        assert lock.is_file()

    assert not lock.exists()


def test_a_live_lock_is_waited_for(tmp_path):
    import threading

    held = threading.Event()
    released = threading.Event()
    acquired = []

    with child.pack_lock(tmp_path / "pack"):
        held.set()

        def wait():
            with child.pack_lock(tmp_path / "pack"):
                acquired.append(True)
            released.set()

        thread = threading.Thread(target=wait)
        thread.start()
        assert held.wait(1)
        assert not released.wait(0.5), "the second builder must wait"
    assert released.wait(10)
    thread.join(10)
    assert acquired == [True]


def test_a_pack_that_will_not_load_twice_raises(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "build", lambda model, quantize: "built")
    monkeypatch.setattr(child, "write_pack", lambda pipe, directory, manifest: None)
    monkeypatch.setattr(child, "pack_directory", lambda root, model: tmp_path)
    monkeypatch.setattr(child, "versions", lambda: {"torch": "2.15.0"})
    monkeypatch.setattr(child, "source_revision", lambda model: "abc123")
    monkeypatch.setattr(child, "pack_state", lambda directory, expected: None)

    def refuse(model, directory, manifest):
        raise ValueError("the weights are truncated")

    monkeypatch.setattr(child, "load_packed", refuse)

    with pytest.raises(ValueError, match="truncated"):
        child.load("me/pack", "fp8", tmp_path)


def test_the_running_check_answers_for_this_process_and_a_dead_one():
    import os

    assert child._running(os.getpid()) is True
    assert child._running(4194303) is False
    assert child._running(1) is True, "another user's process is there, we just may not signal it"
