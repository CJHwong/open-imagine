import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.music.yue2_cuda import construction
from studio.l3_interface_adapters.gateways.music.yue2_cuda.construction import (
    DEFAULT_MODEL,
    PROVIDER,
    yue2_cuda_backend,
)


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


def test_the_provider_names_the_cuda_engine_and_the_music_kind():
    assert PROVIDER.engine == "cuda" and PROVIDER.kind == "music"
    assert PROVIDER.backend_id == "yue2_cuda"


def test_the_command_runs_the_child_through_uv_with_the_model(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-2:] == ["--model", DEFAULT_MODEL]
    assert gateway.capabilities().backend_id == "yue2_cuda"


def test_the_section_can_name_another_checkpoint(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({"model": "me/my-weights"}))

    assert gateway._child._command[-2:] == ["--model", "me/my-weights"]


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)

    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        yue2_cuda_backend(Config({}))


def test_the_launcher_prefers_the_parents_uv(monkeypatch):
    monkeypatch.setenv("UV", "/from/parent/uv")
    assert construction.uv_launcher() == "/from/parent/uv"


def test_a_studio_without_uv_env_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(construction.shutil, "which", lambda name: "/usr/bin/uv")
    assert construction.uv_launcher() == "/usr/bin/uv"
