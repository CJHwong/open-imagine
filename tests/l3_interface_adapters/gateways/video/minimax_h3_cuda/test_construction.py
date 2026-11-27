import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda import construction
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.construction import PROVIDER, minimax_h3_cuda_backend
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.storage_assets import (
    DEFAULT_MODEL,
    FLASH_MODEL,
    flash_storage_assets,
    storage_assets,
)


class Config:
    def __init__(self, section):
        self._section = section

    def backend(self, backend_id):
        return self._section

    def required(self, backend_id, key):
        return self._section[key]


def test_the_provider_names_the_cuda_engine_the_video_kind_and_its_storage():
    assert (PROVIDER.backend_id, PROVIDER.kind, PROVIDER.engine) == ("minimax_h3_cuda", "video", "cuda")
    assert PROVIDER.storage_name == "MiniMax H3"
    assert [asset.location for asset in storage_assets(Config({}))] == [DEFAULT_MODEL]


def test_the_command_runs_the_child_with_the_model_and_a_pinned_revision_only_when_set(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")
    command = minimax_h3_cuda_backend(Config({}))._child._command
    assert command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert command[-2:] == ["--model", DEFAULT_MODEL]
    command = minimax_h3_cuda_backend(Config({"model": "me/h3", "revision": "abc"}))._child._command
    assert command[-4:] == ["--model", "me/h3", "--revision", "abc"]


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)
    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        minimax_h3_cuda_backend(Config({}))
    monkeypatch.setenv("UV", "/opt/uv")
    assert construction.uv_launcher() == "/opt/uv"


def test_flash_runs_the_same_child_with_its_flag_and_owns_only_its_transformers(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")
    gateway = construction.minimax_h3_flash_cuda_backend(Config({"model": "me/h3"}))
    assert gateway._child._command[-3:] == ["--model", "me/h3", "--flash"]
    assert gateway.capabilities().backend_id == "minimax_h3_flash_cuda"
    provider = construction.FLASH_PROVIDER
    assert (provider.backend_id, provider.kind, provider.engine) == ("minimax_h3_flash_cuda", "video", "cuda")
    assert provider.storage_name == "HyperFlow H3 Flash" and provider.resident_gib == 43.1
    assert [asset.location for asset in flash_storage_assets(Config({}))] == [DEFAULT_MODEL, FLASH_MODEL]
