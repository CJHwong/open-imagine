import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.video.ltx25_cuda import construction
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.construction import (
    DEFAULT_MODEL,
    PROVIDER,
    ltx25_cuda_backend,
)


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


def test_the_provider_names_the_cuda_engine_and_the_video_kind():
    assert PROVIDER.engine == "cuda" and PROVIDER.kind == "video"
    assert PROVIDER.backend_id == "ltx25_cuda"


def test_the_command_runs_the_child_on_312_with_the_model(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")
    gateway = ltx25_cuda_backend(Config({}))
    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-2:] == ["--model", DEFAULT_MODEL]


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)
    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        ltx25_cuda_backend(Config({}))
