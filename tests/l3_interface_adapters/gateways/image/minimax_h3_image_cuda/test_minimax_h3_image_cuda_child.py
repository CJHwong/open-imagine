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
        self.vae = SimpleNamespace(parameters=lambda: [], buffers=lambda: [])
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "vae": self.vae,
        }

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
        self.vae = SimpleNamespace(parameters=lambda: [], buffers=lambda: [])
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "vae": self.vae,
        }

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

    def cpu(self):
        self.route.append("cpu")
        return self

    def clone(self):
        return Part(self.name)

    def to(self, device):
        self.route.append(f"to {device}")
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
    monkeypatch.setattr(
        torch_part, "save_file", lambda tensors, path: store.update({str(path): dict(tensors)}), raising=False
    )

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

    stored = store[str(tmp_path / "transformer.safetensors")]
    assert set(stored) == {
        "transformer.block.weight.qdata",
        "transformer.block.weight.scale",
        "transformer.norm.weight",
    }
    assert qdata.route == ["cpu"] and scale.route == ["cpu"]
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
    for name in child.PACK_COMPONENTS:
        (tmp_path / f"{name}.safetensors").write_text("")
    (tmp_path / "pack.json").write_text(
        json.dumps({"format": 1, "model": "me/pack", "quantize": "fp8", "versions": {"torch": "2.15.0"}})
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

    stored = store[str(tmp_path / "transformer.safetensors")]
    assert set(stored) == {"transformer.proj.weight.qdata", "transformer.proj.weight.scale"}
    assert manifest["tensors"]["transformer.proj.weight"]["per_tensor_scale"] is False


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


def test_local_snapshot_prefers_the_cached_directory(monkeypatch):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "snapshot_download", lambda model, local_files_only: "/cached", raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/pack") == "/cached"


def test_local_snapshot_keeps_an_id_that_is_not_cached(monkeypatch):
    def refuse(model, local_files_only):
        raise OSError("no cache")

    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "snapshot_download", refuse, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/pack") == "me/pack"
