"""Providers stay lazy, expose each workspace, and normalize external declarations."""

from unittest.mock import Mock

from studio.l2_use_cases.model_provider import ModelProvider
from studio.l2_use_cases.model_services import ModelServices
from studio.l3_interface_adapters.gateways.model_catalog.composite_model_catalog_gateway import (
    CompositeModelCatalogGateway,
)
from studio.l3_interface_adapters.gateways.model_catalog.registry import BUILTIN_PROVIDERS
from studio.l3_interface_adapters.gateways.model_catalog.rewriter_cache_status import rewriter_cache_line
from studio.l3_interface_adapters.gateways.video.ltx_runtime.rewriter_configuration import enhancer
from studio.l4_frameworks_and_drivers.config import Config
from tests.support.plugins import entry, fake_plugins, install


def test_catalog_lists_builtins_and_installed_without_loading_their_declarations(monkeypatch):
    declaration = entry("image", "example_image", fake_plugins()["image"])
    installed = install(monkeypatch, [declaration])
    catalog = CompositeModelCatalogGateway(BUILTIN_PROVIDERS, installed, Mock())
    assert catalog.ids("image")[-1] == "example_image"
    assert catalog.ids("music") == ("yue2",)
    declaration.load.assert_not_called()
    provider = catalog.provider("image", "example_image")
    assert isinstance(provider, ModelProvider) and not provider.requires_mlx
    assert provider.backend_id == "example_image" and provider.rewriter is None
    declaration.load.assert_called_once()


def test_builtin_catalog_lists_and_returns_providers_without_an_installed_catalog():
    factory = Mock()
    provider = ModelProvider("sample", "image", factory)
    catalog = CompositeModelCatalogGateway([provider], None, Mock())
    assert catalog.ids("image") == ("sample",)
    assert catalog.ids("video") == ()
    assert catalog.provider("image", "sample") is provider
    factory.assert_not_called()


def test_external_model_has_no_builtin_cache_report():
    assert rewriter_cache_line(Config("external", (), "", (), {})) == ""


def test_ltx_enhancer_is_reused_only_within_one_studio_instance():
    config = Config("", (), "", (), {})
    services = ModelServices(Mock())
    assert enhancer(config, services) is enhancer(config, services)
    assert enhancer(config, ModelServices(Mock())) is not enhancer(config, services)


def test_both_ltx_providers_recognize_their_own_rewriter_output():
    config = Config("", (), "", (), {})
    shared_enhancer = Mock(return_value="rewritten shot")
    shared_enhancer.is_enhanced.side_effect = lambda prompt, references: prompt == "rewritten shot"
    services = ModelServices(Mock(), {"ltx_prompt_enhancer": shared_enhancer})
    catalog = CompositeModelCatalogGateway(BUILTIN_PROVIDERS, None, services.run_process)
    for name in ("ltx23_mlx", "ltx25_mlx"):
        provider = catalog.provider("video", name)
        backend = provider.create(config, execute_process=services.run_process, services=services)
        rewriter = provider.rewriter(config, name, services=services)
        result = rewriter.rewrite("a shot", "generate", (), Mock(), lambda: False)
        assert backend._runner._enhanced_prompt(result.prompt, ())
        assert not backend._runner._enhanced_prompt("a different shot", ())


def test_h3_lora_configuration_does_not_inherit_ltx_engine_rules():
    config = Config(
        "",
        (),
        "minimax_h3",
        ("minimax_h3",),
        {
            "mlx_video": {"loras": [{"invalid": "belongs to another runtime"}]},
            "minimax_h3": {"loras": [{"id": "sample", "label": "Sample", "path": "/synthetic.safetensors"}]},
        },
    )
    catalog = CompositeModelCatalogGateway(BUILTIN_PROVIDERS, None, Mock())
    backend = catalog.provider("video", "minimax_h3").create(config, execute_process=Mock())
    assert tuple(lora.id for lora in backend.capabilities().loras) == ("sample",)
