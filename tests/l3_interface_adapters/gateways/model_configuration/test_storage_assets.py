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
            "minimax_h3_image",
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
        SimpleNamespace(
            backend_id="builtin", storage_name="", kind="image", storage_assets=lambda cfg: (), ready_assets=None
        ),
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


def test_a_pack_a_prepare_builds_is_listed_and_removable_with_its_model():
    """The storage list showed two rows named YuE2 at the same size: the NVFP4 entry was named
    like the bf16 one, and neither row counted a pack, so the 1.8 GB YuE2 pack and the 59 GB H3
    pack were missing from the list and could not be removed from it."""
    import os

    rows = {
        model_id: (name, assets)
        for model_id, name, _, assets in storage_definitions(
            BUILTIN_PROVIDERS, SimpleNamespace(ids=lambda kind: ()), config({})
        )
    }
    roots = {os.path.expanduser(root) for provider in BUILTIN_PROVIDERS for root in provider.storage_roots}

    assert rows["yue2_cuda"][0] == "YuE2" and rows["yue2_cuda_nvfp4"][0] == "YuE2 NVFP4"
    # A row reads as the picker does.
    assert rows["minimax_h3_image_cuda"][0] == "MiniMax H3-Image"
    for model_id, folder in (
        ("yue2_cuda_nvfp4", "~/.cache/open-imagine/yue2-nvfp4"),
        ("minimax_h3_image_cuda", "~/.cache/open-imagine/h3-pack"),
    ):
        packs = [asset for asset in rows[model_id][1] if asset.kind == "pack"]
        assert [asset.location for asset in packs] == [
            os.path.join(os.path.expanduser(folder), asset.location.rsplit("/", 1)[-1]) for asset in packs
        ] and packs
        assert os.path.expanduser(folder) in roots
    # The bf16 entry reads no pack, so its row keeps only the shared download.
    assert [asset.kind for asset in rows["yue2_cuda"][1]] == ["weights"]
