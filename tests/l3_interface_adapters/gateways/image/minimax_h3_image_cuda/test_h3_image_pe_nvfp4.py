"""Packed prompt-enhancer weights must retain their values and full width."""

import contextlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import h3_image_pe_cuda_child as child


def test_decode_all_fp4_codes_in_low_nibble_order():
    packed = np.array([[0x10, 0x32, 0x54, 0x76, 0x98, 0xBA, 0xDC, 0xFE]], dtype=np.uint8)
    expected = np.array([[0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6]], dtype=np.float32)
    actual = child.dequantize_nvfp4(packed, np.ones((1, 1), dtype=np.float32), np.array(1, dtype=np.float32))
    np.testing.assert_array_equal(actual, expected)
    assert actual.dtype == np.float32


def test_decode_applies_each_block_scale_and_the_tensor_scale():
    packed = np.full((2, 16), 0x22, dtype=np.uint8)
    scales = np.array([[2, 0.5], [4, 0.25]], dtype=np.float32)
    actual = child.dequantize_nvfp4(packed, scales, np.array([0.5], dtype=np.float32))
    np.testing.assert_array_equal(actual[:, :16], np.array([[1] * 16, [2] * 16]))
    np.testing.assert_array_equal(actual[:, 16:], np.array([[0.25] * 16, [0.125] * 16]))


@pytest.mark.parametrize(
    ("packed", "scales", "global_scale"),
    [
        (np.zeros((1, 8), dtype=np.float32), np.ones((1, 1)), np.array(1)),
        (np.zeros(8, dtype=np.uint8), np.ones((1, 1)), np.array(1)),
        (np.zeros((1, 7), dtype=np.uint8), np.ones((1, 1)), np.array(1)),
        (np.zeros((1, 8), dtype=np.uint8), np.ones((1, 2)), np.array(1)),
        (np.zeros((1, 8), dtype=np.uint8), np.ones((1, 1)), np.ones(2)),
    ],
)
def test_decode_refuses_invalid_packed_dimensions(packed, scales, global_scale):
    with pytest.raises(ValueError):
        child.dequantize_nvfp4(packed, scales, global_scale)


class Tensor:
    def __init__(self, values, dtype=None):
        self.values = np.asarray(values)
        self.dtype = dtype if dtype is not None else self.values.dtype
        self.clones = 0
        self.device = "cpu"

    def clone(self):
        self.clones += 1
        return Tensor(self.values.copy(), self.dtype)

    def float(self):
        return Tensor(self.values.astype(np.float32))

    def numpy(self):
        return self.values

    def to(self, destination):
        if destination == "cuda":
            self.device = destination
            return self
        return Tensor(self.values, destination)


@pytest.fixture
def packed_model(monkeypatch, tmp_path):
    packed = Tensor(np.full((1, 8), 0x22, dtype=np.uint8))
    dense = Tensor(np.array([0.125], dtype=np.float32))
    shards = {
        "weights.safetensors": {"layer.weight": packed, "layer.A_log": dense},
        "scales.safetensors": {
            "layer.weight_scale": Tensor([[2.0]]),
            "layer.weight_scale_2": Tensor([0.5]),
            "layer.input_scale": Tensor([99]),
        },
    }
    index = {name: shard for shard, tensors in shards.items() for name in tensors}
    (tmp_path / "model.safetensors.index.json").write_text(json.dumps({"weight_map": index}))
    buffer = SimpleNamespace(data=Tensor([1.0]))
    model = SimpleNamespace(
        state_dict=lambda: {"layer.weight": None, "layer.A_log": None}, tie_weights=Mock(), buffers=lambda: [buffer]
    )
    model.eval = Mock(return_value=model)
    assignments, opened, closed = [], [], []

    @contextlib.contextmanager
    def safe_open(path, framework, device):
        from pathlib import Path

        shard = Path(path).name
        assert framework == "pt" and device == "cpu"
        opened.append(shard)
        try:
            yield SimpleNamespace(get_tensor=lambda name: shards[shard][name])
        finally:
            closed.append(shard)

    monkeypatch.setitem(sys.modules, "safetensors", SimpleNamespace(safe_open=safe_open))
    monkeypatch.setitem(sys.modules, "accelerate", SimpleNamespace(init_empty_weights=contextlib.nullcontext))
    monkeypatch.setitem(
        sys.modules,
        "accelerate.utils",
        SimpleNamespace(set_module_tensor_to_device=lambda *args, **kwargs: assignments.append((args, kwargs))),
    )
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(from_numpy=Tensor, bfloat16="bf16"))
    generation = Mock(return_value="generation-config")
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            Qwen3_5ForConditionalGeneration=lambda config: model,
            GenerationConfig=SimpleNamespace(from_pretrained=generation),
        ),
    )
    snapshot = Mock(return_value=str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=snapshot))
    return SimpleNamespace(
        directory=tmp_path,
        model=model,
        assignments=assignments,
        opened=opened,
        closed=closed,
        buffer=buffer,
        dense=dense,
        snapshot=snapshot,
        generation=generation,
        shards=shards,
    )


def test_streams_cross_shard_weights_and_preserves_dense_dtype(packed_model):
    fixture = packed_model
    config = SimpleNamespace(quantization_config={"quant_algo": "NVFP4", "quant_method": "modelopt", "group_size": 16})
    assert child.load_nvfp4(str(fixture.directory), config) is fixture.model
    loaded = {args[1]: kwargs for args, kwargs in fixture.assignments}
    np.testing.assert_array_equal(loaded["layer.weight"]["value"].numpy(), np.ones((1, 16)))
    assert loaded["layer.weight"]["dtype"] == "bf16"
    assert loaded["layer.A_log"]["dtype"] == np.float32
    assert fixture.dense.clones == 1
    assert all(args[0] is fixture.model and args[2] == "cuda" for args, _ in fixture.assignments)
    assert sorted(fixture.opened) == sorted(fixture.closed) == ["scales.safetensors", "weights.safetensors"]
    assert fixture.buffer.data.device == "cuda"
    fixture.model.tie_weights.assert_called_once_with()
    fixture.model.eval.assert_called_once_with()
    fixture.snapshot.assert_not_called()
    fixture.generation.assert_not_called()
    assert not hasattr(config, "quantization_config")


def test_downloads_uncached_packed_model_and_reads_generation_settings(packed_model):
    fixture = packed_model
    (fixture.directory / "generation_config.json").write_text("{}")
    config = SimpleNamespace(quantization_config={"quant_method": "modelopt", "group_size": 16})
    child.load_nvfp4("public/model", config)
    fixture.snapshot.assert_called_once_with("public/model")
    fixture.generation.assert_called_once_with(str(fixture.directory))
    assert fixture.model.generation_config == "generation-config"


def test_refuses_other_block_sizes_before_constructing_model(packed_model):
    with pytest.raises(ValueError, match="groups of sixteen"):
        child.load_nvfp4(
            str(packed_model.directory),
            SimpleNamespace(quantization_config={"quant_method": "modelopt", "group_size": 32}),
        )
    assert not packed_model.assignments


def test_refuses_missing_and_unexpected_weights_before_device_transfers(packed_model):
    fixture = packed_model
    fixture.model.state_dict = lambda: {"missing.weight": None}
    with pytest.raises(ValueError, match=r"missing.*missing\.weight.*unexpected.*layer\.A_log"):
        child.load_nvfp4(
            str(fixture.directory), SimpleNamespace(quantization_config={"quant_method": "modelopt", "group_size": 16})
        )
    assert not fixture.assignments
    assert not fixture.opened


def test_closes_shards_after_a_failed_decode(packed_model):
    fixture = packed_model
    fixture.shards["scales.safetensors"]["layer.weight_scale"] = Tensor([[2, 3]])
    with pytest.raises(ValueError, match="scales do not match"):
        child.load_nvfp4(
            str(fixture.directory), SimpleNamespace(quantization_config={"quant_method": "modelopt", "group_size": 16})
        )
    assert sorted(fixture.opened) == sorted(fixture.closed)


def test_load_selects_packed_loader_without_dense_pretrained_loading(monkeypatch):
    config = SimpleNamespace(quantization_config={"quant_algo": "NVFP4"})
    model, processor = object(), object()
    dense_loader = Mock(side_effect=AssertionError("Packed tensors cannot enter the dense loader"))
    packed_loader = Mock(return_value=model)
    synchronize = Mock()
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(bfloat16="bf16", cuda=SimpleNamespace(synchronize=synchronize))
    )
    monkeypatch.setitem(
        sys.modules,
        "transformers",
        SimpleNamespace(
            AutoConfig=SimpleNamespace(from_pretrained=lambda source: config),
            AutoProcessor=SimpleNamespace(from_pretrained=lambda source: processor),
            Qwen3_5ForConditionalGeneration=SimpleNamespace(from_pretrained=dense_loader),
        ),
    )
    monkeypatch.setattr(child, "load_nvfp4", packed_loader)
    monkeypatch.setattr(child, "local_snapshot", lambda model: "/public/snapshot")
    assert child.load("public/model") == (processor, model)
    packed_loader.assert_called_once_with("/public/snapshot", config)
    dense_loader.assert_not_called()
    synchronize.assert_called_once_with()


@pytest.mark.parametrize("method", [None, "torchao"])
def test_refuses_another_nvfp4_layout(packed_model, method):
    config = SimpleNamespace(quantization_config={"quant_algo": "NVFP4", "quant_method": method, "group_size": 16})
    with pytest.raises(ValueError, match="ModelOpt NVFP4"):
        child.load_nvfp4(str(packed_model.directory), config)
    assert not packed_model.assignments
