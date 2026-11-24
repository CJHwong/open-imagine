import base64
import io
import json
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
from PIL import Image

from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda import minimax_h3_cuda_child as child


def fake_module(name: str, **attributes) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def png(color=(255, 0, 0), size=(8, 8)) -> str:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


class Linear:
    def __init__(self, dtype="bfloat16"):
        self.weight = SimpleNamespace(dtype=dtype)


class Module:
    """A component: named submodules, no weights, and a record of the hooks it was given."""

    def __init__(self, layers=None):
        self.layers = layers or {}
        self.hooks = []
        self.lm_head = "head"
        self.model = SimpleNamespace(language_model=SimpleNamespace(layers=list(range(64))))

    def named_modules(self):
        return list(self.layers.items())

    def parameters(self):
        return []

    def buffers(self):
        return []

    def register_forward_pre_hook(self, hook):
        self.hooks.append(hook)


class FakePipe:
    text_encoder_layer = 50
    audio_sampling_rate = 32000
    component_names = (
        "image_processor",
        "text_encoder",
        "tokenizer",
        "vae",
        "audio_vae",
        "transformer_ref",
        "transformer",
    )

    def __init__(self):
        self.components = {}
        self.loads = []
        self.calls = []

    def load_components(self, names, dtype, device_map):
        self.loads.append(tuple(names))
        for name in names:
            linears = {"block.linear": Linear(), "visual.proj": Linear(), "norm": Linear("float32")}
            self.components[name] = Module(linears if name in child.QUANTIZED else None)

    def update_components(self, **components):
        self.components.update(components)

    def __getattr__(self, name):
        if name in self.__dict__.get("components", {}):
            return self.components[name]
        raise AttributeError(name)

    def __call__(self, **arguments):
        self.calls.append(arguments)
        for _ in range(arguments["num_inference_steps"] - 1):
            for hook in self.components["transformer"].hooks:
                hook()
        frames = [Image.new("RGB", (arguments["width"], arguments["height"])) for _ in range(arguments["num_frames"])]
        return {"videos": [frames], "audio": ["generated sound"], "sampling_rate": 32000}


@pytest.fixture
def world(monkeypatch, tmp_path):
    """Every engine package the child imports, faked, and a record of what each was asked."""
    record = SimpleNamespace(quantized=[], encoded=[], downloads=[], pipe=FakePipe(), hub=tmp_path / "hub")

    torch = fake_module(
        "torch",
        bfloat16="bfloat16",
        nn=SimpleNamespace(Linear=Linear, Identity=lambda: "identity"),
        cuda=SimpleNamespace(is_available=lambda: True, synchronize=Mock(), empty_cache=Mock()),
        Generator=lambda: SimpleNamespace(manual_seed=lambda seed: ("generator", seed)),
        from_numpy=lambda array: ("tensor", array.shape),
    )
    monkeypatch.setitem(sys.modules, "torch", torch)

    mx = fake_module("torchao.prototype.mx_formats", NVFP4DynamicActivationNVFP4WeightConfig=lambda: "nvfp4")
    quantization = fake_module(
        "torchao.quantization", quantize_=lambda layer, config: record.quantized.append((layer, config))
    )
    for name, module in (
        ("torchao", types.ModuleType("torchao")),
        ("torchao.prototype", types.ModuleType("torchao.prototype")),
        ("torchao.prototype.mx_formats", mx),
        ("torchao.quantization", quantization),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    diffusers = fake_module("diffusers", ModularPipeline=SimpleNamespace(from_pretrained=lambda path: record.pipe))
    references = fake_module(
        "diffusers.modular_pipelines.minimax_h3",
        MiniMaxH3ImageReference=lambda image: ("picture", image.size),
        MiniMaxH3AudioReference=lambda audio, sample_rate: ("track", audio, sample_rate),
    )

    def encode_video(frames, fps, output_path, audio, audio_sample_rate):
        record.encoded.append((len(frames), fps, audio, audio_sample_rate))
        Path(output_path).write_bytes(b"mp4")

    exporter = fake_module("diffusers.utils.export_utils", encode_video=encode_video)
    for name, module in (
        ("diffusers", diffusers),
        ("diffusers.modular_pipelines", types.ModuleType("diffusers.modular_pipelines")),
        ("diffusers.modular_pipelines.minimax_h3", references),
        ("diffusers.utils", types.ModuleType("diffusers.utils")),
        ("diffusers.utils.export_utils", exporter),
    ):
        monkeypatch.setitem(sys.modules, name, module)

    def snapshot_download(model, revision, allow_patterns):
        record.downloads.append((model, revision, tuple(allow_patterns)))
        return "/downloaded"

    hub = fake_module(
        "huggingface_hub",
        constants=SimpleNamespace(HF_HUB_CACHE=str(record.hub)),
        snapshot_download=snapshot_download,
    )
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setattr(child, "move_by_way_of_memory", lambda module, device="cuda": None)
    return record


def fake_av(monkeypatch, planes, frames=1):
    """PyAV with `frames` decoded frames, each resampled to `planes`, then the flush."""

    class Container:
        def __init__(self, source):
            self.source = source

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def decode(self, audio):
            return ["frame"] * frames if planes is not None else []

    class Resampler:
        def __init__(self, format, layout, rate):
            self.settings = (format, layout, rate)

        def resample(self, frame):
            if planes is None:
                return []
            if frame is None:
                return [SimpleNamespace(to_ndarray=lambda: planes[:, :1] * 0)]
            return [SimpleNamespace(to_ndarray=lambda: planes)]

    monkeypatch.setitem(sys.modules, "av", fake_module("av", open=Container, AudioResampler=Resampler))


def test_prepare_environment_sets_ptxas_only_when_present(monkeypatch, tmp_path):
    monkeypatch.delenv("TRITON_PTXAS_PATH", raising=False)
    monkeypatch.delenv("HF_HUB_DISABLE_XET", raising=False)
    monkeypatch.setattr(child, "PTXAS", tmp_path / "absent")
    child.prepare_environment()
    assert "TRITON_PTXAS_PATH" not in child.os.environ
    assert child.os.environ["HF_HUB_DISABLE_XET"] == "1"
    (tmp_path / "ptxas").write_text("")
    monkeypatch.setattr(child, "PTXAS", tmp_path / "ptxas")
    child.prepare_environment()
    assert child.os.environ["TRITON_PTXAS_PATH"] == str(tmp_path / "ptxas")


def test_the_pinned_snapshot_is_used_from_the_cache_without_the_hub(world):
    cached = world.hub / "models--MiniMaxAI--MiniMax-H3" / "snapshots" / "abc"
    (cached / "transformer").mkdir(parents=True)
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc") == "/downloaded"
    assert world.downloads[0][:2] == ("MiniMaxAI/MiniMax-H3", "abc")
    assert "transformer_ref/*" in world.downloads[0][2]
    (cached / "transformer_ref").mkdir()
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc") == str(cached)
    assert len(world.downloads) == 1


def test_a_local_folder_is_read_as_it_is(world, tmp_path):
    assert child.snapshot(str(tmp_path), "abc") == str(tmp_path)
    assert world.downloads == []


def test_component_reads_an_attribute_then_the_mapping():
    assert child.component(SimpleNamespace(vae="vae", components={}), "vae") == "vae"
    assert child.component(SimpleNamespace(components={"vae": "mapped"}), "vae") == "mapped"


def test_move_by_way_of_memory_lands_a_group_once_and_skips_what_is_there():
    class Tensor:
        def __init__(self, device="cpu"):
            self.device = SimpleNamespace(type=device)
            self.clones = 0

        def clone(self):
            self.clones += 1
            return self

        def to(self, device):
            return Tensor(device)

        def data_ptr(self):
            return id(self)

    shared, landed = Tensor(), Tensor("cuda")
    first, second, third = (SimpleNamespace(data=shared), SimpleNamespace(data=shared), SimpleNamespace(data=landed))
    module = SimpleNamespace(parameters=lambda: [first, second], buffers=lambda: [third])

    child.move_by_way_of_memory(module)

    assert shared.clones == 1
    assert first.data is second.data and first.data.device.type == "cuda"
    assert third.data is landed


def test_land_in_nvfp4_quantizes_bf16_linears_and_keeps_the_named_ones(world):
    module = Module({"block.linear": Linear(), "visual.proj": Linear(), "norm": Linear("float32"), "act": object()})
    child.land_in_nvfp4(module, kept=("visual",))
    assert world.quantized == [(module.layers["block.linear"], "nvfp4")]


def test_load_takes_one_large_component_at_a_time_and_hooks_both_transformers(world, capsys):
    pipe = child.load("MiniMaxAI/MiniMax-H3", "/local")

    assert pipe is world.pipe
    assert pipe.loads == [
        ("image_processor", "tokenizer", "vae", "audio_vae"),
        ("text_encoder",),
        ("transformer",),
        ("transformer_ref",),
    ]
    encoder = pipe.components["text_encoder"]
    assert len(encoder.model.language_model.layers) == 51 and encoder.lm_head == "identity"
    assert all(len(pipe.components[name].hooks) == 1 for name in child.TRANSFORMERS)
    # The encoder keeps its vision tower in bf16; the transformers have none to keep.
    quantized = [layer for layer, _ in world.quantized]
    assert encoder.layers["visual.proj"] not in quantized and encoder.layers["block.linear"] in quantized
    assert all(pipe.components[name].layers["visual.proj"] in quantized for name in child.TRANSFORMERS)
    assert {config for _, config in world.quantized} == {"nvfp4"}
    assert "loaded MiniMaxAI/MiniMax-H3" in capsys.readouterr().err


def test_flash_reads_everything_but_the_base_transformers_and_its_own_pinned_pair(world):
    """Flash never loads the 124 GB of base transformers, so it neither fetches them nor waits
    for them in the cache."""
    assert not {pattern.split("/")[0] for pattern in child.SHARED} & set(child.TRANSFORMERS)
    assert "text_encoder/*" in child.SHARED and "vae/*" in child.SHARED
    cached = world.hub / "models--MiniMaxAI--MiniMax-H3" / "snapshots" / "abc"
    (cached / "text_encoder").mkdir(parents=True)
    # An interrupted download that left only the encoder is fetched again.
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc", child.SHARED, child.SHARED_FOLDERS) == "/downloaded"
    (cached / "vae").mkdir()
    (cached / "audio_vae").mkdir()
    assert child.snapshot("MiniMaxAI/MiniMax-H3", "abc", child.SHARED, child.SHARED_FOLDERS) == str(cached)
    assert (
        child.snapshot(child.FLASH_MODEL, child.FLASH_REVISION, child.FLASH_WEIGHTS, ("fl2va_bf16",)) == "/downloaded"
    )
    assert world.downloads == [
        ("MiniMaxAI/MiniMax-H3", "abc", child.SHARED),
        (child.FLASH_MODEL, child.FLASH_REVISION, child.FLASH_WEIGHTS),
    ]


@pytest.fixture
def flash(world, monkeypatch):
    """Flash's package, faked: its block swap, its transformer and a record of what it loaded."""

    class Blocks:
        def init_pipeline(self, path):
            world.built = path
            return world.pipe

    world.swaps = dict(child.FLASH_SWAPS)

    def swap(blocks, counts):
        counts.update(world.swaps)

    class LowRankLinear:
        pass

    class Transformer(Module):
        source: tuple = ()

        @classmethod
        def from_pretrained(cls, path, subfolder, torch_dtype):
            pair = LowRankLinear()
            model = cls(
                {
                    "blocks.0.attn.to_q": pair,
                    "blocks.0.attn.to_q.down": Linear(),
                    "blocks.0.attn.to_q.up": Linear(),
                    "blocks.0.attn.to_k": Linear(),
                    "blocks.0.adaln_proj.linear": Linear(),
                    "norm_out.linear": Linear(),
                }
            )
            model.source = path, subfolder, torch_dtype
            return model

    def pad(model, multiple):
        model.padded = multiple

    monkeypatch.setattr(sys.modules["diffusers.modular_pipelines.minimax_h3"], "MiniMaxH3Blocks", Blocks, raising=False)
    for name, module in (
        ("hyperflow_h3_flash", types.ModuleType("hyperflow_h3_flash")),
        ("hyperflow_h3_flash.blocks", fake_module("hyperflow_h3_flash.blocks", _swap=swap)),
        (
            "hyperflow_h3_flash.transformer",
            fake_module(
                "hyperflow_h3_flash.transformer",
                HyperFlowH3FlashTransformer3DModel=Transformer,
                LowRankLinear=LowRankLinear,
                set_lowrank_rank_multiple=pad,
            ),
        ),
    ):
        monkeypatch.setitem(sys.modules, name, module)
    asked = []
    monkeypatch.setattr(
        child, "snapshot", lambda model, revision, patterns, needed: asked.append((model, needed)) or f"/{model}"
    )
    world.asked = asked
    return world


def test_flash_loads_its_own_transformers_and_keeps_its_small_layers_in_bf16(flash, capsys):
    pipe = child.load("MiniMaxAI/MiniMax-H3", "abc", flash=True)

    assert flash.built == "/MiniMaxAI/MiniMax-H3"
    assert flash.asked == [
        ("MiniMaxAI/MiniMax-H3", child.SHARED_FOLDERS),
        (child.FLASH_MODEL, ("fl2va_bf16", "ref2va_bf16")),
    ]
    # The base transformers are never loaded; Flash's land in their place, from its pinned pair.
    assert pipe.loads == [("image_processor", "tokenizer", "vae", "audio_vae"), ("text_encoder",)]
    for name, folder in child.FLASH_FOLDERS.items():
        model = pipe.components[name]
        assert model.source == ("/" + child.FLASH_MODEL, folder, "bfloat16") and model.padded == 8
        assert len(model.hooks) == 1
        quantized = [layer for layer, _ in flash.quantized]
        assert model.layers["blocks.0.attn.to_k"] in quantized
        kept = ("blocks.0.attn.to_q.down", "blocks.0.attn.to_q.up", "blocks.0.adaln_proj.linear", "norm_out.linear")
        assert not [part for part in kept if model.layers[part] in quantized]
    assert f"loaded {child.FLASH_MODEL}" in capsys.readouterr().err


def test_flash_refuses_to_load_when_its_swap_no_longer_matches(flash):
    """`_swap` is Flash's private code: a release that swaps other blocks would sample wrongly."""
    flash.swaps = {"set_timesteps": 3, "denoiser": 2}
    with pytest.raises(RuntimeError, match=r"replaced .* blocks, where this child expects"):
        child.load("m", "abc", flash=True)


def test_a_run_counts_the_calls_its_job_names(world, capsys):
    """Flash takes six steps as six calls, where base diffusers takes six as five. The fake pipe
    makes base diffusers' five calls; the total it reports against is the job's."""
    pipe = child.load("m", "/local")
    child.run(pipe, {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 6, "forwards": 6, "seed": 0})
    assert "step 5/6" in capsys.readouterr().err


def test_main_passes_the_flash_flag_to_the_loader(world, monkeypatch):
    seen = []
    monkeypatch.setattr(sys, "argv", ["child", "--flash"])
    monkeypatch.setattr(sys, "stdin", io.StringIO(""))
    monkeypatch.setattr(child, "load", lambda model, revision, flash: seen.append(flash))
    assert child.main() == 0
    assert seen == [True]


def test_text_runs_the_pipeline_and_reports_each_transformer_call_as_a_step(world, capsys):
    pipe = child.load("m", "/local")
    reply = child.run(
        pipe, {"prompt": "a fox", "width": 64, "height": 32, "frames": 124, "steps": 5, "forwards": 4, "seed": 3}
    )

    call = pipe.calls[-1]
    assert (call["num_inference_steps"], call["num_frames"], call["generator"]) == (5, 124, ("generator", 3))
    assert "image" not in call and "references" not in call
    assert (reply["width"], reply["height"], reply["frames"], reply["steps"]) == (64, 32, 124, 4)
    assert base64.b64decode(reply["mp4"]) == b"mp4"
    assert world.encoded[-1] == (124, 24, "generated sound", 32000)
    err = capsys.readouterr().err
    assert "step 0/0" in err and "step 4/4" in err


def test_a_silent_clip_writes_no_sound(world):
    pipe = child.load("m", "/local")
    child.run(
        pipe,
        {
            "prompt": "p",
            "width": 8,
            "height": 8,
            "frames": 124,
            "steps": 2,
            "forwards": 1,
            "seed": 0,
            "include_audio": False,
        },
    )
    assert world.encoded[-1][2:] == (None, None)


def test_the_still_that_sets_the_canvas_is_cover_cropped_and_its_follower_is_not(world):
    """The pipeline stretches the anchor still: a 4:3 photo on a 16:9 clip came out a third wider."""
    pipe = child.load("m", "/local")
    job = {"prompt": "p", "width": 32, "height": 18, "frames": 124, "steps": 2, "forwards": 1, "seed": 0}
    wide, square = png(size=(40, 30)), png(size=(20, 20))
    child.run(pipe, {**job, "first": wide})
    assert pipe.calls[-1]["image"].size == (32, 18) and "last_image" not in pipe.calls[-1]
    child.run(pipe, {**job, "last": wide})
    assert pipe.calls[-1]["last_image"].size == (32, 18) and "image" not in pipe.calls[-1]
    child.run(pipe, {**job, "first": wide, "last": square})
    assert pipe.calls[-1]["image"].size == (32, 18) and pipe.calls[-1]["last_image"].size == (20, 20)


def test_a_track_runs_the_reference_workflow_and_the_clip_carries_the_generated_sound(world, monkeypatch):
    """The pipeline puts a reference before the clip on its own clock, so the picture is not timed
    to the track; the sound generated with the frames is the one that matches them."""
    fake_av(monkeypatch, np.ones((2, 32000 * 10), dtype=np.float32))
    pipe = child.load("m", "/local")
    job = {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "forwards": 1, "seed": 0}
    child.run(pipe, {**job, "pictures": [png(), png((0, 0, 255))], "audio": base64.b64encode(b"wav").decode()})

    references = pipe.calls[-1]["references"]
    assert references[:2] == [("picture", (8, 8)), ("picture", (8, 8))]
    # The track is decoded only as far as the clip: 124 frames at 24 fps.
    assert references[2] == ("track", ("tensor", (2, round(124 / 24 * 32000))), 32000)
    assert world.encoded[-1][2:] == ("generated sound", 32000)


def test_pictures_without_a_track_run_the_reference_workflow_with_pictures_only(world):
    pipe = child.load("m", "/local")
    job = {"prompt": "p", "width": 8, "height": 8, "frames": 124, "steps": 2, "forwards": 1, "seed": 0}
    child.run(pipe, {**job, "pictures": [png(), png((0, 0, 255))]})

    assert pipe.calls[-1]["references"] == [("picture", (8, 8)), ("picture", (8, 8))]
    assert "image" not in pipe.calls[-1] and "last_image" not in pipe.calls[-1]


def test_decoding_stops_at_the_clip_and_a_short_track_is_flushed_whole(world, monkeypatch):
    fake_av(monkeypatch, np.ones((2, 1000), dtype=np.float32), frames=50)
    assert child.decode_track(base64.b64encode(b"wav").decode(), 32000, 2500).shape == (2, 2500)
    fake_av(monkeypatch, np.ones((2, 1000), dtype=np.float32), frames=2)
    # Two frames and the resampler's flush, short of the limit.
    assert child.decode_track(base64.b64encode(b"wav").decode(), 32000, 9000).shape == (2, 2001)


def test_a_track_with_no_sound_is_refused(world, monkeypatch):
    fake_av(monkeypatch, None)
    with pytest.raises(ValueError, match="holds no sound"):
        child.decode_track(base64.b64encode(b"wav").decode(), 32000, 100)


def test_main_answers_each_job_and_turns_a_failure_into_an_error_reply(world, monkeypatch, capsys):
    jobs = [
        json.dumps(
            {
                "prompt": "p",
                "width": 8,
                "height": 8,
                "frames": 124,
                "steps": 2,
                "forwards": 1,
                "seed": 0,
                "request_id": "a",
            }
        ),
        "",
        json.dumps({"request_id": "b"}),
    ]
    monkeypatch.setattr(sys, "argv", ["child", "--model", "m", "--revision", "r"])
    monkeypatch.setattr(sys, "stdin", io.StringIO("\n".join(jobs) + "\n"))
    monkeypatch.setattr(child, "snapshot", lambda model, revision: "/local")

    assert child.main() == 0

    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert replies[0]["request_id"] == "a" and "mp4" in replies[0]
    assert replies[1]["request_id"] == "b" and replies[1]["error"].startswith("KeyError")


def test_main_refuses_a_host_without_cuda(world, monkeypatch):
    sys.modules["torch"].cuda.is_available = lambda: False
    monkeypatch.setattr(sys, "argv", ["child"])
    assert child.main() == 2


def test_the_script_enters_through_its_main_guard(monkeypatch):
    import runpy

    monkeypatch.setattr(sys, "argv", ["child", "--help"])
    with pytest.raises(SystemExit) as exited:
        runpy.run_path(child.__file__, run_name="__main__")
    assert exited.value.code == 0
