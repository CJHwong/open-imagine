import os

import pytest

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import construction
from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda.construction import (
    DEFAULT_MODEL,
    DEFAULT_PACK_DIR,
    NVFP4_PROVIDER,
    PROVIDER,
    backend_factory,
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


def test_the_default_entry_runs_fp8(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = backend_factory("minimax_h3_image_cuda")(Config({}))

    assert gateway._child._command[:5] == ["/bin/uv", "run", "--python", "3.12", "--script"]
    assert gateway._child._command[-6:-2] == ["--model", DEFAULT_MODEL, "--quantize", "fp8"]
    assert gateway._child._command[-2] == "--pack-dir"
    assert gateway._child._command[-1] == os.path.expanduser(DEFAULT_PACK_DIR)
    assert gateway.capabilities().badge == "fp8"


def test_the_second_entry_runs_the_pack(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = backend_factory("minimax_h3_image_cuda_nvfp4")(Config({}))

    assert gateway._child._command[-6:-2] == ["--model", DEFAULT_MODEL, "--quantize", "nvfp4"]
    assert gateway.capabilities().backend_id == "minimax_h3_image_cuda_nvfp4"
    assert gateway.capabilities().name == "MiniMax H3-Image (CUDA, NVFP4)"
    assert NVFP4_PROVIDER.resident_gib == 40.0


def test_the_section_can_keep_its_pack_elsewhere(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = backend_factory("minimax_h3_image_cuda")(Config({"pack_dir": "~/elsewhere"}))

    assert gateway._child._command[-1] == os.path.expanduser("~/elsewhere")


def test_an_unknown_quantize_is_refused_by_name(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    with pytest.raises(ModelConfigurationError, match=r"quantize is 'int4'"):
        backend_factory("minimax_h3_image_cuda")(Config({"quantize": "int4"}))


def test_a_host_without_uv_gets_a_named_refusal(monkeypatch):
    monkeypatch.setattr(construction.shutil, "which", lambda name: None)
    monkeypatch.delenv("UV", raising=False)

    with pytest.raises(ModelConfigurationError, match="needs uv on PATH"):
        backend_factory("minimax_h3_image_cuda")(Config({}))


def test_the_section_can_name_the_prompt_enhancer(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = construction.build_rewriter(Config({"rewrite_model": "me/pe"}), "minimax_h3_image_cuda")

    assert gateway.modes() == ("generate", "edit")
    assert gateway._child._command[-4:] == ["--model", "me/pe", "--quantize", "bf16"]


def test_the_section_can_hold_the_prompt_enhancer_in_fp8(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = construction.build_rewriter(
        Config({"rewrite_model": "me/pe", "rewrite_quantize": 8}), "minimax_h3_image_cuda"
    )

    assert gateway._child._command[-2:] == ["--quantize", "fp8"]


def test_the_enhancer_refuses_a_width_it_cannot_hold(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    with pytest.raises(
        ModelConfigurationError, match=r"rewrite_quantize under \[minimax_h3_image_cuda\] must be 0 or 8"
    ):
        construction.build_rewriter(Config({"rewrite_model": "me/pe", "rewrite_quantize": 4}), "minimax_h3_image_cuda")


def test_without_the_setting_the_page_offers_no_rewrite():
    assert construction.build_rewriter(Config({}), "minimax_h3_image_cuda").modes() == ()


def test_only_the_prepare_child_may_build_a_pack(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")

    gateway = backend_factory("minimax_h3_image_cuda")(Config({}))

    assert "--may-build" not in gateway._child._command
    assert gateway._prepare_child._command == [*gateway._child._command, "--may-build"]


def test_the_pack_is_a_file_a_run_needs_unless_the_entry_runs_bf16():
    from studio.l1_entities.model_asset import ModelAsset

    assert PROVIDER.ready_assets is not None
    assert NVFP4_PROVIDER.ready_assets is not None
    folder = os.path.join(os.path.expanduser("~/packs"), DEFAULT_MODEL.replace("/", "--"))
    assert PROVIDER.ready_assets(Config({"pack_dir": "~/packs"})) == (ModelAsset("Pack", folder, "pack"),)
    assert NVFP4_PROVIDER.ready_assets(Config({"quantize": "bf16"})) == ()
