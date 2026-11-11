"""The Flash changes to the engine, against a stand-in for the engine's package.

The engine's own modules are not in Studio's environment, so `minimax_h3_mlx` is faked here.
The arithmetic runs on the real MLX arrays.
"""

import json
import sys
from types import ModuleType, SimpleNamespace

import mlx.core as mx
import mlx.nn as nn
import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.video.minimax_h3 import flash
from studio.l3_interface_adapters.gateways.video.minimax_h3.capabilities import FLASH_FORWARDS

# The plan is in float32, so the test names the keyframe time as float32 reads it.
KEYFRAME = float(np.float32(0.999))


class Embedder(nn.Module):
    """One number in, one number out: weight times the input, plus the bias."""

    def __init__(self, config):
        super().__init__()
        self.proj_in = nn.Linear(1, 1)
        self.proj_out = nn.Linear(1, 1)

    def __call__(self, values):
        return self.proj_out(self.proj_in(values))


def row_timesteps(layout, video, audio, keyframe, clean, frozen_video, frozen_audio, frozen_time):
    """Rows as the engine lays them out here: a keyframe row, two video rows and an audio row."""
    rows = np.array([keyframe, video, video, audio], dtype=np.float32)
    if frozen_video is not None:
        rows[2] = frozen_time
    if frozen_audio is not None:
        rows[3] = clean
    distinct, inverse = np.unique(rows, return_inverse=True)
    return mx.array(distinct), mx.array(inverse)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    package = ModuleType("minimax_h3_mlx")
    dit = ModuleType("minimax_h3_mlx.dit")
    monkeypatch.setattr(dit, "TimestepEmbedder", Embedder, raising=False)
    monkeypatch.setattr(dit, "timestep_embedding", lambda values, dim: values.reshape(-1, 1) * dim, raising=False)
    packing = ModuleType("minimax_h3_mlx.packing")
    monkeypatch.setattr(packing, "KEYFRAME_NOISE_AUG", KEYFRAME, raising=False)
    monkeypatch.setattr(packing, "build_row_timesteps", row_timesteps, raising=False)
    for module in (package, dit, packing):
        monkeypatch.setitem(sys.modules, module.__name__, module)

    class DiT:
        config = SimpleNamespace(timestep_input_dim=2)

        def time_embedder(self, values):
            return values * 10

        def parameters(self):
            return {"blocks": [{"weight": mx.zeros((1,))}, {"weight": mx.zeros((1,))}]}

    loads = []

    def load_dit(model_dir, strict=True, verbose=False):
        loads.append((model_dir, strict))
        return DiT()

    return SimpleNamespace(load_dit=load_dit, row_timestep_plan=None, FROZEN_VIDEO_TIMESTEP=0.75, loads=loads)


def pack(folder, endpoint=4, blocks=(0,), dropped=(1,)):
    """A Flash pack whose endpoint embedder doubles its input and adds one. The engine's
    transformer has two blocks here, and the pack drops the second."""
    values = {
        "proj_in.weight": mx.array([[2.0]]),
        "proj_in.bias": mx.array([0.0]),
        "proj_out.weight": mx.array([[1.0]]),
        "proj_out.bias": mx.array([1.0]),
    }
    tensors = {flash.ENDPOINT + key: value for key, value in list(values.items())[:endpoint]}
    for block in blocks:
        tensors[f"blocks.{block}.weight"] = mx.zeros((1,))
    mx.save_safetensors(str(folder / "model-1.safetensors"), tensors)
    (folder / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": dict.fromkeys(tensors, "model-1.safetensors")})
    )
    (folder / "flash.json").write_text(json.dumps({"hyperflow_gate": 0.25, "dropped_blocks": list(dropped)}))
    return folder


def test_the_schedule_is_six_steps_of_euler_on_the_models_own_grid():
    flags = flash.schedule_flags()

    assert flags[0] == "--sigma-knots" and flags[2:] == ["--sampler", "euler"]
    knots = [float(value) for value in flags[1].split(",")]
    # Seven sigma points make six steps. The engine reads thousandths, from noise to clean.
    assert len(knots) == 7 and knots[0] == 1000 and knots[-1] == 0
    assert knots == sorted(knots, reverse=True) and knots[1] == 825.217
    assert len(flash.SIGMAS) - 1 == FLASH_FORWARDS


def test_install_loads_the_endpoint_embedder_and_mixes_it_in_at_the_gate(engine, tmp_path):
    assert flash.install(engine) == flash.schedule_flags()

    dit = engine.load_dit(pack(tmp_path), verbose=True, strict=True)

    # The dropped blocks have no weights, so the engine loads without its strict key check.
    assert engine.loads == [(tmp_path, False)]
    assert dit.skip_blocks == frozenset({1})
    # At t = 1 and r = 3 with dim 2: the model's own embedder gives 20, and the endpoint one
    # gives 2 x 6 + 1 = 13. A gate of 0.25 moves a quarter of the way: 20 - 7 / 4.
    mixed = dit.embed_timesteps(mx.array([[1.0, 3.0], [1.0, 1.0]]))
    assert mixed.tolist() == [[18.25], [20 + 0.25 * (5 - 20)]]
    with pytest.raises(ValueError, match="pair"):
        dit.embed_timesteps(mx.array([1.0, 3.0]))


def test_install_refuses_a_pack_without_its_four_endpoint_tensors(engine, tmp_path):
    flash.install(engine)

    with pytest.raises(RuntimeError, match="four endpoint tensors"):
        engine.load_dit(pack(tmp_path, endpoint=3))


def test_the_plan_pairs_each_time_with_the_time_of_the_next_step(engine):
    flash.install(engine)

    table, plan = engine.row_timestep_plan(None, mx.array([0.0, 0.5]), mx.array([0.0, 0.25]))

    pairs = [[tuple(table[index].tolist()) for index in step.tolist()] for step in plan]
    # A row steps to the time of the next step, and the last step ends clean at 1. The keyframe
    # row goes nowhere: its two times are equal.
    assert pairs == [
        [(KEYFRAME, KEYFRAME), (0.0, 0.5), (0.0, 0.5), (0.0, 0.25)],
        [(KEYFRAME, KEYFRAME), (0.5, 1.0), (0.5, 1.0), (0.25, 1.0)],
    ]
    assert table.shape == (5, 2) and table.dtype == mx.float32


def test_the_plan_holds_a_frozen_row_at_one_time(engine):
    flash.install(engine)
    frozen = np.array([True])

    table, plan = engine.row_timestep_plan(None, mx.array([0.0]), mx.array([0.0]), frozen, frozen)

    # A frozen video row holds the engine's own time for it, and a frozen audio row is clean.
    assert tuple(table[plan[0][2].item()].tolist()) == (0.75, 0.75)
    assert tuple(table[plan[0][3].item()].tolist()) == (1.0, 1.0)


def test_the_plan_moves_a_keyframe_row_once_the_clip_is_cleaner_than_it(engine):
    flash.install(engine)
    late = float(np.float32(0.9995))

    table, plan = engine.row_timestep_plan(None, mx.array([late]), mx.array([0.5]))

    # The keyframe row never trails the clip: past its own noise level it takes the clip's time.
    assert tuple(table[plan[0][0].item()].tolist()) == (late, late)


@pytest.mark.parametrize("blocks,dropped", [((), (1,)), ((0, 1, 2), (1,)), ((0,), ())])
def test_install_refuses_a_pack_with_another_hole_than_the_dropped_blocks(engine, tmp_path, blocks, dropped):
    flash.install(engine)

    with pytest.raises(RuntimeError, match="does not match the engine"):
        engine.load_dit(pack(tmp_path, blocks=blocks, dropped=dropped))
