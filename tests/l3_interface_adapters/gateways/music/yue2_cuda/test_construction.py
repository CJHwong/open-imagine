import os

import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.music.yue2_cuda import construction
from studio.l3_interface_adapters.gateways.music.yue2_cuda.capabilities import yue2_cuda_capabilities
from studio.l3_interface_adapters.gateways.music.yue2_cuda.construction import (
    DEFAULT_MODEL,
    DEFAULT_PACK_DIR,
    NVFP4_PROVIDER,
    PROVIDER,
    backend_factory,
)

yue2_cuda_backend = backend_factory("yue2_cuda")


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
    assert PROVIDER.resident_gib == 18.1


def test_the_second_entry_runs_the_packed_build(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = backend_factory("yue2_cuda_nvfp4")(Config({}))

    assert NVFP4_PROVIDER.backend_id == "yue2_cuda_nvfp4"
    assert NVFP4_PROVIDER.engine == "cuda" and NVFP4_PROVIDER.resident_gib == 9.1
    assert gateway._child._command[-6:-2] == ["--model", DEFAULT_MODEL, "--quantize", "nvfp4"]
    assert gateway.capabilities().backend_id == "yue2_cuda_nvfp4"
    assert gateway.capabilities().name == "YuE2 (CUDA, NVFP4)"
    assert gateway.capabilities().badge == "nvfp4"


def test_the_two_entries_carry_different_estimates():
    bf16 = yue2_cuda_capabilities("yue2_cuda", "YuE2 (CUDA)", "bf16").estimate
    nvfp4 = yue2_cuda_capabilities("yue2_cuda_nvfp4", "YuE2 (CUDA, NVFP4)", "nvfp4").estimate

    assert bf16 is not None and nvfp4 is not None
    assert bf16.generate_base_seconds != nvfp4.generate_base_seconds


def test_the_command_runs_the_child_through_uv_with_the_model(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-6:-2] == ["--model", DEFAULT_MODEL, "--quantize", "bf16"]
    assert gateway._child._command[-2] == "--pack-dir"
    assert gateway._child._command[-1] == os.path.expanduser(DEFAULT_PACK_DIR)
    assert gateway.capabilities().backend_id == "yue2_cuda"
    assert gateway.capabilities().badge == "bf16"


def test_the_badge_follows_the_quantize_setting(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({"quantize": "nvfp4"}))

    assert gateway.capabilities().badge == "nvfp4"


def test_the_section_can_keep_its_pack_elsewhere(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({"pack_dir": "~/packs/yue2"}))

    assert gateway._child._command[-1] == os.path.expanduser("~/packs/yue2")


def test_the_section_can_name_another_checkpoint(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({"model": "me/my-weights"}))

    assert gateway._child._command[-6:-2] == ["--model", "me/my-weights", "--quantize", "bf16"]


def test_the_section_can_ask_for_a_narrower_language_model(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = yue2_cuda_backend(Config({"quantize": "fp8"}))

    assert gateway._child._command[-6:-2] == ["--model", DEFAULT_MODEL, "--quantize", "fp8"]


def test_a_quantizer_the_child_does_not_offer_is_refused(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    with pytest.raises(ModelConfigurationError, match="quantize"):
        yue2_cuda_backend(Config({"quantize": "q4"}))


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
