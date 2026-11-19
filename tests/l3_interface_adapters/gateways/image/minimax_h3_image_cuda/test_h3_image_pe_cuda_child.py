import base64
import contextlib
import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import h3_image_pe_cuda_child as child


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
    def __init__(self, parameters):
        self._parameters = list(parameters)

    def parameters(self):
        return self._parameters

    def buffers(self):
        return []


class FakeInputs(dict):
    def __init__(self):
        super().__init__({"input_ids": SimpleNamespace(shape=(1, 5))})

    def to(self, device):
        return self


class Written:
    def __getitem__(self, key):
        return "tokens"


class FakeProcessor:
    def __init__(self):
        self.template_content: str | list[dict[str, str]] = ""
        self.images = []
        self.inputs = FakeInputs()

    def apply_chat_template(self, messages, tokenize, add_generation_prompt, enable_thinking):
        self.template_content = messages[-1]["content"]
        return "formatted"

    def __call__(self, text, images, return_tensors):
        self.images = images or []
        self.text = text
        return self.inputs

    def batch_decode(self, written, skip_special_tokens):
        """The card continues from an opening when it was given one."""
        if self.text[0].endswith(child.CAPTION_OPENING):
            return ['a longer caption", "aspect_ratio": "3:2"}']
        return ['{"expanded_caption": "a longer caption", "aspect_ratio": "3:2", "target_aspect_ratio": "2:3"}']


class FakeModel(Module):
    def __init__(self):
        super().__init__([Holder(FakeTensor("w"))])
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
    monkeypatch.setattr(
        module, "AutoConfig", SimpleNamespace(from_pretrained=lambda path: SimpleNamespace()), raising=False
    )
    monkeypatch.setattr(module, "AutoProcessor", SimpleNamespace(from_pretrained=lambda path: processor), raising=False)
    monkeypatch.setattr(
        module,
        "Qwen3_5ForConditionalGeneration",
        SimpleNamespace(from_pretrained=lambda path, **kwargs: model),
        raising=False,
    )
    monkeypatch.setitem(sys.modules, "transformers", module)


def templates(tmp_path):
    (tmp_path / "t2i").mkdir(exist_ok=True)
    (tmp_path / "edit").mkdir(exist_ok=True)
    (tmp_path / "t2i" / "system_prompt.txt").write_text("You lengthen a request.\n", encoding="utf-8")
    (tmp_path / "t2i" / "task_prompt.txt").write_text("Request: {}", encoding="utf-8")
    (tmp_path / "edit" / "task_prompt.txt").write_text("Rewrite the instruction for these pictures.", encoding="utf-8")
    return tmp_path


def png():
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def test_load_sends_each_weight_through_memory(monkeypatch):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)

    assert child.load("me/pe") == (processor, model)
    assert model.parameters()[0].data.device == "cuda"


def test_a_generate_job_uses_the_cards_own_system_and_task_text(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()

    reply = child.generate(processor, model, {"kind": "generate", "prompt": "a pear"}, templates(tmp_path))

    assert reply == {"prompt": "a longer caption", "ratio": "3:2"}
    assert processor.template_content == "Request: a pear"
    assert processor.text == ['formatted{"expanded_caption":"']


@pytest.mark.parametrize(
    ("continuation", "caption"),
    [
        ('A poster that reads \\"Blue Hour\\" in gold.', 'A poster that reads "Blue Hour" in gold.'),
        ('A poster in gold."}', "A poster in gold."),
    ],
)
def test_a_caption_the_card_left_open_is_read_as_the_caption(monkeypatch, tmp_path, continuation, caption):
    """One poster answer in four ended its turn inside the caption string."""
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    monkeypatch.setattr(processor, "batch_decode", lambda written, skip_special_tokens: [continuation])

    reply = child.generate(processor, model, {"kind": "generate", "prompt": "a poster"}, templates(tmp_path))

    assert reply == {"prompt": caption, "ratio": None}


@pytest.mark.parametrize(
    ("continuation", "message"),
    [('a caption", "aspect_ratio": "3:2', "no JSON object"), ("   ", "an empty caption")],
)
def test_an_open_answer_that_is_not_a_caption_still_fails(monkeypatch, tmp_path, continuation, message):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    monkeypatch.setattr(processor, "batch_decode", lambda written, skip_special_tokens: [continuation])

    with pytest.raises(ValueError, match=message):
        child.generate(processor, model, {"kind": "generate", "prompt": "a pear"}, templates(tmp_path))


def test_an_edit_job_labels_each_picture_and_keeps_the_requested_ratio(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()

    reply = child.generate(
        processor,
        model,
        {"kind": "edit", "prompt": "make it night", "images": [png()], "ratio": "adaptive"},
        templates(tmp_path),
    )

    assert isinstance(processor.template_content, list)
    assert "Reference Media: <Picture 1>, aspect_ratio 4:3" in processor.template_content[-1]["text"]
    assert processor.template_content[0] == {"type": "image"}
    assert len(processor.images) == 1
    assert reply == {"prompt": "a longer caption", "ratio": "2:3"}
    assert processor.text == ["formatted"]


def test_cuda_chat_template_receives_each_image_marker_without_mutating_messages(monkeypatch):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    messages = [{"role": "system", "content": "Keep the subject."}, {"role": "user", "content": "Make it night."}]
    pictures = [object(), object()]

    child.ask(processor, model, messages, pictures)

    assert processor.template_content == [
        {"type": "image"},
        {"type": "image"},
        {"type": "text", "text": "Make it night."},
    ]
    assert processor.images == pictures
    assert messages == [
        {"role": "system", "content": "Keep the subject."},
        {"role": "user", "content": "Make it night."},
    ]


def test_an_empty_prompt_and_an_unknown_kind_are_refused(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()

    with pytest.raises(ValueError, match="Write a prompt"):
        child.generate(processor, model, {"kind": "generate", "prompt": "  "}, templates(tmp_path))
    with pytest.raises(ValueError, match="Unknown prompt-enhancer kind"):
        child.generate(processor, model, {"kind": "music", "prompt": "a pear"}, templates(tmp_path))


def test_reference_image_decodes_a_png():
    image = child.reference_image(base64.b64decode(png()))

    assert (image.size, image.mode) == ((4, 3), "RGB")


def test_move_by_way_of_memory_clones_once_and_keeps_shared_storage_shared():
    shared = FakeTensor("tied")
    module = Module([Holder(shared), Holder(shared)])

    child.move_by_way_of_memory(module, "cuda")

    assert shared.clones == 1
    first, second = module.parameters()
    assert first.data is second.data and first.data.device == "cuda"


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_torch(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys, tmp_path):
    fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)
    monkeypatch.setattr(sys, "argv", ["child", "--prompt-dir", str(templates(tmp_path))])
    jobs = [
        json.dumps({"kind": "generate", "prompt": "a pear"}),
        "",
        json.dumps({"kind": "generate", "prompt": ""}),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs)))

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert lines[0].get("prompt") == "a longer caption", lines
    assert lines[1]["error"].startswith("ValueError")


def test_main_loads_the_enhancer_at_the_precision_it_is_given(monkeypatch, tmp_path):
    fake_torch(monkeypatch)
    loaded = []
    monkeypatch.setattr(child, "load", lambda model, quantize: loaded.append((model, quantize)) or (None, None))
    monkeypatch.setattr(sys, "argv", ["child", "--prompt-dir", str(tmp_path), "--quantize", "fp8"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))

    assert child.main() == 0
    assert loaded == [("MiniMaxAI/MiniMax-H3-Image-PE", "fp8")]


def test_load_at_fp8_quantizes_the_language_model(monkeypatch):
    """bf16 held 51.0 GiB and wrote 3.6 tokens a second; fp8 held 28.4 GiB and wrote 4.4."""
    torch = fake_torch(monkeypatch)
    processor, model = FakeProcessor(), FakeModel()
    fake_transformers(monkeypatch, processor, model)
    quantized = []
    monkeypatch.setattr(child, "to_fp8", quantized.append)

    child.load("me/pe", "fp8")
    assert quantized == [model]
    child.load("me/pe")
    assert quantized == [model]
    torch.cuda.empty_cache.assert_called_once()


class Linear:
    def __init__(self, dtype="bfloat16"):
        self.weight = SimpleNamespace(dtype=dtype)


def test_fp8_takes_the_language_models_bf16_linears(monkeypatch):
    torch = fake_torch(monkeypatch)
    monkeypatch.setattr(torch, "nn", SimpleNamespace(Linear=Linear), raising=False)

    assert child.language_linear(Linear(), "model.language_model.layers.0.mlp.up_proj")
    assert not child.language_linear(Linear(), "model.visual.blocks.0.attn.qkv")
    assert not child.language_linear(Linear(), "lm_head")
    assert not child.language_linear(Linear("float32"), "model.language_model.layers.0.mlp.up_proj")
    assert not child.language_linear(SimpleNamespace(), "model.norm")


def test_to_fp8_sends_the_row_scaled_config_and_the_filter(monkeypatch):
    recorded = []
    quantization = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(quantization, "PerRow", lambda: "per-row", raising=False)
    monkeypatch.setattr(
        quantization,
        "Float8DynamicActivationFloat8WeightConfig",
        lambda granularity, kernel_preference: (granularity, kernel_preference),
        raising=False,
    )
    monkeypatch.setattr(
        quantization,
        "quantize_",
        lambda weights, config, filter_fn: recorded.append((weights, config, filter_fn)),
        raising=False,
    )
    preference = types.ModuleType("torchao.quantization.quantize_.common.kernel_preference")
    monkeypatch.setattr(preference, "KernelPreference", SimpleNamespace(TORCH="torch"), raising=False)
    monkeypatch.setitem(sys.modules, "torchao", types.ModuleType("torchao"))
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantization)
    monkeypatch.setitem(sys.modules, "torchao.quantization.quantize_.common.kernel_preference", preference)

    child.to_fp8("weights")

    assert recorded == [("weights", ("per-row", "torch"), child.language_linear)]


def test_local_snapshot_prefers_the_cached_directory(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pe"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")
    (root / "snapshots" / "abc123").mkdir(parents=True)

    assert child.local_snapshot("me/pe") == str(root / "snapshots" / "abc123")


def test_local_snapshot_keeps_an_id_that_is_not_cached(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/pe") == "me/pe"


def test_local_snapshot_keeps_an_id_whose_snapshot_is_gone(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pe"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")

    assert child.local_snapshot("me/pe") == "me/pe"


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")

    assert exited.value.code == 0
