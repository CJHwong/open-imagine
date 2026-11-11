import runpy
import sys
from pathlib import Path
from types import ModuleType

import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image.minimax_h3_image_child import run_stage


@pytest.mark.parametrize("stage", ["text", "references", "dit", "vae"])
@pytest.mark.parametrize("as_script", [False, True])
def test_one_stage_runs_and_the_dit_stage_reports_each_finished_step(monkeypatch, capsys, stage, as_script):
    calls = {}

    def module(name, **members):
        value = ModuleType(name)
        value.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    def denoise(path, text, width, height, seed, resident=True, refs=(), tags=None, progress=None):
        calls["denoise"] = (path, text, width, height, seed, resident, refs, tags)
        calls["hook"] = progress
        if progress:
            progress(1, 0.5)
            progress(2, 0.4)
        return "latent", None

    dit = module("h3_image_mlx.dit", denoise=denoise)

    def main(stage, work):
        calls["main"] = (stage, work)
        if stage == "dit":
            # As the engine does: read the function at call time and pass no hook.
            calls["returned"] = dit.denoise("dit.safetensors", "embedding", 1024, 576, 7, True, [], "tags")

    stages = module("h3_image_mlx._stage", main=main)
    module("h3_image_mlx", _stage=stages, dit=dit)
    module("mlx", core=module("mlx.core", get_peak_memory=lambda: 123))
    if as_script:
        monkeypatch.setattr(sys, "argv", ["minimax_h3_image_child.py", stage, "/work"])
        runpy.run_path(run_stage.__code__.co_filename, run_name="__main__")
    else:
        run_stage(stage, "/work")
    assert calls["main"] == (stage, Path("/work"))
    output = capsys.readouterr().err
    assert f'"type": "result", "stage": "{stage}"' in output
    assert '"engine_seconds":' in output and '"peak_memory_bytes": 123' in output
    if stage == "dit":
        assert calls["denoise"] == ("dit.safetensors", "embedding", 1024, 576, 7, True, [], "tags")
        assert calls["returned"] == ("latent", None)
        assert output.count('"type": "step"') == 2
        assert 'H3_IMAGE_EVENT {"type": "step", "step": 1}' in output
        assert 'H3_IMAGE_EVENT {"type": "step", "step": 2}' in output
    else:
        assert dit.denoise is denoise and '"type": "step"' not in output
