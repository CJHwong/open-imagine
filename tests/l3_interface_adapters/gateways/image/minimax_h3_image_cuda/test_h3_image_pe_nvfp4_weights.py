"""The enhancer's NVFP4 weights read back as written and decode to the numpy decode's values."""

import numpy as np
import pytest

torch = pytest.importorskip("torch")

from studio.l3_interface_adapters.gateways.image.minimax_h3_image_cuda import (  # noqa: E402
    h3_image_pe_nvfp4_weights as decode,
)


def numpy_decode(packed, scales, global_scale):
    """The decode the child ran before, in numpy, as the reference."""
    levels = np.array(decode.LEVELS, dtype=np.float32)
    decoded = np.empty((packed.shape[0], packed.shape[1] * 2), dtype=np.float32)
    decoded[:, 0::2] = levels[packed & 15]
    decoded[:, 1::2] = levels[packed >> 4]
    decoded.reshape(packed.shape[0], packed.shape[1] // 8, 16)[:] *= scales.astype(np.float32)[:, :, None]
    decoded *= global_scale.astype(np.float32).reshape(())
    return torch.from_numpy(decoded).to(torch.bfloat16)


def test_decode_all_fp4_codes_in_low_nibble_order():
    packed = torch.tensor([[0x10, 0x32, 0x54, 0x76, 0x98, 0xBA, 0xDC, 0xFE]], dtype=torch.uint8)
    actual = decode.dequantize_nvfp4(packed, torch.ones(1, 1), torch.tensor(1.0), "cpu")
    assert actual.dtype == torch.bfloat16
    assert actual.float().tolist() == [list(map(float, decode.LEVELS))]
    assert torch.signbit(actual[0, 8])


def test_decode_applies_each_block_scale_and_the_tensor_scale():
    packed = torch.full((2, 16), 0x22, dtype=torch.uint8)
    scales = torch.tensor([[2, 0.5], [4, 0.25]])
    actual = decode.dequantize_nvfp4(packed, scales, torch.tensor([0.5]), "cpu").float()
    assert actual[:, :16].tolist() == [[1.0] * 16, [2.0] * 16]
    assert actual[:, 16:].tolist() == [[0.25] * 16, [0.125] * 16]


def test_decode_matches_the_numpy_decode_bit_for_bit():
    generator = torch.Generator().manual_seed(7)
    packed = torch.randint(0, 256, (64, 128), dtype=torch.uint8, generator=generator)
    scales = (torch.rand(64, 16, generator=generator) * 3).to(torch.float8_e4m3fn).float()
    global_scale = torch.tensor([0.0123])

    actual = decode.dequantize_nvfp4(packed, scales, global_scale, "cpu")

    expected = numpy_decode(packed.numpy(), scales.numpy(), global_scale.numpy())
    assert torch.equal(actual.view(torch.int16), expected.view(torch.int16))


@pytest.mark.parametrize(
    ("packed", "scales", "global_scale"),
    [
        (torch.zeros((1, 8)), torch.ones((1, 1)), torch.tensor(1.0)),
        (torch.zeros(8, dtype=torch.uint8), torch.ones((1, 1)), torch.tensor(1.0)),
        (torch.zeros((1, 7), dtype=torch.uint8), torch.ones((1, 1)), torch.tensor(1.0)),
        (torch.zeros((1, 8), dtype=torch.uint8), torch.ones((1, 2)), torch.tensor(1.0)),
        (torch.zeros((1, 8), dtype=torch.uint8), torch.ones((1, 1)), torch.ones(2)),
    ],
)
def test_decode_refuses_invalid_packed_dimensions(packed, scales, global_scale):
    with pytest.raises(ValueError):
        decode.dequantize_nvfp4(packed, scales, global_scale, "cpu")


def test_a_shard_reads_back_every_tensor_save_file_wrote(tmp_path):
    save_file = pytest.importorskip("safetensors.torch").save_file
    tensors = {
        "codes": torch.randint(0, 256, (4, 8), dtype=torch.uint8),
        "block": torch.rand(4, 1).to(torch.float8_e4m3fn),
        "tensor": torch.tensor([0.5]),
        "dense": torch.randn(3, 5, dtype=torch.bfloat16),
        "half": torch.randn(2, dtype=torch.float16),
        "index": torch.arange(3),
        "count": torch.arange(3, dtype=torch.int32),
        "mask": torch.tensor([True, False]),
        "empty": torch.zeros(0, 4, dtype=torch.bfloat16),
    }
    path = tmp_path / "shard.safetensors"
    save_file(tensors, str(path), metadata={"format": "pt"})

    with decode.open_shard(path) as read:
        for name, tensor in tensors.items():
            got = read(name)
            assert got.dtype == tensor.dtype and got.shape == tensor.shape, name
            assert torch.equal(got.reshape(-1).view(torch.uint8), tensor.reshape(-1).view(torch.uint8)), name


def test_a_shard_cut_short_names_the_tensor_it_ends_inside(tmp_path):
    save_file = pytest.importorskip("safetensors.torch").save_file
    path = tmp_path / "shard.safetensors"
    save_file({"weight": torch.ones(64)}, str(path))
    path.write_bytes(path.read_bytes()[:-16])

    with decode.open_shard(path) as read, pytest.raises(ValueError, match=r"shard\.safetensors ends inside weight"):
        read("weight")
