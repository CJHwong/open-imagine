import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.voice.drama3_cuda import construction
from studio.l3_interface_adapters.gateways.voice.drama3_cuda.construction import (
    DEFAULT_CHECKPOINT,
    PROVIDER,
    voice_drama_cuda_backend,
)


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


def test_the_provider_names_the_cuda_engine_and_the_voice_kind():
    assert PROVIDER.engine == "cuda" and PROVIDER.kind == "voice"
    assert PROVIDER.backend_id == "drama3_cuda"


def test_the_command_runs_the_child_on_python_312_with_the_checkpoint(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = voice_drama_cuda_backend(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-2:] == ["--checkpoint", DEFAULT_CHECKPOINT]


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)
    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        voice_drama_cuda_backend(Config({}))
