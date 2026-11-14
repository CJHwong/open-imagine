import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import construction
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.construction import (
    DEFAULT_MODEL,
    PROVIDER,
    minimax_h3_image_cuda_backend,
)


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


def test_the_provider_names_the_cuda_engine():
    assert PROVIDER.engine == "cuda"
    assert PROVIDER.backend_id == "minimax_h3_image_cuda"


def test_the_command_runs_the_child_through_uv_with_nvfp4(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = minimax_h3_image_cuda_backend(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-4:] == ["--model", DEFAULT_MODEL, "--quantize", "nvfp4"]


def test_an_unknown_quantize_is_refused_by_name(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    with pytest.raises(ModelConfigurationError, match=r"quantize is 'int4'"):
        minimax_h3_image_cuda_backend(Config({"quantize": "int4"}))


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)

    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        minimax_h3_image_cuda_backend(Config({}))
