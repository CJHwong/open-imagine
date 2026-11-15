import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.qwen21_cuda import construction
from studio.l3_interface_adapters.gateways.image.qwen21_cuda.construction import (
    DEFAULT_MODEL,
    PROVIDER,
    qwen21_cuda_backend,
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
    assert PROVIDER.backend_id == "qwen21_turbo_cuda"


def test_the_entry_runs_bf16(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = qwen21_cuda_backend(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-4:] == ["--model", DEFAULT_MODEL, "--quantize", "bf16"]
    assert gateway.capabilities().badge == "bf16"
    assert gateway.capabilities().name == "Qwen-Image-2.1-Turbo (CUDA)"
    assert PROVIDER.resident_gib == 41.0


def test_the_section_can_name_another_checkpoint_and_bf16(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = qwen21_cuda_backend(Config({"model": "me/my-pack", "quantize": "bf16"}))

    assert gateway._child._command[-4:] == ["--model", "me/my-pack", "--quantize", "bf16"]
    assert gateway.capabilities().badge == "bf16"


def test_an_unknown_quantize_is_refused_by_name(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    with pytest.raises(ModelConfigurationError, match=r"quantize is 'int8'"):
        qwen21_cuda_backend(Config({"quantize": "int8"}))


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)

    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        qwen21_cuda_backend(Config({}))


def test_the_launcher_prefers_the_parents_uv(monkeypatch):
    monkeypatch.setenv("UV", "/from/parent/uv")

    assert construction.uv_launcher() == "/from/parent/uv"


def test_a_studio_without_uv_env_falls_back_to_path(monkeypatch):
    monkeypatch.delenv("UV", raising=False)
    monkeypatch.setattr(construction.shutil, "which", lambda name: "/usr/bin/uv")
    assert construction.uv_launcher() == "/usr/bin/uv"
