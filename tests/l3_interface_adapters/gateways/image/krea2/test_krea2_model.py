import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image

from studio.l1_entities.errors import Cancelled, StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.image.krea2.krea2_model import (
    SCHEDULER,
    Krea2Model,
    build_model,
    generate_kwargs,
    image_size,
    missing_files,
)
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import StepHook
from tests.support.heavy import heavy_modules
from tests.support.images import png


def job(references=(), **options):
    defaults = {"size": "1024x1024", "steps": 8, "strength": 0.4}
    return ImageJob(mode="generate", prompt="a pear", seed=5, options={**defaults, **options}, references=references)


def checkpoint(root: Path, skip: str = "") -> str:
    """A folder in the q8 layout: three indexes, their shards and the tokenizer."""
    layout = {
        "model.safetensors.index.json": ["0.safetensors", "1.safetensors"],
        "text_encoder/model.safetensors.index.json": ["0.safetensors"],
        "vae/model.safetensors.index.json": ["0.safetensors"],
    }
    for index, shards in layout.items():
        path = root / index
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"weight_map": {f"w{n}": shard for n, shard in enumerate(shards * 2)}}))
        for shard in shards:
            (path.parent / shard).write_bytes(b"")
    (root / "tokenizer").mkdir()
    for name in ("tokenizer.json", "tokenizer_config.json"):
        (root / "tokenizer" / name).write_text("{}")
    if skip:
        (root / skip).unlink()
    return str(root)


class FakeModel:
    """A Krea2 that records its runs, keeps a prompt cache and calls its step hook, as mflux does.

    mflux runs range(init_time_step, steps), and init_time_step is max(1, int(steps * strength))
    with a starting image, 0 without one.
    """

    def __init__(self, runs, hook, fail=None):
        self.runs, self.hook, self.fail = runs, hook, fail
        self.prompt_cache = {}

    def generate_image(self, **kwargs):
        self.prompt_cache[(kwargs["prompt"], None, 1.0)] = "embeds"
        self.runs.append(kwargs)
        steps = kwargs["num_inference_steps"]
        start = max(1, int(steps * kwargs["image_strength"])) if "image_path" in kwargs else 0
        config = SimpleNamespace(init_time_step=start, num_inference_steps=steps)
        for t in range(start, steps):
            self.hook.call_in_loop(t, kwargs["seed"], kwargs["prompt"], None, config, None)
        if self.fail is not None:
            raise self.fail
        return SimpleNamespace(image=Image.new("RGB", (kwargs["width"], kwargs["height"])))


class Recording:
    def __init__(self, fail=None):
        self.builds, self.runs, self.fail = [], [], fail
        self.model = None

    def build(self, model_dir, hook):
        self.builds.append(model_dir)
        self.model = FakeModel(self.runs, hook, self.fail)
        return self.model

    def prompt_cache(self) -> dict:
        assert self.model is not None
        return self.model.prompt_cache

    def krea2(self, tmp_path):
        return Krea2Model(checkpoint(tmp_path), build=self.build)


def run(model, the_job, seen=None):
    seen = [] if seen is None else seen
    return model.run(the_job, lambda step, total: seen.append((step, total)), lambda: False)


def test_a_text_run_maps_the_form_to_mflux():
    assert generate_kwargs(job(size="1280x720")) == {
        "seed": 5,
        "prompt": "a pear",
        "width": 1280,
        "height": 720,
        "num_inference_steps": 8,
        "scheduler": SCHEDULER,
    }


def test_the_sampler_is_the_model_cards():
    assert SCHEDULER == "er_sde"


def test_a_reference_goes_in_as_a_pil_image_with_its_strength():
    # mflux encodes a PIL image as it is, so the reference never reaches the disk.
    kwargs = generate_kwargs(job(references=(png(64, 48),), strength=0.6))
    assert isinstance(kwargs["image_path"], Image.Image)
    assert kwargs["image_path"].size == (64, 48)
    assert kwargs["image_strength"] == 0.6


def test_a_text_run_brings_no_strength():
    assert "image_strength" not in generate_kwargs(job(strength=0.6))


def test_match_keeps_the_reference_shape_at_one_megapixel():
    # mflux stretches the reference to the target size, so a square output from
    # a 16:9 photo would squash it.
    assert image_size(job(references=(png(1600, 900),), size="match")) == (1360, 768)


def test_match_with_nothing_to_match_is_a_square():
    assert image_size(job(size="match")) == (1024, 1024)


def test_the_model_is_built_from_the_local_weights_with_no_quantize():
    # The weights are stored at int8, and mflux runs the stored bits.
    krea2 = Mock()
    resolve = Mock(return_value="the config")
    with heavy_modules(
        {
            "mflux.models.common.resolution.config_resolution": {"ConfigResolution": Mock(resolve_restricted=resolve)},
            "mflux.models.krea2.variants": {"Krea2": krea2},
        }
    ):
        hook = StepHook()
        model = build_model("/weights/krea2", hook)

    assert resolve.call_args.args == (None, "krea-2")
    assert resolve.call_args.kwargs == {"model_path": "/weights/krea2"}
    assert krea2.call_args.kwargs == {"model_config": "the config", "model_path": "/weights/krea2"}
    assert model is krea2.return_value
    krea2.return_value.callbacks.register.assert_called_once_with(hook)


def test_a_complete_checkpoint_misses_nothing(tmp_path):
    assert missing_files(checkpoint(tmp_path)) == []


@pytest.mark.parametrize(
    "skip",
    ["1.safetensors", "vae/0.safetensors", "text_encoder/model.safetensors.index.json", "tokenizer/tokenizer.json"],
)
def test_a_half_done_download_names_the_file_it_lacks(tmp_path, skip):
    assert missing_files(checkpoint(tmp_path, skip=skip)) == [skip]


def test_a_missing_folder_is_named(tmp_path):
    assert missing_files(str(tmp_path / "nowhere")) == [str(tmp_path / "nowhere")]


def test_an_incomplete_checkpoint_stops_the_load_before_mflux(tmp_path):
    recording = Recording()
    model = Krea2Model(checkpoint(tmp_path, skip="1.safetensors"), build=recording.build)
    with pytest.raises(StudioError, match=r"incomplete: 1\.safetensors\. Follow the Krea 2 setup"):
        model.load()
    assert recording.builds == []


def test_a_run_returns_the_image_the_model_made(tmp_path):
    recording = Recording()
    steps = []
    result = run(recording.krea2(tmp_path), job(size="768x432"), steps)
    assert (result.width, result.height, result.seed, result.steps) == (768, 432, 5, 8)
    assert steps == [(0, 8)] + [(step, 8) for step in range(1, 9)]


def test_a_reference_run_counts_only_the_steps_it_runs(tmp_path):
    # Strength 0.5 skips 4 of the 8 steps. The page shows 1 to 4 of 4, not 5 to 8 of 8.
    steps = []
    run(Recording().krea2(tmp_path), job(size="16x16", references=(png(8, 8),), strength=0.5), steps)
    assert steps[1:] == [(1, 4), (2, 4), (3, 4), (4, 4)]


def test_a_cancel_stops_at_the_step_it_lands_on_and_leaves_no_prompt(tmp_path):
    recording = Recording()
    model = recording.krea2(tmp_path)
    steps = []
    with pytest.raises(Cancelled, match="stopped at step 3"):
        model.run(job(size="16x16"), lambda step, total: steps.append(step), lambda: len(steps) > 2)
    assert steps == [0, 1, 2]
    assert recording.prompt_cache() == {}


@pytest.mark.parametrize("text", ["{", "{}", "[]"])
def test_a_truncated_index_is_named_as_missing(tmp_path, text):
    folder = checkpoint(tmp_path)
    (tmp_path / "vae/model.safetensors.index.json").write_text(text)
    assert missing_files(folder) == ["vae/model.safetensors.index.json"]


def test_the_model_stays_warm_across_images_of_one_batch(tmp_path):
    recording = Recording()
    model = recording.krea2(tmp_path)
    run(model, job(size="16x16"))
    run(model, job(size="16x16", references=(png(8, 8),)))
    assert len(recording.builds) == 1


def test_release_drops_the_model_so_the_next_load_builds_again(tmp_path):
    recording = Recording()
    model = recording.krea2(tmp_path)
    model.load()
    model.release()
    model.load()
    assert len(recording.builds) == 2


def test_a_run_leaves_no_prompt_in_the_cache(tmp_path):
    # AGENTS.md rule 1: a private run keeps no plaintext copy of its prompt.
    recording = Recording()
    run(recording.krea2(tmp_path), job(size="16x16"))
    assert recording.prompt_cache() == {}


@pytest.mark.parametrize("fail", [RuntimeError("out of memory"), Cancelled("stopped at step 2")])
def test_a_failed_or_cancelled_run_leaves_no_prompt_and_hands_the_pool_back(tmp_path, fail):
    recording = Recording(fail=fail)
    model = recording.krea2(tmp_path)
    model.load()
    clear_cache = Mock()
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}), pytest.raises(type(fail)):
        run(model, job(size="16x16"))
    assert recording.prompt_cache() == {}
    clear_cache.assert_called_once_with()


def test_release_hands_the_mlx_pool_back(tmp_path):
    clear_cache = Mock()
    model = Recording().krea2(tmp_path)
    with heavy_modules({"mlx.core": {"clear_cache": clear_cache}}):
        model.release()
    clear_cache.assert_called_once_with()
