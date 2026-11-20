from unittest.mock import Mock

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


def test_the_backend_and_its_rewriter_share_one_child_in_a_studio(monkeypatch):
    """The enhancer lives in the video child, so a second child would load the video model twice."""
    from studio.l2_use_cases.model_services import ModelServices
    from studio.l3_interface_adapters.gateways.video.ltx25_cuda.rewriter import Ltx25CudaRewriter

    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")
    assert PROVIDER.rewriter is not None
    services = ModelServices(run_process=Mock())

    backend = ltx25_cuda_backend(Config({}), services=services)
    rewriter = PROVIDER.rewriter(Config({}), "ltx25_cuda", services=services)

    assert isinstance(rewriter, Ltx25CudaRewriter)
    assert rewriter._child is backend._child
    assert rewriter._rewritten is backend._rewritten
    other = ltx25_cuda_backend(Config({}), services=ModelServices(run_process=Mock()))
    assert other._child is not backend._child


def test_without_a_studio_each_build_gets_its_own_child(monkeypatch):
    monkeypatch.setattr(construction, "uv_launcher", lambda: "/bin/uv")
    assert PROVIDER.rewriter is not None
    rewriter = PROVIDER.rewriter(Config({}), "ltx25_cuda")
    assert rewriter._child is not ltx25_cuda_backend(Config({}))._child
