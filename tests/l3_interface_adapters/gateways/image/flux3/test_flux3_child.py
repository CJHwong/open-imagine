import json
import runpy
import sys
from types import ModuleType, SimpleNamespace

import pytest

from studio.l3_interface_adapters.gateways.image.flux3.flux3_child import generate


@pytest.mark.parametrize(
    "mode,references,expected",
    [
        ("generate", [], "generate"),
        ("generate", ["reference.png"], "edit"),
        ("edit", ["reference.png"], "edit"),
    ],
)
@pytest.mark.parametrize("as_script", [False, True])
def test_engine_native_calls_and_completed_step_progress(
    monkeypatch, capsys, tmp_path, mode, references, expected, as_script
):
    calls = {}

    class FakeModel:
        def __init__(self, **kwargs):
            calls["init"] = kwargs
            self.callbacks = SimpleNamespace(register=lambda hook: calls.update(hook=hook))

        def generate_image(self, **kwargs):
            calls["generate"] = kwargs
            calls["hook"].call_in_loop(0, 7, "caption", "latents", SimpleNamespace(num_inference_steps=16), None)
            return SimpleNamespace(image=SimpleNamespace(save=lambda path, **kwargs: calls.update(output=path)))

    class FakeGenerate(FakeModel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            calls["variant"] = "generate"

    class FakeEdit(FakeModel):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            calls["variant"] = "edit"

    def module(name, **members):
        value = ModuleType(name)
        value.__dict__.update(members)
        monkeypatch.setitem(sys.modules, name, value)
        return value

    core = module(
        "mlx.core",
        eval=lambda value: calls.update(evaluated=value),
        synchronize=lambda: None,
        get_peak_memory=lambda: 123,
    )
    module("mlx", core=core)
    module("mflux")
    module("mflux.models")
    module("mflux.models.common")
    module("mflux.models.flux3")
    module("mflux.models.common.config", ModelConfig=SimpleNamespace(flux3_image_klein=lambda: "distilled"))
    module("mflux.models.flux3.variants", Flux3Klein=FakeGenerate, Flux3KleinEdit=FakeEdit)
    request = dict(
        mode=mode,
        references=references,
        quantize=8,
        model_dir="/local/snapshot",
        seed=7,
        prompt="caption",
        width=512,
        height=512,
        steps=16,
    )
    if as_script:
        request_path = tmp_path / "request.json"
        request_path.write_text(json.dumps(request))
        monkeypatch.setattr(sys, "argv", ["flux3_child.py", str(request_path), "result.png"])
        runpy.run_path(
            generate.__code__.co_filename,
            run_name="__main__",
        )
    else:
        generate(request, "result.png")
    assert calls["variant"] == expected
    assert calls["init"] == {"model_config": "distilled", "model_path": "/local/snapshot", "quantize": 8}
    assert calls["generate"].get("image_paths", []) == references
    assert "guidance" not in calls["generate"]
    assert calls["evaluated"] == "latents"
    assert calls["output"] == "result.png"
    output = capsys.readouterr().err
    assert '"step": 1, "total": 16' in output
    assert '"peak_memory_bytes": 123' in output
    assert '"construction_seconds":' in output and '"engine_seconds":' in output
    assert '"load_seconds":' not in output
