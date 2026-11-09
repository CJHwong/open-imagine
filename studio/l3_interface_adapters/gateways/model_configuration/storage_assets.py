"""Resolve provider-declared assets without inspecting other models' configuration."""

from pathlib import Path

from studio.l1_entities.model_asset import ModelAsset


def configured_asset(config, section, key, label, default="", kind="weights"):
    value = str(config.backend(section).get(key, default))
    if not value:
        return ()
    return (ModelAsset(label, value, kind),)


def runtime_asset(config, section):
    value = config.backend(section).get("python_path")
    return (ModelAsset("Runtime", str(Path(value).parent.parent), "runtime"),) if value else ()


def hub_asset(repository, label="Weights"):
    return (ModelAsset(label, repository, source="hub"),)
