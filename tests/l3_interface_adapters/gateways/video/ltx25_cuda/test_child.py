import io
import json
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.video.ltx25_cuda import ltx25_cuda_child as child


class EmptyModule:
    def parameters(self):
        return []

    def buffers(self):
        return []


class FakePipe:
    def __init__(self):
        self.transformer: object = EmptyModule()
        self.text_encoder = EmptyModule()
        self.connectors = EmptyModule()
        self.vae = EmptyModule()
        self.device = None
        self.calls = []
        self.components = {
            "transformer": self.transformer,
            "text_encoder": self.text_encoder,
            "connectors": self.connectors,
            "vae": self.vae,
            "scheduler": SimpleNamespace(),
        }

    def to(self, device):
        self.device = device
        return self

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        callback = kwargs.get("callback_on_step_end")
        if callback is not None:
            for index in range(child.DISTILLED_STEPS):
                callback(self, index, None, {})
        return ([[np.zeros((2, 2, 3), dtype=np.uint8)]], None, None, None)


class FakeWriter:
    def __init__(self, buffer):
        self.buffer = buffer

    def append_data(self, frame):
        pass

    def close(self):
        self.buffer.write(b"mp4-bytes")


def fake_world(monkeypatch, pipe, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch, "cuda", SimpleNamespace(is_available=lambda: available, synchronize=Mock()), raising=False
    )
    monkeypatch.setattr(
        torch, "Generator", lambda device=None: SimpleNamespace(manual_seed=lambda seed: seed), raising=False
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    diffusers = types.ModuleType("diffusers")
    monkeypatch.setattr(
        diffusers, "LTX2DFRPipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "diffusers", diffusers)

    imageio = types.ModuleType("imageio")

    class PathWriter:
        def __init__(self, path):
            self.path = path

        def append_data(self, frame):
            pass

        def close(self):
            self.path.write_bytes(b"mp4-bytes")

    v2 = types.ModuleType("imageio.v2")
    monkeypatch.setattr(v2, "get_writer", lambda path, **kwargs: PathWriter(pathlib.Path(path)), raising=False)
    monkeypatch.setitem(sys.modules, "imageio", imageio)
    monkeypatch.setitem(sys.modules, "imageio.v2", v2)


def test_prepare_environment_sets_ptxas_only_when_present(monkeypatch, tmp_path):
    ptxas = tmp_path / "ptxas"
    ptxas.write_text("")
    monkeypatch.setattr(child, "PTXAS", ptxas)
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    child.prepare_environment()
    assert child.os.environ["TRITON_PTXAS_PATH"] == str(ptxas)
    assert child.os.environ["HF_HUB_DISABLE_XET"] == "1"

    monkeypatch.setattr(child, "PTXAS", tmp_path / "absent")
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    child.prepare_environment()
    assert "TRITON_PTXAS_PATH" not in child.os.environ


def test_move_by_way_of_memory_clones_a_group_once_and_lands_it():
    """One round trip per group of aliased weights, and the aliases keep sharing it."""

    class Tensor:
        def __init__(self):
            self.clones = 0
            self.device = None

        def clone(self):
            self.clones += 1
            return Tensor()

        def to(self, device):
            self.device = device
            return self

        def data_ptr(self):
            return id(self)

    shared = Tensor()
    a, b = SimpleNamespace(data=shared), SimpleNamespace(data=shared)

    child.move_by_way_of_memory(SimpleNamespace(parameters=lambda: [a, b], buffers=lambda: []))

    assert shared.clones == 1
    assert a.data is b.data
    assert a.data.device == "cuda"


def test_load_materializes_and_moves_to_the_device(monkeypatch, capsys):
    pipe = FakePipe()
    fake_world(monkeypatch, pipe)
    assert child.load("me/pack") is pipe
    assert pipe.device == "cuda"
    assert "loaded me/pack" in capsys.readouterr().err


def test_load_sends_each_weight_through_memory_first(monkeypatch):
    log = []

    class Tensor:
        def clone(self):
            log.append("clone")
            return self

        def to(self, device):
            log.append(f"to {device}")
            return self

        def data_ptr(self):
            return 1

    pipe = FakePipe()
    moved = SimpleNamespace(parameters=lambda: [SimpleNamespace(data=Tensor())], buffers=lambda: [])
    pipe.transformer = moved
    pipe.components["transformer"] = moved
    fake_world(monkeypatch, pipe)

    child.load("me/pack")

    assert log == ["clone", "to cuda"]


def test_a_run_reports_steps_and_returns_an_mp4(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe())
    reply = child.run(
        FakePipe(), {"prompt": "a fox", "width": 768, "height": 512, "frames": 97, "frame_rate": 24, "seed": 1}
    )
    assert reply["mp4"] == "bXA0LWJ5dGVz"
    assert (reply["width"], reply["height"], reply["frames"]) == (768, 512, 1)
    assert reply["steps"] == child.DISTILLED_STEPS


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe(), available=False)
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_world(monkeypatch, FakePipe())
    monkeypatch.setattr(sys, "argv", ["child"])
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            "\n".join(
                [
                    json.dumps({"prompt": "a fox", "width": 8, "height": 8, "frames": 2, "frame_rate": 24, "seed": 1}),
                    "",
                    json.dumps({"seed": 1}),
                ]
            )
        ),
    )
    assert child.main() == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "mp4" in lines[0]
    assert lines[1]["error"].startswith("KeyError")


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0


def test_an_enhanced_run_passes_the_flag_and_a_flat_frame_list(monkeypatch):
    class Enhanced(FakePipe):
        def __call__(self, **kwargs):
            self.calls.append(kwargs)
            kwargs["callback_on_step_end"](self, 1, None, {})
            return ([np.zeros((2, 2, 3), dtype=np.uint8)], np.zeros((4, 2)), None, None)

    pipe = Enhanced()
    fake_world(monkeypatch, pipe)
    reply = child.run(
        pipe, {"prompt": "a fox", "width": 8, "height": 8, "frames": 1, "frame_rate": 24, "seed": 1, "enhance": True}
    )
    assert pipe.calls[0]["enable_prompt_enhancement"] is True
    assert reply["frames"] == 1


def test_load_skips_a_component_the_pipeline_does_not_carry(monkeypatch):
    pipe = FakePipe()
    del pipe.connectors
    fake_world(monkeypatch, pipe)
    assert child.load("me/pack") is pipe
    assert pipe.device == "cuda"


def test_unpack_handles_an_array_and_a_nested_list():
    import numpy as np

    array = np.zeros((1, 3, 4, 4, 3), dtype=np.uint8)
    assert child.unpack(array).shape == (3, 4, 4, 3)
    assert len(child.unpack([np.zeros((2, 2, 3))])) == 1
    nested = [[np.zeros((2, 2, 3)), np.zeros((2, 2, 3))]]
    assert len(child.unpack(nested)) == 2
    assert len(child.unpack(np.zeros((3, 4, 4, 3), dtype=np.uint8))) == 3
