"""The real base weights, run as a checkpoint from a folder.

Two things here need the real engine. On `linear`, a checkpoint folder that holds the
base weights has to give the same bytes as the built-in qwen21, which resolves the same
weights from the hub cache: the record adds a folder and nothing else. On
`linear_quadratic`, mflux has to sample the registered schedules on both paths, the edit
path included, whose `Config` is patched because its call takes no scheduler argument.

The unit tests stub both engines, and `test_qwen_schedules_mflux.py` runs no model. This
is the test that runs the whole path.
"""

from functools import partial
from pathlib import Path

import pytest

from studio.l1_entities.image_job import ImageJob
from studio.l3_interface_adapters.gateways.image.qwen21.qwen21_backend_gateway import Qwen21BackendGateway
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.capabilities import qwen_checkpoint_capabilities
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.qwen_checkpoint_backend_gateway import (
    QwenCheckpointBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime import edit as qwen_edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime import generator as qwen_generator
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import base_model_config
from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import (
    AncestralSeedHook,
    edit_scheduler,
    generate_scheduler,
)
from tests.support.images import png

CACHE = Path.home() / ".cache/huggingface/hub/models--Qwen--Qwen-Image-2.1/snapshots"
QUANTIZE = 8


def base_snapshot() -> Path | None:
    snapshots = sorted(CACHE.iterdir()) if CACHE.is_dir() else []
    return snapshots[-1] if snapshots else None


def checkpoint(scheduler="linear", sampler="euler") -> QwenCheckpointBackendGateway:
    """Built as the composition root builds a plugin's record."""
    folder = str(base_snapshot())
    callbacks = (AncestralSeedHook(),) if sampler == "euler_ancestral" else ()
    return QwenCheckpointBackendGateway(
        Qwen21Generator(
            QUANTIZE,
            build=partial(qwen_generator.build_model, model_config=base_model_config, callbacks=callbacks),
            scheduler=generate_scheduler(scheduler, sampler),
            model_path=folder,
        ),
        Qwen21Edit(QUANTIZE, build=partial(qwen_edit.build_model, model_config=base_model_config), model_path=folder),
        qwen_checkpoint_capabilities(
            "example_qwen", "Example Qwen checkpoint", badge="int8", scheduler=scheduler, generate_sampler=sampler
        ),
        folder,
        edit_scheduler=edit_scheduler(scheduler),
    )


def job(mode="generate", seed=5, references=()):
    options = {"size": "512x512", "steps": 4} if mode == "generate" else {"resolution": "match", "steps": 4}
    return ImageJob(mode=mode, prompt="a pear on a table", seed=seed, options=options, references=references)


def run(backend, *jobs):
    try:
        return [backend.run(one, lambda step, total: None, lambda: False).png for one in jobs]
    finally:
        backend.release()


pytestmark = [pytest.mark.live, pytest.mark.skipif(base_snapshot() is None, reason="no local Qwen-Image-2.1")]


def test_live_a_linear_checkpoint_of_the_base_weights_draws_what_qwen21_draws():
    reference = png(512, 384)
    built_in = Qwen21BackendGateway(Qwen21Generator(QUANTIZE), Qwen21Edit(QUANTIZE), badge="int8")

    expected = run(built_in, job(), job("edit", references=(reference,)))

    assert run(checkpoint(), job(), job("edit", references=(reference,))) == expected


def test_live_linear_quadratic_samples_its_own_nodes_on_both_paths():
    reference = png(512, 384)
    linear_generate, linear_edit = run(checkpoint(), job(), job("edit", references=(reference,)))

    generate, edit = run(checkpoint("linear_quadratic"), job(), job("edit", references=(reference,)))

    assert generate[:4] == edit[:4] == b"\x89PNG"
    assert generate != linear_generate
    assert edit != linear_edit


def test_live_euler_ancestral_repeats_for_a_seed_and_differs_from_plain_euler():
    euler = run(checkpoint("linear_quadratic"), job())[0]

    first, again, other = run(checkpoint("linear_quadratic", "euler_ancestral"), job(), job(), job(seed=6))

    assert first == again
    assert first not in (other, euler)
