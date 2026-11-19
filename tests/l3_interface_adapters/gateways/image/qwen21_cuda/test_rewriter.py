import base64
import io
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.qwen21_cuda import construction, rewriter
from tests.support.images import png


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


@pytest.fixture(autouse=True)
def stub_system_prompt(monkeypatch):
    """The instructions ship beside the weights; no test reads the Hub for them."""
    monkeypatch.setattr(rewriter, "system_prompt", lambda repo: f"instructions for {repo}")


def test_the_models_come_from_the_two_settings_and_none_hides_the_toggle():
    models = rewriter.rewrite_models(
        Config({"rewrite_generate_model": "me/t2i", "rewrite_edit_model": "me/i2i"}), "qwen21_turbo_cuda"
    )
    assert models == {"generate": "me/t2i", "edit": "me/i2i"}
    assert rewriter.rewrite_models(Config({"rewrite_generate_model": "me/t2i"}), "qwen21_turbo_cuda") is None


def test_the_rewrite_sends_the_instructions_the_nudge_and_the_sampling():
    child = Mock()
    child.request.return_value = {"text": '{"rewritten_prompt": "a pear, at golden hour"}'}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})
    told = []

    result = gateway.rewrite("a pear", "generate", (), lambda: told.append(1), lambda: False)

    payload = child.request.call_args[0][0]
    assert payload["role"] == "generate"
    assert payload["system"]
    assert payload["user"].endswith("Write the instruction in English.")
    assert (payload["temperature"], payload["top_p"], payload["top_k"], payload["enable_thinking"]) == (
        1.0,
        0.95,
        20,
        False,
    )
    assert told == [1]
    assert result.prompt == "a pear, at golden hour"


def test_a_reference_reaches_the_card_as_base64():
    child = Mock()
    child.request.return_value = {"text": "a longer instruction"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})

    reference = png(4, 4)

    gateway.rewrite("a pear", "edit", (reference,), lambda: None, lambda: False)

    sent = child.request.call_args[0][0]["references"]
    assert [base64.b64decode(item) for item in sent] == [reference.png]


def test_a_large_reference_reaches_the_card_smaller():
    """The card reads the picture to know what it edits, and 1 MP is enough for that."""
    child = Mock()
    child.request.return_value = {"text": "a longer instruction"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})

    gateway.rewrite("a pear", "edit", (png(2000, 1500),), lambda: None, lambda: False)

    written = base64.b64decode(child.request.call_args[0][0]["references"][0])
    with Image.open(io.BytesIO(written)) as sent:
        assert sent.size == (1155, 866)


def test_a_cjk_request_is_not_asked_for_english():
    child = Mock()
    child.request.return_value = {"text": "a longer instruction"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})

    gateway.rewrite("一顆梨子放在桌上", "generate", (), lambda: None, lambda: False)

    assert child.request.call_args[0][0]["user"] == "一顆梨子放在桌上"


def test_an_unknown_mode_is_refused_by_name():
    gateway = rewriter.Qwen21CudaRewriter(Mock(), {"generate": "me/t2i"})

    with pytest.raises(InvalidJob, match="does not serve edit"):
        gateway.rewrite("a pear", "edit", (), lambda: None, lambda: False)


def test_a_child_error_becomes_a_named_failure():
    child = Mock()
    child.request.return_value = {"error": "OutOfMemoryError: no room"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i"})

    with pytest.raises(InvalidJob, match="no room"):
        gateway.rewrite("a pear", "generate", (), lambda: None, lambda: False)


def test_release_stops_the_child_and_modes_lists_the_settings():
    child = Mock()
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})

    assert gateway.modes() == ("generate", "edit")
    gateway.release()
    child.stop.assert_called_once()


def test_the_builder_returns_the_child_gateway_when_the_section_names_both_cards(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = rewriter.build_rewriter(
        Config({"rewrite_generate_model": "me/t2i", "rewrite_edit_model": "me/i2i"}), "qwen21_turbo_cuda"
    )

    command = gateway._child._command
    assert command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert command[-6:] == ["--generate-model", "me/t2i", "--edit-model", "me/i2i", "--quantize", "bf16"]
    assert gateway.modes() == ("generate", "edit")


def test_the_builder_passes_the_rewrite_precision_the_section_names(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = rewriter.build_rewriter(
        Config({"rewrite_generate_model": "me/t2i", "rewrite_edit_model": "me/i2i", "rewrite_quantize": 8}),
        "qwen21_turbo_cuda",
    )

    assert gateway._child._command[-2:] == ["--quantize", "fp8"]


@pytest.mark.parametrize("width", [4, "fp8", True])
def test_the_builder_refuses_a_rewrite_width_the_child_cannot_hold(width):
    settings = {"rewrite_generate_model": "me/t2i", "rewrite_edit_model": "me/i2i", "rewrite_quantize": width}

    with pytest.raises(ModelConfigurationError, match=r"rewrite_quantize under \[qwen21_turbo_cuda\] must be 0 or 8"):
        rewriter.build_rewriter(Config(settings), "qwen21_turbo_cuda")


def test_the_builder_falls_back_to_no_rewriter_without_the_settings():
    gateway = rewriter.build_rewriter(Config({}), "qwen21_turbo_cuda")

    assert gateway.modes() == ()


def test_the_cache_line_names_each_mode(monkeypatch):
    monkeypatch.setattr(rewriter, "cache_line", lambda models: "Rewriters: generate cached, edit cached")

    line = rewriter.rewriter_cache(
        Config({"rewrite_generate_model": "me/t2i", "rewrite_edit_model": "me/i2i"}), "qwen21_turbo_cuda"
    )

    assert line == "Rewriters: generate cached, edit cached"
    assert rewriter.rewriter_cache(Config({}), "qwen21_turbo_cuda") == ""


def test_a_prepare_asks_each_card_for_one_token_and_then_stops_the_child():
    child = Mock()
    child.request.return_value = {"text": "x"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i", "edit": "me/i2i"})

    gateway.prepare()

    asked = [call.args[0] for call in child.request.call_args_list]
    assert [payload["role"] for payload in asked] == ["generate", "edit"]
    assert all(payload["max_tokens"] == 1 and payload["references"] == [] for payload in asked)
    child.stop.assert_called_once_with()


def test_a_card_that_cannot_load_fails_the_prepare_and_still_stops_the_child():
    child = Mock()
    child.request.return_value = {"error": "no such repo"}
    gateway = rewriter.Qwen21CudaRewriter(child, {"generate": "me/t2i"})

    with pytest.raises(InvalidJob, match="no such repo"):
        gateway.prepare()

    child.stop.assert_called_once_with()
