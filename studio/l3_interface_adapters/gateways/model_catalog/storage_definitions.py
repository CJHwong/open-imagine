"""Collect built-in assets and conservatively protect installed checkpoint paths."""

from studio.l1_entities.model_asset import ModelAsset


def storage_definitions(providers, plugins, config):
    definitions = [
        (
            provider.backend_id,
            provider.storage_name or provider.backend_id,
            provider.kind,
            provider.storage_assets(config),
        )
        for provider in providers
        if provider.storage_assets is not None
    ]
    for kind in ("image", "video", "voice"):
        for name in plugins.ids(kind):
            settings = config.backend(name)
            # The public plugin API does not declare ownership. Never delete its configured checkpoints.
            assets = tuple(
                ModelAsset("Installed checkpoint", str(settings[key]), "protected")
                for key in ("model_dir", "pack_dir")
                if settings.get(key)
            )
            definitions.append((name, name, kind, assets))
    return definitions


def protected_model_paths(providers, plugins, config):
    """User LoRAs are references, never owned model downloads."""
    names = [provider.backend_id for provider in providers]
    names.extend(name for kind in ("image", "video", "voice") for name in plugins.ids(kind))
    paths = []
    for name in names:
        entries = config.backend(name).get("loras", [])
        if not isinstance(entries, list):
            continue
        paths.extend(
            entry["path"]
            for entry in entries
            if isinstance(entry, dict) and isinstance(entry.get("path"), str) and entry["path"]
        )
    return tuple(paths)
