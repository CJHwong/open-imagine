import base64
import contextlib
import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.image.qwen_cuda_runtime import qwen21_rewriter_cuda_child as child


class FakeTensor:
    def __init__(self, name):
        self.name, self.clones, self.device = name, 0, "cpu"

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


class FakeInputs(dict):
    def __init__(self):
        super().__init__({"input_ids": SimpleNamespace(shape=(1, 5))})
        self.device = None

    def to(self, device):
        self.device = device
        return self


class Written:
    def getitem(self, key):
        return "tokens"

    def __getitem__(self, key):
        return "tokens"


class FakeProcessor:
    def __init__(self):
        self.tokenizer = SimpleNamespace(eos_token_id=248046)
        self.messages = []
        self.images = []
        self.inputs = FakeInputs()

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        self.messages = messages
        return "formatted"

    def __call__(self, text, images, return_tensors):
        self.images = images
        return self.inputs

    def batch_decode(self, written, skip_special_tokens):
        return ["the answer"]


class FakeModel(Module):
    def __init__(self, eos=248044):
        super().__init__([Holder(FakeTensor("w"))])
        self.generation_config = SimpleNamespace(eos_token_id=eos)
        self.kwargs = {}

    def generate(self, **kwargs):
        self.kwargs = kwargs
        return Written()


def fake_torch(monkeypatch, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(is_available=lambda: available, synchronize=Mock(), empty_cache=Mock()),
        raising=False,
    )
    monkeypatch.setattr(torch, "inference_mode", contextlib.nullcontext, raising=False)
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def fake_transformers(monkeypatch, processor, model):
    module = types.ModuleType("transformers")
    monkeypatch.setattr(module, "AutoProcessor", SimpleNamespace(from_pretrained=lambda path: processor), raising=False)
    monkeypatch.setattr(
        module,
        "Qwen3_5ForConditionalGeneration",
        SimpleNamespace(from_pretrained=lambda path, **kwargs: model),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "transformers", module)


def png():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_load_sends_each_weight_through_memory(monkeypatch):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)

    assert child.load("me/t2i") == (processor, model)
    assert model.parameters()[0].data.device == "cuda"


def test_resident_keeps_the_card_that_is_already_loaded(monkeypatch):
    fake_torch(monkeypatch)
    state = {"role": "generate", "processor": Mock(), "model": Mock()}

    assert child.resident(state, "generate", {"generate": "me/t2i"}) is state


def test_resident_swaps_the_cards_and_empties_the_cache(monkeypatch, capsys):
    torch = fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)
    state = {"role": "generate", "processor": Mock(), "model": Mock()}

    swapped = child.resident(state, "edit", {"generate": "me/t2i", "edit": "me/i2i"})

    assert swapped["role"] == "edit" and swapped["model"] is model
    torch.cuda.empty_cache.assert_called()
    assert "swapping generate for edit" in capsys.readouterr().err


def test_generate_sends_the_images_and_reads_only_the_new_tokens(monkeypatch):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    encoded = png()

    reply = child.generate(
        {"processor": processor, "model": model},
        {
            "role": "edit",
            "system": "You lengthen an instruction.",
            "user": "make it night",
            "references": [encoded],
            "max_tokens": 64,
            "temperature": 0.9,
            "top_p": 0.95,
            "top_k": 20,
            "enable_thinking": False,
        },
    )

    assert reply == {"text": "the answer"}
    content = processor.messages[1]["content"]
    assert content[0] == {"type": "image"} and content[1] == {"type": "text", "text": "make it night"}
    assert len(processor.images) == 1
    assert model.kwargs["max_new_tokens"] == 64 and model.kwargs["do_sample"] is True
    assert model.kwargs["eos_token_id"] == [248044, 248046]


def test_the_answer_ends_at_the_end_of_the_turn_as_well_as_the_configured_end():
    processor = FakeProcessor()

    assert child.stop_tokens(processor, FakeModel(eos=248044)) == [248044, 248046]
    assert child.stop_tokens(processor, FakeModel(eos=[248044, 248046])) == [248044, 248046]
    assert child.stop_tokens(processor, FakeModel(eos=None)) == [248046]


def test_reference_image_decodes_a_png():
    image = child.reference_image(png())

    assert (image.size, image.mode) == ((4, 3), "RGB")


def test_move_by_way_of_memory_clones_once_and_keeps_shared_storage_shared():
    shared = FakeTensor("tied")
    module = Module([Holder(shared), Holder(shared)])

    child.move_by_way_of_memory(module, "cuda")

    assert shared.clones == 1
    first, second = module.parameters()
    assert first.data is second.data
    assert first.data.device == "cuda"


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_torch(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)
    monkeypatch.setattr(sys, "argv", ["child"])
    jobs = [
        json.dumps({"role": "generate", "system": "s", "user": "u", "request_id": "r1"}),
        "",
        json.dumps({"role": "music", "system": "s", "user": "u", "request_id": "r2"}),
        json.dumps({"role": "generate", "request_id": "r3"}),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs)))

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0] == {"text": "the answer", "request_id": "r1"}
    assert lines[1]["error"].startswith("ValueError") and lines[1]["request_id"] == "r2"
    assert lines[2]["error"].startswith("KeyError") and lines[2]["request_id"] == "r3"


def test_local_snapshot_prefers_the_cached_directory(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--t2i"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")
    (root / "snapshots" / "abc123").mkdir(parents=True)

    assert child.local_snapshot("me/t2i") == str(root / "snapshots" / "abc123")


def test_local_snapshot_keeps_an_id_that_is_not_cached(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/t2i") == "me/t2i"


def test_local_snapshot_keeps_an_id_whose_snapshot_is_gone(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--t2i"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")

    assert child.local_snapshot("me/t2i") == "me/t2i"


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")

    assert exited.value.code == 0


class FakeLinear:
    pass


def fake_torchao(monkeypatch):
    calls = []
    quantization = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(quantization, "PerRow", lambda: "per-row", raising=False)
    monkeypatch.setattr(
        quantization,
        "Float8DynamicActivationFloat8WeightConfig",
        lambda granularity, kernel_preference: ("fp8 dynamic", granularity, kernel_preference),
        raising=False,
    )
    monkeypatch.setattr(
        quantization,
        "quantize_",
        lambda weights, config, filter_fn: calls.append((weights, config, filter_fn)),
        raising=False,
    )
    preference = types.ModuleType("torchao.quantization.quantize_.common.kernel_preference")
    monkeypatch.setattr(preference, "KernelPreference", SimpleNamespace(TORCH="torch"), raising=False)
    monkeypatch.setitem(sys.modules, "torchao", types.ModuleType("torchao"))
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantization)
    monkeypatch.setitem(
        sys.modules, "torchao.quantization.quantize_", types.ModuleType("torchao.quantization.quantize_")
    )
    monkeypatch.setitem(
        sys.modules, "torchao.quantization.quantize_.common", types.ModuleType("torchao.quantization.quantize_.common")
    )
    monkeypatch.setitem(sys.modules, "torchao.quantization.quantize_.common.kernel_preference", preference)
    return calls


def test_load_at_fp8_quantizes_the_language_model_with_fp8_matrix_multiplies(monkeypatch, capsys):
    torch = fake_torch(monkeypatch)
    monkeypatch.setattr(torch, "nn", SimpleNamespace(Linear=FakeLinear), raising=False)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)
    calls = fake_torchao(monkeypatch)

    child.load("me/i2i", "fp8")

    [(weights, config, filter_fn)] = calls
    assert weights is model and config == ("fp8 dynamic", "per-row", "torch")
    assert filter_fn is child.language_linear
    assert "loaded me/i2i as fp8" in capsys.readouterr().err


def test_load_at_bf16_leaves_the_weights_alone(monkeypatch):
    fake_torch(monkeypatch)
    fake_transformers(monkeypatch, FakeProcessor(), FakeModel())
    calls = fake_torchao(monkeypatch)

    child.load("me/i2i")

    assert calls == []


def test_only_the_language_models_linear_layers_take_fp8(monkeypatch):
    torch = fake_torch(monkeypatch)
    monkeypatch.setattr(torch, "nn", SimpleNamespace(Linear=FakeLinear), raising=False)

    assert child.language_linear(FakeLinear(), "model.language_model.layers.0.mlp.up_proj")
    assert not child.language_linear(FakeLinear(), "model.visual.blocks.0.attn.qkv")
    assert not child.language_linear(FakeLinear(), "lm_head")
    assert not child.language_linear(object(), "model.language_model.norm")


def test_main_holds_the_cards_at_the_precision_it_was_given(monkeypatch, capsys):
    fake_torch(monkeypatch)
    loaded = []
    monkeypatch.setattr(child, "load", lambda model, quantize: loaded.append((model, quantize)) or (Mock(), Mock()))
    monkeypatch.setattr(child, "generate", lambda state, job: {"text": "ok"})
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "fp8"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"role": "edit", "request_id": "r1"})))

    assert child.main() == 0

    assert loaded == [("Qwen/Qwen-Image-2.1-PE-I2I", "fp8")]
