from pathlib import Path
from unittest.mock import Mock

import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.construction import (
    build_rewriter,
    minimax_h3_image_backend,
)
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.h3_image_pe_rewriter import H3ImagePeRewriter
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        try:
            return self._section[key]
        except KeyError:
            raise ModelConfigurationError(f"[{backend_id}] needs {key}") from None


def test_the_backend_reads_its_weights_at_int8_only():
    gateway = minimax_h3_image_backend(Config({"model_dir": "/weights"}), execute_process=Mock())
    assert gateway._model_dir == "/weights"
    with pytest.raises(ModelConfigurationError, match="runs its weights at int8"):
        minimax_h3_image_backend(Config({"model_dir": "/weights", "quantize": 4}), execute_process=Mock())
    assert minimax_h3_image_backend(Config({"model_dir": "/weights", "quantize": 8}), execute_process=Mock())


def test_a_lora_table_is_refused():
    with pytest.raises(ModelConfigurationError, match="takes no LoRAs"):
        minimax_h3_image_backend(Config({"model_dir": "/weights", "loras": [{"id": "x"}]}), execute_process=Mock())


def test_a_studio_without_a_pack_offers_no_rewrite_toggle():
    assert isinstance(build_rewriter(Config({}), "minimax_h3_image"), NoPromptRewriterGateway)


def test_a_named_pack_runs_the_child_on_the_studios_uv(monkeypatch):
    monkeypatch.setenv("UV", "/opt/uv/bin/uv")
    rewriter = build_rewriter(Config({"rewrite_model_dir": "/packs/pe"}), "minimax_h3_image")
    assert isinstance(rewriter, H3ImagePeRewriter)
    command = rewriter._child._command
    assert command[0] == "/opt/uv/bin/uv" and command[1:3] == ["run", "--script"]
    assert command[3].endswith("/h3_image_pe_child.py")
    assert command[-2:] == ["--model-dir", str(Path("/packs/pe"))]


def test_a_prompt_dir_is_passed_when_one_is_named(monkeypatch):
    monkeypatch.setenv("UV", "/opt/uv/bin/uv")
    rewriter = build_rewriter(
        Config({"rewrite_model_dir": "/packs/pe", "rewrite_prompt_dir": "/packs/prompts"}), "minimax_h3_image"
    )
    assert rewriter._child._command[-2:] == ["--prompt-dir", str(Path("/packs/prompts"))]
