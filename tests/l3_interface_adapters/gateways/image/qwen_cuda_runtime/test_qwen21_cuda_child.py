import io
import json
import sys
import types
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from studio.l3_interface_adapters.gateways.image.qwen_cuda_runtime import qwen21_cuda_child as child


class FakeImage:
    width, height = 8, 6

    def __init__(self):
        self.saved = None

    def save(self, buffer, format):
        self.saved = format
        buffer.write(b"png-bytes")


class EmptyModule:
    def __init__(self):
        self.compiled = []

    def compile_repeated_blocks(self, **options):
        self.compiled.append(options)

    def parameters(self):
        return []

    def buffers(self):
        return []


class FakePipe:
    def __init__(self):
        self.device = None
        self.calls = []
        self.transformer = EmptyModule()
        self.text_encoder = EmptyModule()
        self.vae = EmptyModule()

    def to(self, device):
        self.device = device
        return self

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        kwargs["callback_on_step_end"](self, 0, None, {})
        return SimpleNamespace(images=[FakeImage()])


def fake_torch(monkeypatch, available=True):
    torch = types.ModuleType("torch")
    monkeypatch.setattr(torch, "bfloat16", "bfloat16", raising=False)
    monkeypatch.setattr(
        torch,
        "cuda",
        SimpleNamespace(is_available=lambda: available, synchronize=Mock(), empty_cache=Mock()),
        raising=False,
    )
    monkeypatch.setattr(
        torch, "Generator", lambda device: SimpleNamespace(seed=None, manual_seed=lambda seed: seed), raising=False
    )
    monkeypatch.setitem(sys.modules, "torch", torch)
    return torch


def fake_diffusers(monkeypatch, pipe):
    module = types.ModuleType("diffusers")
    monkeypatch.setattr(
        module, "QwenImage21Pipeline", SimpleNamespace(from_pretrained=lambda model, **kwargs: pipe), raising=False
    )
    monkeypatch.setitem(sys.modules, "diffusers", module)


def fake_torchao(monkeypatch, record):
    quantize = types.ModuleType("torchao.quantization")
    monkeypatch.setattr(
        quantize, "quantize_", lambda model, config: record.append(("quantize", model, config)), raising=False
    )

    class Config:
        pass

    config = types.ModuleType("torchao.prototype.mx_formats")
    monkeypatch.setattr(config, "NVFP4DynamicActivationNVFP4WeightConfig", Config, raising=False)
    package = types.ModuleType("torchao")
    prototype = types.ModuleType("torchao.prototype")
    monkeypatch.setitem(sys.modules, "torchao", package)
    monkeypatch.setitem(sys.modules, "torchao.quantization", quantize)
    monkeypatch.setitem(sys.modules, "torchao.prototype", prototype)
    monkeypatch.setitem(sys.modules, "torchao.prototype.mx_formats", config)


def test_load_quantizes_the_transformer_and_reports_ready(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    loaded = child.load("me/pack", "nvfp4")

    assert loaded is pipe
    assert pipe.device == "cuda"
    assert recorded[0][1] is pipe.transformer
    assert "loaded me/pack as nvfp4" in capsys.readouterr().err


def test_load_keeps_bf16_when_asked(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    recorded = []
    fake_torchao(monkeypatch, recorded)

    assert child.load("me/pack", "bf16") is pipe
    assert recorded == []


def test_load_compiles_the_bf16_transformer_for_every_size_and_prompt(monkeypatch):
    """Static, the compile ran out of recompiles by the second size and fell back to eager;
    dynamic, 1024 took 8.9 s against 11.3 s eager on the DGX Spark."""
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    fake_torchao(monkeypatch, [])

    child.load("me/pack", "bf16")

    assert pipe.transformer.compiled == [{"fullgraph": False, "dynamic": True}]


def test_load_leaves_the_nvfp4_transformer_uncompiled(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    fake_torchao(monkeypatch, [])

    child.load("me/pack", "nvfp4")

    assert pipe.transformer.compiled == []


def test_an_unknown_quantizer_stops_the_child(monkeypatch):
    fake_torch(monkeypatch)
    fake_diffusers(monkeypatch, FakePipe())

    with pytest.raises(SystemExit, match="nvfp4 or bf16"):
        child.load("me/pack", "int8")


def test_a_run_reports_steps_and_returns_png_bytes(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()

    reply = child.run(pipe, {"prompt": "a fox", "height": 512, "width": 768, "steps": 3, "seed": 9, "guidance": 2.5})

    assert reply["width"] == 8 and reply["height"] == 6 and reply["steps"] == 3
    assert reply["png_base64"] == "cG5nLWJ5dGVz"
    call = pipe.calls[0]
    assert (call["prompt"], call["height"], call["width"], call["num_inference_steps"]) == ("a fox", 512, 768, 3)
    assert call["negative_prompt"] is None and call["true_cfg_scale"] == 2.5
    assert "step 1/3" in capsys.readouterr().err


def test_main_refuses_a_host_without_cuda(monkeypatch, capsys):
    fake_torch(monkeypatch, available=False)
    monkeypatch.setattr(sys, "argv", ["child"])

    assert child.main() == 2
    assert "CUDA is not available" in capsys.readouterr().err


def test_main_answers_each_line_and_survives_a_failed_job(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    fake_diffusers(monkeypatch, pipe)
    monkeypatch.setattr(sys, "argv", ["child", "--quantize", "bf16"])
    jobs = [
        json.dumps({"prompt": "a fox", "height": 8, "width": 8, "steps": 1, "seed": 1}),
        "",
        json.dumps({"prompt": "no steps"}),
    ]
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs)))

    assert child.main() == 0

    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert "png_base64" in lines[0]
    assert lines[1]["error"].startswith("KeyError")
    # Each job, the failed one too, hands the cached memory back.
    assert sys.modules["torch"].cuda.empty_cache.call_count == 2


class FakeTensor:
    def __init__(self, name):
        self.name = name
        self.clones = 0
        self.device = "cpu"

    def clone(self):
        self.clones += 1
        return FakeTensor(self.name + "-clone")

    def to(self, device):
        self.device = device
        return self

    def data_ptr(self):
        return id(self)


class Holder:
    def __init__(self, tensor):
        self.data = tensor


class Module:
    def __init__(self, parameters, buffers=()):
        self._parameters = list(parameters)
        self._buffers = list(buffers)

    def parameters(self):
        return self._parameters

    def buffers(self):
        return self._buffers


def test_move_by_way_of_memory_clones_once_and_keeps_shared_storage_shared():
    shared = FakeTensor("tied")
    alone = FakeTensor("alone")
    buffer = FakeTensor("rotary")
    module = Module([Holder(shared), Holder(shared), Holder(alone)], [Holder(buffer)])

    child.move_by_way_of_memory(module, "cuda")

    assert shared.clones == 1 and alone.clones == 1 and buffer.clones == 1
    first, second, third = module.parameters()
    assert first.data is second.data
    assert first.data is not third.data
    assert module.buffers()[0].data.name == "rotary-clone"
    assert first.data.device == "cuda"


def test_the_script_enters_through_its_main_guard(monkeypatch):
    """The `__main__` guard is the path uv runs, so prove it answers."""
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])

    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")

    assert exited.value.code == 0


def test_local_snapshot_prefers_the_cached_directory(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pack"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")
    (root / "snapshots" / "abc123").mkdir(parents=True)

    assert child.local_snapshot("me/pack") == str(root / "snapshots" / "abc123")


def test_local_snapshot_keeps_an_id_that_is_not_cached(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)

    assert child.local_snapshot("me/pack") == "me/pack"


def test_local_snapshot_keeps_an_id_whose_snapshot_is_gone(monkeypatch, tmp_path):
    hub = types.ModuleType("huggingface_hub")
    monkeypatch.setattr(hub, "constants", SimpleNamespace(HF_HUB_CACHE=str(tmp_path)), raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    root = tmp_path / "models--me--pack"
    (root / "refs").mkdir(parents=True)
    (root / "refs" / "main").write_text("abc123")

    assert child.local_snapshot("me/pack") == "me/pack"


def png():
    import base64

    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (4, 3), "red").save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_an_edit_run_sends_every_reference_as_an_image(monkeypatch, capsys):
    fake_torch(monkeypatch)
    pipe = FakePipe()
    encoded = png()

    reply = child.run(
        pipe,
        {
            "mode": "edit",
            "prompt": "make it night",
            "output_resolution": 1024,
            "steps": 2,
            "seed": 4,
            "guidance": 1.0,
            "references": [encoded, encoded],
        },
    )

    assert reply["steps"] == 2 and reply["png_base64"] == "cG5nLWJ5dGVz"
    call = pipe.calls[0]
    assert [image.size for image in call["image"]] == [(4, 3), (4, 3)]
    assert call["true_cfg_scale"] == 1.0 and call["output_resolution"] == 1024
    assert "height" not in call and "width" not in call
    assert "step 1/2" in capsys.readouterr().err


class StartPipe(FakePipe):
    """A pipeline that records how a starting image reaches it. The latents are numbers,
    so the mix of noise and picture can be read back."""

    vae_scale_factor = 16

    def __init__(self, sample_sigmas):
        super().__init__()
        self.config = SimpleNamespace(sample_sigmas=sample_sigmas)
        self.vae = SimpleNamespace(dtype="bfloat16")
        self.seen = {}
        pipe = self

        class Scheduler:
            def __init__(self):
                self.config = {"base_image_seq_len": 256}
                self.sigmas = None

            def set_timesteps(self, sigmas, device, mu):
                pipe.seen["mu"] = mu
                # A shift the start level must follow: every level halves.
                self.sigmas = [level / 2 for level in sigmas] + [0.0]

        class Pixels:
            def unsqueeze(self, axis):
                pipe.seen["unsqueeze"] = axis
                return self

            def to(self, device, dtype):
                pipe.seen["pixels_on"] = (device, dtype)
                return "pixels"

        class Processor:
            def preprocess(self, picture, width, height):
                pipe.seen["preprocess"] = (picture.mode, picture.size, width, height)
                return Pixels()

        self.scheduler = Scheduler()
        self.image_processor = Processor()

    def _encode_vae_image(self, pixels, generator):
        self.seen["encoded"] = pixels
        return SimpleNamespace(shape=(1, 16, 1, 3, 2))

    def _pack_latents(self, encoded, batch, channels, rows, columns):
        import numpy as np

        self.seen["packed"] = (batch, channels, rows, columns)
        return np.full((1, rows * columns, channels), 2.0)


def fake_start_engine(monkeypatch):
    import contextlib

    import numpy as np

    torch = fake_torch(monkeypatch)
    monkeypatch.setattr(torch, "no_grad", contextlib.nullcontext, raising=False)
    monkeypatch.setattr(torch, "randn", lambda shape, generator, device, dtype: np.full(shape, 10.0), raising=False)
    shifts = []
    module = types.ModuleType("diffusers.pipelines.qwenimage21.pipeline_qwenimage21")
    monkeypatch.setattr(module, "calculate_shift", lambda *arguments: shifts.append(arguments) or 0.7, raising=False)
    for name in ("diffusers", "diffusers.pipelines", "diffusers.pipelines.qwenimage21"):
        monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return shifts


def start_job(strength, **extra):
    return {
        "prompt": "a blue bike",
        "height": 528,
        "width": 800,
        "steps": 8,
        "seed": 2,
        "start": png(),
        "strength": strength,
        **extra,
    }


def test_a_starting_image_skips_the_head_of_the_checkpoints_schedule(monkeypatch, capsys):
    shifts = fake_start_engine(monkeypatch)
    table = [1.0, 0.98, 0.95, 0.93, 0.9, 0.85, 0.7, 0.41]
    pipe = StartPipe(table)

    reply = child.run(pipe, start_job(0.4))

    call = pipe.calls[0]
    # int(8 * 0.4) = 3 steps skipped, so five run, from the table's fourth level.
    assert call["sigmas"] == table[3:] and call["num_inference_steps"] == 5 and reply["steps"] == 5
    assert "step 1/5" in capsys.readouterr().err
    # The pipeline floors 528x800 to its 32 grid; the picture is encoded at that frame.
    assert (call["height"], call["width"]) == (512, 800)
    assert pipe.seen["preprocess"] == ("RGBA", (4, 3), 800, 512) and pipe.seen["unsqueeze"] == 2
    assert pipe.seen["pixels_on"] == ("cuda", "bfloat16") and pipe.seen["encoded"] == "pixels"
    assert pipe.seen["packed"] == (1, 16, 3, 2)
    # The shift is the one the pipeline computes for this frame's token count.
    assert shifts[0][0] == (512 // 16) * (800 // 16) and pipe.seen["mu"] == 0.7
    # Noise and picture mix at the shifted level of the first step kept: 0.93 / 2.
    level = 0.465
    assert call["latents"].shape == (1, 6, 16)
    assert abs(float(call["latents"][0, 0, 0]) - (level * 10.0 + (1 - level) * 2.0)) < 1e-9


def test_a_starting_image_runs_at_least_one_step_and_skips_at_least_one(monkeypatch):
    fake_start_engine(monkeypatch)
    table = [1.0, 0.9, 0.7, 0.4]

    full = StartPipe(table)
    child.run(full, start_job(1.0))
    faint = StartPipe(table)
    child.run(faint, start_job(0.05))

    assert full.calls[0]["sigmas"] == [0.4]
    assert faint.calls[0]["sigmas"] == [0.9, 0.7, 0.4]


def test_a_starting_image_follows_a_line_where_the_checkpoint_has_no_table(monkeypatch):
    fake_start_engine(monkeypatch)
    pipe = StartPipe(None)

    child.run(pipe, start_job(0.5, steps=4))

    assert [round(level, 4) for level in pipe.calls[0]["sigmas"]] == [0.5, 0.25]


def test_generate_without_a_starting_image_leaves_the_schedule_to_the_pipeline(monkeypatch):
    fake_torch(monkeypatch)
    pipe = FakePipe()

    child.run(pipe, {"prompt": "a fox", "height": 500, "width": 768, "steps": 8, "seed": 1})

    call = pipe.calls[0]
    assert "sigmas" not in call and "latents" not in call and call["height"] == 480
