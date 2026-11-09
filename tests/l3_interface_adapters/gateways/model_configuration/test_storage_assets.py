"""Providers declare only their own configured assets, including hidden models."""

from types import SimpleNamespace

from studio.l3_interface_adapters.gateways.model_catalog.registry import BUILTIN_PROVIDERS
from studio.l3_interface_adapters.gateways.model_catalog.storage_definitions import storage_definitions
from studio.l3_interface_adapters.gateways.model_configuration.storage_assets import configured_asset, runtime_asset
from studio.l3_interface_adapters.gateways.video.ltx23.storage_assets import storage_assets


def config(sections):
    return SimpleNamespace(backend=lambda name: sections.get(name, {}))


def test_configured_defaults_and_runtime():
    empty = config({})
    assert configured_asset(empty, "model", "path", "Weights") == ()
    assert configured_asset(empty, "model", "path", "Weights", "/weights")[0].location == "/weights"
    assert runtime_asset(empty, "model") == ()
    full = config({"model": {"python_path": "/runtime/bin/python"}})
    assert runtime_asset(full, "model")[0].location == "/runtime"


def test_every_builtin_declares_storage_without_loading_an_engine():
    settings = {
        name: {
            "model_dir": "/weights/" + name,
            "engine_dir": "/engines/" + name,
            "python_path": "/engines/" + name + "/bin/python",
            "lora_path": "/weights/distill",
            "vae_dir": "/weights/vae",
            "transcription_cache_dir": "/weights/transcription",
            "model_ltx25": "/weights/ltx25",
            "model_ltx23": "org/checkpoint",
        }
        for name in (
            "qwen21_turbo",
            "flux2",
            "flux3",
            "krea2",
            "viggle_turbo",
            "yue2",
            "drama3",
            "minimax_h3",
            "mlx_video",
        )
    }
    for provider in BUILTIN_PROVIDERS:
        assert provider.storage_assets is not None
        provider.storage_assets(config({}))
        assert provider.storage_assets(config(settings))
    assert storage_assets(config({"mlx_video": {"model_ltx23": "~/weights"}}))[0].source == "directory"
    assert storage_assets(config({"mlx_video": {"model_ltx23": "custom/repo"}}))[0].location == "custom/repo"


def test_installed_checkpoint_paths_are_protected_without_importing_plugins():
    plugins = SimpleNamespace(ids=lambda kind: ("custom",) if kind == "image" else ())
    providers = [
        SimpleNamespace(backend_id="builtin", storage_name="", kind="image", storage_assets=lambda cfg: ()),
        SimpleNamespace(storage_assets=None),
    ]
    definitions = storage_definitions(providers, plugins, config({"custom": {"model_dir": "/weights", "pack_dir": ""}}))
    assert definitions[0] == ("builtin", "builtin", "image", ())
    assert definitions[1][3][0].kind == "protected"


def test_configured_lora_paths_are_protected_without_parsing_engine_options():
    from studio.l3_interface_adapters.gateways.model_catalog.storage_definitions import protected_model_paths

    providers = [SimpleNamespace(backend_id="a"), SimpleNamespace(backend_id="b")]
    plugins = SimpleNamespace(ids=lambda kind: ("plugin",) if kind == "image" else ())
    settings = config(
        {
            "a": {"loras": [{"path": "/user/lora"}, {"path": ""}, {"path": 1}, {}, 42]},
            "b": {"loras": "invalid"},
            "plugin": {"loras": [{"path": "/user/custom"}]},
        }
    )
    assert protected_model_paths(providers, plugins, settings) == ("/user/lora", "/user/custom")
