import base64
import contextlib
import io
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.music.yue2_cuda import yue2_cuda_child as child


class StubTensor:
    """Enough of a tensor for the pack writer, which only moves and reshapes."""

    def __init__(self, name="tensor"):
        self.name = name

    def detach(self):
        return self

    def clone(self):
        return self

    def contiguous(self):
        return self

    def float(self):
        return self

    def reshape(self, *shape):
        return self

    def to(self, device):
        return self


class FakeLinear:
    def __init__(self, weight=None, bias=None):
        self.weight = weight
        self.bias = bias


class FakeModel:
    def __init__(self, modules=None):
        self.modules = modules or {}
        self.loaded = []
        self.evaluated = False

    def named_modules(self):
        return list(self.modules.items())

    def get_submodule(self, name):
        return self.modules[name]

    def load_state_dict(self, state, strict=False, assign=False):
        self.loaded.append((state, strict, assign))

    def eval(self):
        self.evaluated = True


@dataclass(frozen=True)
class FakeGenerationConfig:
    ode_steps: int = 32


class FakePipe:
    def __init__(self, model=None, model_dir="/models/yue2"):
        self.model_dir = Path(model_dir)
        self._model = model
        self.requests = []
        self.generation_config = FakeGenerationConfig()
        self.observed_steps = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _load_model(self, for_nar=False):
        return self._model

    def plan(self, **request):
        self.requests.append(("plan", request))
        return SimpleNamespace(abc="X:1")

    def __call__(self, **request):
        self.requests.append(("generate", request))
        self.observed_steps.append(self.generation_config.ode_steps)
        return SimpleNamespace(audio=[[0.0, 0.0]], abc="X:1", truncated={"semantic": False})


class FakeNVFP4Tensor:
    def __init__(
        self,
        qdata,
        scale,
        block_size,
        orig_dtype,
        per_tensor_scale,
        act_per_tensor_scale,
        is_swizzled_scales,
        use_triton_kernel,
        act_quant_kwargs,
    ):
        self.qdata, self.scale = qdata, scale
        self.block_size, self.orig_dtype = block_size, orig_dtype
        self.per_tensor_scale, self.act_per_tensor_scale = per_tensor_scale, act_per_tensor_scale
        self.is_swizzled_scales, self.use_triton_kernel = is_swizzled_scales, use_triton_kernel
        self.act_quant_kwargs = act_quant_kwargs


class FakeKwargs:
    def __init__(self, **values):
        self.__dict__.update(values)


class FakeConfig:
    use_triton_kernel = True
    use_dynamic_per_tensor_scale = True


def fake_modules(monkeypatch, *, pipe=None, model=None, recorded=None, shards=None):
    """Every package the pack path touches, faked at the module boundary."""
    recorded = recorded if recorded is not None else {}
    recorded.setdefault("saved", {})
    recorded.setdefault("quantized", [])
    if shards is None:
        shards = {}

    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "torch.bfloat16", raising=False)
    monkeypatch.setattr(torch, "float32", "torch.float32", raising=False)
    monkeypatch.setattr(
        torch,
        "nn",
        types.SimpleNamespace(Linear=FakeLinear, Parameter=lambda value, requires_grad=True: value),
        raising=False,
    )
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(
            is_available=lambda: recorded.get("cuda", True),
            synchronize=Mock(),
            empty_cache=Mock(),
        ),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    yue2 = types.ModuleType("yue2")
    monkeypatch.setattr(
        yue2, "YuE2Pipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "yue2", yue2)

    modeling = types.ModuleType("yue2.modeling_yue2")
    monkeypatch.setattr(
        modeling,
        "YuE2Config",
        SimpleNamespace(from_pretrained=lambda path: SimpleNamespace(path=path)),
        raising=False,
    )
    monkeypatch.setattr(modeling, "YuE2ForCausalLM", lambda config: model, raising=False)
    monkeypatch.setitem(sys.modules, "yue2.modeling_yue2", modeling)

    mslk = types.ModuleType("mslk")
    monkeypatch.setattr(mslk, "__version__", "1.4.0", raising=False)
    monkeypatch.setitem(sys.modules, "mslk", mslk)

    torchao = types.ModuleType("torchao")
    monkeypatch.setattr(torchao, "__version__", "0.18.0", raising=False)
    quantization = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(
        quantization,
        "quantize_",
        lambda module, config: recorded["quantized"].append((module, config)),
        raising=False,
    )
    mx = types.ModuleType("torchao.prototype.mx_formats")
    monkeypatch.setattr(mx, "NVFP4DynamicActivationNVFP4WeightConfig", FakeConfig, raising=False)
    monkeypatch.setattr(mx, "NVFP4Tensor", FakeNVFP4Tensor, raising=False)
    monkeypatch.setattr(mx, "QuantizeTensorToNVFP4Kwargs", FakeKwargs, raising=False)
    workflow = types.ModuleType("torchao.prototype.mx_formats.inference_workflow")
    monkeypatch.setattr(workflow, "NVFP4DynamicActivationNVFP4WeightConfig", FakeConfig, raising=False)
    tensor_module = types.ModuleType("torchao.prototype.mx_formats.nvfp4_tensor")
    monkeypatch.setattr(tensor_module, "NVFP4Tensor", FakeNVFP4Tensor, raising=False)
    monkeypatch.setattr(tensor_module, "QuantizeTensorToNVFP4Kwargs", FakeKwargs, raising=False)
    monkeypatch.setitem(sys.modules, "torchao", torchao)
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantization)
    monkeypatch.setitem(sys.modules, "torchao.prototype", types.ModuleType("torchao.prototype"))
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats", mx)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats.inference_workflow", workflow)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats.nvfp4_tensor", tensor_module)

    safetensors = types.ModuleType("safetensors")
    torch_safe = types.ModuleType("safetensors.torch")

    def save_file(tensors, path):
        recorded["saved"].update(tensors)
        Path(path).write_bytes(b"packed")

    monkeypatch.setattr(torch_safe, "save_file", save_file, raising=False)
    monkeypatch.setattr(torch_safe, "load_file", lambda path: recorded.get("pack_tensors", {}), raising=False)

    @contextlib.contextmanager
    def safe_open(path, framework="pt"):
        yield SimpleNamespace(
            keys=lambda: list(shards[path].keys()),
            get_tensor=lambda key: shards[path][key],
        )

    monkeypatch.setattr(safetensors, "torch", torch_safe, raising=False)
    monkeypatch.setattr(safetensors, "safe_open", safe_open, raising=False)
    monkeypatch.setitem(sys.modules, "safetensors", safetensors)
    monkeypatch.setitem(sys.modules, "safetensors.torch", torch_safe)

    accelerate = types.ModuleType("accelerate")

    @contextlib.contextmanager
    def init_empty_weights():
        yield

    monkeypatch.setattr(accelerate, "init_empty_weights", init_empty_weights, raising=False)
    monkeypatch.setitem(sys.modules, "accelerate", accelerate)

    soundfile = types.ModuleType("soundfile")
    monkeypatch.setattr(
        soundfile,
        "write",
        lambda buffer, data, rate, format=None, subtype=None: buffer.write(b"wav-bytes"),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "soundfile", soundfile)
    return recorded


def quantized_linears():
    return {
        "model.layers.0.mlp.gate_proj": FakeLinear(
            FakeNVFP4Tensor(
                StubTensor("qdata"),
                StubTensor("scale"),
                16,
                "torch.bfloat16",
                StubTensor("scale0"),
                None,
                True,
                True,
                FakeKwargs(),
            )
        ),
        "model.layers.0.mlp.down_proj": FakeLinear(
            FakeNVFP4Tensor(
                StubTensor("qdata"),
                StubTensor("scale"),
                16,
                "torch.bfloat16",
                StubTensor("scale0"),
                None,
                True,
                True,
                FakeKwargs(),
            )
        ),
        "model.embed_tokens": FakeLinear(StubTensor("bf16")),
    }


def test_versions_names_each_package(monkeypatch):
    recorded = fake_modules(monkeypatch)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)

    assert child.versions() == {"torch": "2.15.0", "torchao": "0.18.0", "mslk": "1.4.0"}
    assert recorded["quantized"] == []


def test_quantize_ar_puts_both_operands_in_fp4(monkeypatch):
    recorded = fake_modules(monkeypatch)
    module = FakeLinear()

    child.quantize_ar(module)

    assert len(recorded["quantized"]) == 1
    assert recorded["quantized"][0][0] is module
    assert isinstance(recorded["quantized"][0][1], FakeConfig)


def test_packed_layers_finds_only_the_fp4_linears(monkeypatch):
    fake_modules(monkeypatch)

    assert child.packed_layers(FakeModel(quantized_linears())) == [
        "model.layers.0.mlp.gate_proj",
        "model.layers.0.mlp.down_proj",
    ]


def test_the_expected_manifest_carries_the_configuration(monkeypatch):
    fake_modules(monkeypatch)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)

    manifest = child.expected_manifest("m-a-p/YuE2-3B")

    assert manifest["model"] == "m-a-p/YuE2-3B"
    assert manifest["versions"]["mslk"] == "1.4.0"
    assert manifest["act_quant"]["use_triton_kernel"] is True
    assert manifest["orig_dtype"] == "torch.bfloat16"


def test_a_manifest_matches_only_when_every_field_agrees(monkeypatch):
    fake_modules(monkeypatch)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    expected = child.expected_manifest("m-a-p/YuE2-3B")

    assert child.manifest_matches({**expected, "layers": ["a"]}, expected) is True
    assert child.manifest_matches({**expected, "format": 0}, expected) is False
    assert child.manifest_matches({}, expected) is False


def test_the_pack_path_names_the_checkpoint(tmp_path):
    assert child.pack_path(tmp_path, "m-a-p/YuE2-3B") == tmp_path / "m-a-p--YuE2-3B"


def test_a_missing_pack_reads_as_no_manifest(tmp_path):
    assert child.read_manifest(tmp_path) is None


def test_a_written_manifest_is_read_back(tmp_path):
    (tmp_path / "pack.json").write_text(json.dumps({"format": 1}), encoding="utf-8")

    assert child.read_manifest(tmp_path) == {"format": 1}


def test_write_pack_saves_every_packed_tensor(monkeypatch, tmp_path):
    recorded = fake_modules(monkeypatch)
    model = FakeModel(quantized_linears())
    manifest = {"layers": ["model.layers.0.mlp.gate_proj"], "block_size": 16}

    child.write_pack(model, tmp_path, manifest)

    assert sorted(recorded["saved"]) == [
        "model.layers.0.mlp.gate_proj.per_tensor_scale",
        "model.layers.0.mlp.gate_proj.qdata",
        "model.layers.0.mlp.gate_proj.scale",
    ]
    written = json.loads((tmp_path / "pack.json").read_text(encoding="utf-8"))
    assert written["has_per_tensor_scale"] is True


def test_write_pack_records_a_layer_without_a_per_tensor_scale(monkeypatch, tmp_path):
    recorded = fake_modules(monkeypatch)
    model = FakeModel(
        {
            "layer": FakeLinear(
                FakeNVFP4Tensor(StubTensor(), StubTensor(), 16, "torch.bfloat16", None, None, True, True, FakeKwargs())
            )
        }
    )

    child.write_pack(model, tmp_path, {"layers": ["layer"], "block_size": 16})

    assert sorted(recorded["saved"]) == ["layer.qdata", "layer.scale"]
    assert json.loads((tmp_path / "pack.json").read_text())["has_per_tensor_scale"] is False


def test_empty_model_is_built_without_weights(monkeypatch):
    model = FakeModel()
    fake_modules(monkeypatch, model=model)
    seen = {}
    accelerate = sys.modules["accelerate"]
    monkeypatch.setattr(accelerate, "init_empty_weights", lambda: _record_context(seen))

    assert child.empty_model(Path("/models/yue2")) is model
    assert seen["entered"] is True


def _record_context(seen):
    @contextlib.contextmanager
    def context():
        seen["entered"] = True
        yield

    return context()


def test_load_unpacked_reads_only_what_the_pack_does_not_carry(monkeypatch, tmp_path):
    shards = {}
    model = FakeModel()
    fake_modules(monkeypatch, model=model, shards=shards)
    shard = tmp_path / "model.safetensors"
    shard.write_bytes(b"")
    shards[str(shard)] = {
        "model.layers.0.mlp.gate_proj.weight": "packed",
        "model.layers.0.mlp.gate_proj.bias": "bias",
        "model.embed_tokens.weight": "embed",
    }

    loaded = child.load_unpacked(model, tmp_path, {"model.layers.0.mlp.gate_proj"})

    assert loaded == 2
    assert model.loaded[0][0] == {
        "model.layers.0.mlp.gate_proj.bias": "bias",
        "model.embed_tokens.weight": "embed",
    }
    assert model.loaded[0][1:] == (False, True)


def test_load_unpacked_skips_a_shard_with_nothing_wanted(monkeypatch, tmp_path):
    shards = {}
    model = FakeModel()
    fake_modules(monkeypatch, model=model, shards=shards)
    shard = tmp_path / "model.safetensors"
    shard.write_bytes(b"")
    shards[str(shard)] = {"model.layers.0.mlp.gate_proj.weight": "packed"}

    assert child.load_unpacked(model, tmp_path, {"model.layers.0.mlp.gate_proj"}) == 0
    assert model.loaded == []


def test_attach_pack_rebuilds_each_tensor_from_the_manifest(monkeypatch):
    fake_modules(monkeypatch)
    module = FakeLinear(StubTensor("bf16"))
    model = FakeModel({"layer": module})
    manifest = {
        "layers": ["layer"],
        "block_size": 16,
        "orig_dtype": "torch.bfloat16",
        "is_swizzled_scales": True,
        "use_triton_kernel": True,
        "act_quant": {
            "block_size": 16,
            "is_swizzled_scales": True,
            "use_triton_kernel": True,
            "use_dynamic_per_tensor_scale": True,
        },
    }

    child.attach_pack(model, {"layer.qdata": StubTensor("q"), "layer.scale": StubTensor("s")}, manifest)

    assert isinstance(module.weight, FakeNVFP4Tensor)
    assert module.weight.per_tensor_scale is None
    assert module.weight.act_quant_kwargs.use_dynamic_per_tensor_scale is True


def test_attach_pack_carries_the_scalar_scale(monkeypatch):
    fake_modules(monkeypatch)
    module = FakeLinear(StubTensor("bf16"))
    model = FakeModel({"layer": module})
    manifest = {
        "layers": ["layer"],
        "block_size": 16,
        "orig_dtype": "torch.bfloat16",
        "is_swizzled_scales": True,
        "use_triton_kernel": True,
        "act_quant": {
            "block_size": 16,
            "is_swizzled_scales": True,
            "use_triton_kernel": True,
            "use_dynamic_per_tensor_scale": True,
        },
    }

    child.attach_pack(
        model,
        {
            "layer.qdata": StubTensor("q"),
            "layer.scale": StubTensor("s"),
            "layer.per_tensor_scale": StubTensor("scale0"),
        },
        manifest,
    )

    assert getattr(module.weight, "per_tensor_scale", None) is not None


def test_the_first_fp4_run_builds_the_pack(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)

    result = child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert result is pipe
    assert len(recorded["quantized"]) == 1
    assert (tmp_path / "m-a-p--YuE2-3B" / "pack.json").is_file()
    written = json.loads((tmp_path / "m-a-p--YuE2-3B" / "pack.json").read_text())
    assert written["layers"] == ["model.layers.0.mlp.gate_proj", "model.layers.0.mlp.down_proj"]


def test_a_matching_pack_is_served_without_touching_the_checkpoint_weights(monkeypatch, tmp_path):
    model = FakeModel({"layer": FakeLinear()})
    pipe = FakePipe(model=None, model_dir=tmp_path / "checkpoint")
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    manifest = {
        **child.expected_manifest("m-a-p/YuE2-3B"),
        "layers": ["layer"],
        "has_per_tensor_scale": False,
        "files": {"weights.safetensors": 0},
    }
    (directory / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    shard = tmp_path / "checkpoint" / "model.safetensors"
    shard.parent.mkdir()
    shard.write_bytes(b"")
    (directory / "weights.safetensors").write_bytes(b"")
    monkeypatch.setattr(child, "empty_model", lambda model_dir: model)
    monkeypatch.setattr(child, "load_unpacked", lambda model, model_dir, packed: 3)
    recorded["pack_tensors"] = {"layer.qdata": StubTensor("q"), "layer.scale": StubTensor("s")}

    result = child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert result is pipe and pipe._model is model
    assert model.evaluated is True
    assert recorded["quantized"] == []


def test_a_pack_from_another_version_is_rebuilt(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "pack.json").write_text(
        json.dumps({**child.expected_manifest("m-a-p/YuE2-3B"), "versions": {"torch": "2.10.0"}}),
        encoding="utf-8",
    )

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1


def test_load_refuses_a_quantizer_it_does_not_offer(monkeypatch):
    fake_modules(monkeypatch)

    with pytest.raises(SystemExit, match="quantize must be one of"):
        child.load("me/model", "q4")


def test_fp4_refuses_to_run_without_a_pack_directory(monkeypatch):
    fake_modules(monkeypatch)

    with pytest.raises(SystemExit, match="needs --pack-dir"):
        child.load("me/model", "nvfp4")


def test_fp4_hands_the_work_to_the_pack_loader(monkeypatch, tmp_path):
    fake_modules(monkeypatch)
    seen = {}
    monkeypatch.setattr(
        child,
        "load_packed",
        lambda model, root: seen.update(model=model, root=root) or FakePipe(),
    )

    assert isinstance(child.load("me/model", "nvfp4", tmp_path), FakePipe)
    assert seen == {"model": "me/model", "root": tmp_path}


@pytest.mark.parametrize("name,expected", [("bf16", "none"), ("fp8", "fp8")])
def test_load_asks_the_engine_for_its_own_arithmetic(monkeypatch, name, expected):
    calls = []
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)
    monkeypatch.setattr(
        sys.modules["yue2"],
        "YuE2Pipeline",
        SimpleNamespace(from_pretrained=lambda model, **kwargs: calls.append((model, kwargs)) or pipe),
        raising=False,
    )

    assert child.load("me/model", name) is pipe
    assert calls == [("me/model", {"device": "cuda", "quantization": expected})]


def job(**overrides):
    base = {"style": "piano", "lyrics": "[Verse]\nhello", "seed": 7, "cot": "full"}
    base.update(overrides)
    return base


def test_the_request_marks_an_instrumental_style():
    request = child.request_for(job(instrumental=True))

    assert request["style"].startswith("Instrumental, ")
    assert request["seed"] == 7 and request["cot"] == "full"
    assert "abc" not in request


def test_a_supplied_score_travels_and_a_blank_one_does_not():
    assert child.request_for(job(abc="X:1"))["abc"] == "X:1"
    assert "abc" not in child.request_for(job(abc="   "))


def test_a_generate_job_returns_wav_bytes_and_the_score(monkeypatch):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)

    reply = child.run(pipe, job(), Path("/tmp/yue2-extras"))

    assert reply["wav"] == "d2F2LWJ5dGVz"
    assert reply["score"] == "X:1" and reply["truncated"] == {"semantic": False}
    assert pipe.requests[0][0] == "generate"


def test_sampling_overrides_reach_both_stages_and_an_empty_map_stays_out(monkeypatch):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)

    child.run(
        pipe,
        {"style": "piano", "lyrics": "[Verse]\nhi", "seed": 7, "sampling": {"max_tokens": 2048}},
        Path("/tmp/yue2-extras"),
    )
    child.run(pipe, {"style": "piano", "lyrics": "[Verse]\nhi", "seed": 7}, Path("/tmp/yue2-extras"))

    with_sampling = pipe.requests[-2][1]
    assert with_sampling["abc_sampling"] == {"max_tokens": 2048}
    assert with_sampling["semantic_sampling"] == {"max_tokens": 2048}
    assert "abc_sampling" not in pipe.requests[-1][1]


def test_synthesis_settings_reach_the_engine_without_leaking_to_the_next_job(monkeypatch):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)

    child.run(pipe, job(steps=8, cfg_scale=2.5), Path("/tmp/yue2-extras"))
    child.run(pipe, job(steps=16, cfg_scale=0.0), Path("/tmp/yue2-extras"))
    child.run(pipe, job(), Path("/tmp/yue2-extras"))

    assert pipe.observed_steps == [8, 16, 32]
    assert [request.get("cfg_scale") for _, request in pipe.requests] == [2.5, 0.0, None]
    assert pipe.generation_config.ode_steps == 32


def test_synthesis_steps_are_restored_after_engine_failure(monkeypatch):
    class BrokenPipe(FakePipe):
        def __call__(self, **request):
            assert self.generation_config.ode_steps == 8
            raise RuntimeError("engine failed")

    pipe = BrokenPipe()
    fake_modules(monkeypatch, pipe=pipe)
    with pytest.raises(RuntimeError, match="engine failed"):
        child.run(pipe, job(steps=8), Path("/tmp/yue2-extras"))
    assert pipe.generation_config.ode_steps == 32


def test_guidance_reaches_the_score_plan(monkeypatch):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)

    child.run(pipe, job(mode="plan", cfg_scale=2.0), Path("/tmp/yue2-extras"))

    assert pipe.requests[0][1]["cfg_scale"] == 2.0


def test_a_plan_job_returns_the_score_only(monkeypatch):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)

    reply = child.run(pipe, job(mode="plan"), Path("/tmp/yue2-extras"))

    assert reply == {"score": "X:1", "metadata": {"mode": "plan"}}
    assert pipe.requests[0][0] == "plan"


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    recorded = fake_modules(monkeypatch)
    recorded["cuda"] = False
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join([json.dumps(job()), "", json.dumps({"seed": 1})])))

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "wav" in lines[0]
    assert lines[1]["error"].startswith("KeyError")


def test_main_passes_the_pack_directory_to_the_loader(monkeypatch):
    fake_modules(monkeypatch)
    seen = {}
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "nvfp4", "--pack-dir", "/cache/pack"])
    monkeypatch.setattr(
        child, "load", lambda model, name, root: seen.update(model=model, name=name, root=root) or FakePipe()
    )
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert child.main() == 0
    assert seen["name"] == "nvfp4" and seen["root"] == Path("/cache/pack")


def test_main_asks_for_no_pack_directory_when_none_is_given(monkeypatch):
    fake_modules(monkeypatch)
    seen = {}
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(child, "load", lambda model, name, root: seen.update(root=root) or FakePipe())
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert child.main() == 0
    assert seen["root"] is None


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0


def test_the_pin_is_a_git_blob_hash():
    assert child.blob_sha1(b"hi") == "32f95c0d1244a78b2be1bab8de17906fabb2c4a8"


def test_a_pinned_file_is_fetched_and_checked(monkeypatch):
    body = b"# script\n"

    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *rest):
            return False

        def read(self):
            return body

    monkeypatch.setitem(child.TRANSCRIBER_FILES, "transcribe.py", child.blob_sha1(body))
    monkeypatch.setattr(child.urllib.request, "urlopen", lambda url, timeout: Answer())

    assert child.fetch_pinned("transcribe.py") == body


def test_a_file_that_does_not_match_its_pin_is_refused(monkeypatch):
    class Answer:
        def __enter__(self):
            return self

        def __exit__(self, *rest):
            return False

        def read(self):
            return b"# tampered\n"

    monkeypatch.setattr(child.urllib.request, "urlopen", lambda url, timeout: Answer())

    with pytest.raises(ValueError, match="does not match its pin"):
        child.fetch_pinned("transcribe.py")


def test_the_transcriber_is_written_once_and_reused(monkeypatch, tmp_path):
    body = b"# script\n"
    for name in child.TRANSCRIBER_FILES:
        monkeypatch.setitem(child.TRANSCRIBER_FILES, name, child.blob_sha1(body))
    fetched = []
    monkeypatch.setattr(child, "fetch_pinned", lambda name: fetched.append(name) or body)

    first = child.install_transcriber(tmp_path)
    second = child.install_transcriber(tmp_path)

    assert first == second and (first / "transcribe.py").read_bytes() == body
    assert fetched == ["transcribe.py", "abc_tools.py", "common.py"]


def test_transcription_refuses_a_job_without_audio(tmp_path):
    with pytest.raises(ValueError, match="Upload reference audio"):
        child.transcribe({"reference_audio": ""}, tmp_path)


def fake_ffmpeg(monkeypatch, tmp_path):
    module = types.ModuleType("imageio_ffmpeg")
    binary = tmp_path / "ffmpeg"
    binary.write_text("")
    monkeypatch.setattr(module, "get_ffmpeg_exe", lambda: str(binary), raising=False)
    monkeypatch.setitem(sys.modules, "imageio_ffmpeg", module)


def test_transcription_runs_the_pinned_script_and_reads_the_score(monkeypatch, tmp_path):
    fake_ffmpeg(monkeypatch, tmp_path)
    hub = types.ModuleType("huggingface_hub")
    downloads = []
    monkeypatch.setattr(hub, "snapshot_download", lambda *a, **k: downloads.append(a), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "transcribe.py").write_text("# script\n")
    monkeypatch.setattr(child, "install_transcriber", lambda extras: scripts)
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        output = Path(command[command.index("--output") + 1])
        output.mkdir(parents=True)
        (output / "score.abc").write_text("X:1\n")
        (output / "transcription_manifest.json").write_text('{"status": "complete", "warnings": []}')
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(child.subprocess, "run", run)

    score, extra = child.transcribe({"reference_audio": base64.b64encode(b"audio").decode()}, tmp_path)

    assert score == "X:1\n"
    assert extra["artifacts"][0]["name"] == "score.abc"
    assert calls[0][:2] == [sys.executable, str(scripts / "transcribe.py")]
    assert "--device" in calls[0] and downloads


def test_a_failed_transcription_reports_the_last_line(monkeypatch, tmp_path):
    fake_ffmpeg(monkeypatch, tmp_path)
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "snapshot_download", lambda *a, **k: [], raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "transcribe.py").write_text("# script\n")
    monkeypatch.setattr(child, "install_transcriber", lambda extras: scripts)
    monkeypatch.setattr(
        child.subprocess, "run", lambda command, **kwargs: SimpleNamespace(returncode=2, stderr="boom\n", stdout="")
    )

    with pytest.raises(ValueError, match="Transcription failed: boom"):
        child.transcribe({"reference_audio": base64.b64encode(b"audio").decode()}, tmp_path)


def test_a_transcribe_job_returns_the_score_only(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "transcribe", lambda job, extras: ("X:1\n", {"transcription": {}}))

    reply = child.run(Mock(), {"mode": "transcribe", "reference_audio": "YQ=="}, tmp_path)

    assert reply == {"wav": "", "score": "X:1\n", "metadata": {"transcription": {}, "mode": "transcribe"}}


def transcription_job(audio=b"reference", **overrides):
    return {"mode": "transcribe", "reference_audio": base64.b64encode(audio).decode(), **overrides}


def test_a_worker_reuses_a_transcription_for_the_same_audio_and_task(monkeypatch, tmp_path):
    transcriber = Mock(return_value=("X:1\n", {"transcription": {"warnings": []}}))
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(FakePipe(), tmp_path)

    first = worker.run(transcription_job(seed=1))
    second = worker.run(transcription_job(seed=2, style="different style", transcription_task="melody-full"))

    assert transcriber.call_count == 1
    assert first["score"] == second["score"] == "X:1\n"
    assert first["metadata"] == second["metadata"] == {"transcription": {"warnings": []}, "mode": "transcribe"}


def test_a_worker_keys_transcription_on_decoded_audio_bytes(monkeypatch, tmp_path):
    transcriber = Mock(return_value=("X:1\n", {}))
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(FakePipe(), tmp_path)
    first = transcription_job()
    wrapped = {**first, "reference_audio": first["reference_audio"] + "\n"}

    worker.run(first)
    reply = worker.run(wrapped)

    transcriber.assert_called_once()
    assert reply["metadata"] == {"mode": "transcribe"}


@pytest.mark.parametrize("changed", [{"audio": b"other reference"}, {"transcription_task": "full"}])
def test_a_worker_keeps_only_its_latest_transcription(monkeypatch, tmp_path, changed):
    transcriber = Mock(return_value=("X:1\n", {}))
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(FakePipe(), tmp_path)

    worker.run(transcription_job())
    miss = worker.run(transcription_job(**changed))
    evicted = worker.run(transcription_job())

    assert transcriber.call_count == 3
    assert miss["metadata"] == evicted["metadata"] == {"mode": "transcribe"}


def test_transcription_metadata_cannot_mutate_the_cached_result(monkeypatch, tmp_path):
    original = {"transcription": {"warnings": ["original"]}, "artifacts": [{"name": "score.abc"}]}
    transcriber = Mock(return_value=("X:1\n", original))
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(FakePipe(), tmp_path)

    first = worker.run(transcription_job())
    first["metadata"]["transcription"]["warnings"].append("caller change")
    first["metadata"]["artifacts"][0]["name"] = "changed"
    original["transcription"]["warnings"].append("source change")
    second = worker.run(transcription_job())

    assert second["metadata"]["transcription"]["warnings"] == ["original"]
    assert second["metadata"]["artifacts"][0]["name"] == "score.abc"


def test_a_failed_transcription_is_retried_and_does_not_retain_an_old_entry(monkeypatch, tmp_path):
    transcriber = Mock(side_effect=[("X:1\n", {}), ValueError("decode failed"), ("X:2\n", {})])
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(FakePipe(), tmp_path)

    worker.run(transcription_job())
    with pytest.raises(ValueError, match="decode failed"):
        worker.run(transcription_job(b"bad reference"))
    reply = worker.run(transcription_job())

    assert transcriber.call_count == 3
    assert reply["score"] == "X:2\n"
    assert reply["metadata"] == {"mode": "transcribe"}


def test_a_new_worker_has_no_previous_transcription(monkeypatch, tmp_path):
    transcriber = Mock(return_value=("X:1\n", {}))
    monkeypatch.setattr(child, "transcribe", transcriber)

    child.Worker(FakePipe(), tmp_path).run(transcription_job())
    reply = child.Worker(FakePipe(), tmp_path).run(transcription_job())

    assert transcriber.call_count == 2
    assert reply["metadata"] == {"mode": "transcribe"}


def test_a_cover_reuses_transcription_without_changing_generation_inputs(monkeypatch, tmp_path):
    pipe = FakePipe()
    fake_modules(monkeypatch, pipe=pipe)
    transcriber = Mock(return_value=("X:1\n", {}))
    monkeypatch.setattr(child, "transcribe", transcriber)
    worker = child.Worker(pipe, tmp_path)

    worker.run(transcription_job())
    reply = worker.run(transcription_job(mode="cover", style="piano", lyrics="la", seed=7))
    generated = worker.run(job())

    transcriber.assert_called_once()
    assert reply["metadata"] == {"mode": "cover", "cot": "melody"}
    assert pipe.requests[0][1]["abc"] == "X:1"
    assert pipe.requests[0][1]["style"] == "piano"
    assert pipe.requests[0][1]["lyrics"] == "la"
    assert len(pipe.requests) == 2
    assert "transcription_cache_hit" not in generated["metadata"]


def test_the_child_loop_retains_only_one_worker_cache(monkeypatch, capsys):
    fake_modules(monkeypatch, pipe=FakePipe())
    transcriber = Mock(return_value=("X:1\n", {}))
    monkeypatch.setattr(child, "transcribe", transcriber)
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join([json.dumps(transcription_job())] * 2)))

    assert child.main() == 0

    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    transcriber.assert_called_once()
    assert replies[0] == replies[1] == {"wav": "", "score": "X:1\n", "metadata": {"mode": "transcribe"}}


def test_a_cover_job_sings_the_transcribed_score(monkeypatch, tmp_path):
    monkeypatch.setattr(child, "transcribe", lambda job, extras: ("X:1\n", {"transcription": {"status": "complete"}}))
    pipe = Mock()
    pipe.return_value = SimpleNamespace(audio=[[0.0, 0.0]], abc="X:1\n", truncated={})

    child.run(
        pipe,
        {
            "mode": "cover",
            "style": "pop",
            "lyrics": "la",
            "seed": 7,
            "reference_audio": "YQ==",
            "transcription_task": "full",
        },
        tmp_path,
    )

    request = pipe.call_args.kwargs
    assert request["abc"] == "X:1" and request["cot"] == "full"


def test_the_reference_extension_follows_its_bytes():
    assert child.audio_suffix(b"RIFF....") == ".wav"
    assert child.audio_suffix(b"ID3....") == ".mp3"
    assert child.audio_suffix(b"OggS....") == ".ogg"
    assert child.audio_suffix(b"fLaC....") == ".flac"
    assert child.audio_suffix(b"????") == ".bin"


def test_a_half_written_manifest_reads_as_no_pack(tmp_path, capsys):
    """An interrupted write leaves half a JSON file. Reading it as absent rebuilds, which
    is what the owner wanted; reading it as a pack fails every start after it."""
    (tmp_path / "pack.json").write_text('{"format": 1, "layers": [', encoding="utf-8")

    assert child.read_manifest(tmp_path) is None
    assert "built again" in capsys.readouterr().err


def test_a_pack_that_dies_while_it_is_written_is_not_published(monkeypatch, tmp_path):
    fake_modules(monkeypatch)
    model = FakeModel(quantized_linears())
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "pack.json").write_text('{"format": 1, "old": true}', encoding="utf-8")

    def explode(tensors, path):
        raise OSError("the disk went away")

    monkeypatch.setattr(sys.modules["safetensors.torch"], "save_file", explode, raising=False)

    with pytest.raises(OSError, match="the disk went away"):
        child.write_pack(model, directory, {"layers": ["model.layers.0.mlp.gate_proj"], "block_size": 16})

    assert json.loads((directory / "pack.json").read_text(encoding="utf-8"))["old"] is True


def test_the_pack_names_the_snapshot_the_model_resolves_to(monkeypatch, tmp_path):
    snapshot = tmp_path / "models--m-a-p--YuE2-3B" / "snapshots" / "abc123"
    snapshot.mkdir(parents=True)
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("m-a-p/YuE2-3B") == "abc123"


def test_a_local_checkpoint_is_named_by_its_file_list(tmp_path):
    folder = tmp_path / "checkpoint"
    folder.mkdir()
    (folder / "model.safetensors").write_bytes(b"1234")
    first = child.source_revision(str(folder))
    (folder / "model.safetensors").write_bytes(b"12345")

    assert first.startswith("local:")
    assert child.source_revision(str(folder)) != first


def test_a_model_this_machine_cannot_name_reports_unknown():
    assert child.source_revision("org/model-that-is-not-cached") == "unknown"


def test_a_cache_with_two_snapshots_is_not_named_after_one(monkeypatch, tmp_path):
    for commit in ("abc123", "def456"):
        (tmp_path / "models--m-a-p--YuE2-3B" / "snapshots" / commit).mkdir(parents=True)
    constants = types.ModuleType("huggingface_hub.constants")
    monkeypatch.setattr(constants, "HF_HUB_CACHE", str(tmp_path), raising=False)
    package = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(package, "constants", constants, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", package)
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)

    assert child.source_revision("m-a-p/YuE2-3B") == "unknown"


def test_a_machine_without_the_cache_still_names_a_local_folder(monkeypatch, tmp_path):
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


def test_a_matching_manifest_without_its_weights_is_rebuilt(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    manifest = {**child.expected_manifest("m-a-p/YuE2-3B"), "layers": ["layer"]}
    (directory / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1, "a manifest without weights is not a pack"


def test_a_pack_from_another_snapshot_is_rebuilt(monkeypatch, tmp_path):
    """The repository id can point at a branch that moved. A pack built from the snapshot
    that is here now must not be served for weights that changed under the same name."""
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    monkeypatch.setattr(child, "source_revision", lambda model_name: "abc123")
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "weights.safetensors").write_bytes(b"")
    (directory / "pack.json").write_text(
        json.dumps({**child.expected_manifest("m-a-p/YuE2-3B"), "source": "def456", "layers": ["layer"]}),
        encoding="utf-8",
    )

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1, "a pack from another snapshot is not this model's"


def test_the_source_is_the_snapshot_the_cache_points_at(monkeypatch, tmp_path):
    """Two cached snapshots used to report `unknown`, so a pack built from one revision
    could serve the other."""
    root = tmp_path / "models--m-a-p--YuE2-3B"
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

    assert child.source_revision("m-a-p/YuE2-3B") == "bbb222"


def test_a_manifest_that_is_not_an_object_reads_as_no_pack(tmp_path, capsys):
    (tmp_path / "pack.json").write_text('"text"', encoding="utf-8")

    assert child.read_manifest(tmp_path) is None
    assert "not a pack manifest" in capsys.readouterr().err


def test_a_matching_manifest_whose_weights_changed_size_is_rebuilt(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "weights.safetensors").write_bytes(b"truncated")
    manifest = {
        **child.expected_manifest("m-a-p/YuE2-3B"),
        "layers": ["layer"],
        "files": {"weights.safetensors": 0},
    }
    (directory / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1


def test_a_pack_that_will_not_load_is_moved_aside_and_built_once(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "weights.safetensors").write_bytes(b"")
    manifest = {
        **child.expected_manifest("m-a-p/YuE2-3B"),
        "layers": ["layer"],
        "files": {"weights.safetensors": 0},
    }
    (directory / "pack.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setattr(child, "load_file", lambda path: (_ for _ in ()).throw(ValueError("truncated")), raising=False)
    monkeypatch.setattr(child, "empty_model", lambda model_dir: model)

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1
    assert list(tmp_path.glob(f"{directory.name}.corrupt-*")), "the bad pack is kept out of the way"
    assert (directory / "pack.json").is_file(), "a fresh pack is published in its place"


def test_a_pack_that_does_not_name_its_files_is_built_again(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    directory = tmp_path / "m-a-p--YuE2-3B"
    directory.mkdir()
    (directory / "weights.safetensors").write_bytes(b"")
    (directory / "pack.json").write_text(
        json.dumps({**child.expected_manifest("m-a-p/YuE2-3B"), "layers": ["layer"]}), encoding="utf-8"
    )

    child.load_packed("m-a-p/YuE2-3B", tmp_path)

    assert len(recorded["quantized"]) == 1


def test_a_cache_that_names_no_snapshot_is_unknown(monkeypatch, tmp_path):
    root = tmp_path / "models--m-a-p--YuE2-3B"
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

    assert child.source_revision("m-a-p/YuE2-3B") == "unknown"


def test_quarantine_leaves_a_missing_pack_alone(tmp_path):
    child.quarantine(tmp_path / "absent")

    assert not (tmp_path / "absent").exists()


def test_a_pack_left_under_its_old_name_is_put_back(tmp_path):
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
    lock.write_text("4194303")

    with child.pack_lock(tmp_path / "pack"):
        assert lock.is_file()

    assert not lock.exists()


def test_a_second_builder_waiting_uses_what_the_first_published(monkeypatch, tmp_path):
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    recorded = fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    monkeypatch.setattr(child, "serve_packed", lambda pipe, directory, manifest: "served")
    reasons = iter(["there is no readable pack", None])
    monkeypatch.setattr(child, "pack_state", lambda directory, expected: next(reasons, None))

    assert child.load_packed("m-a-p/YuE2-3B", tmp_path) == "served"
    assert recorded["quantized"] == []


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
    model = FakeModel(quantized_linears())
    pipe = FakePipe(model=model)
    fake_modules(monkeypatch, pipe=pipe, model=model)
    monkeypatch.setattr(sys.modules["torch"], "__version__", "2.15.0", raising=False)
    monkeypatch.setattr(child, "pack_state", lambda directory, expected: None)

    def refuse(*_):
        raise ValueError("the weights are truncated")

    monkeypatch.setattr(child, "serve_packed", refuse)

    with pytest.raises(ValueError, match="truncated"):
        child.load_packed("m-a-p/YuE2-3B", tmp_path)


def test_the_running_check_answers_for_this_process_and_a_dead_one():
    import os

    assert child._running(os.getpid()) is True
    assert child._running(4194303) is False
    assert child._running(1) is True, "another user's process is there, we just may not signal it"
