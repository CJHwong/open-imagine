"""The H3 prompt enhancer's NVFP4 weights: read from the shards, decoded on the GPU into bf16.

The release packs each linear as fp4 codes, two to a byte with the low nibble first, with one
fp8 scale per block of sixteen and one fp32 scale per tensor. The same float32 arithmetic the
numpy decode used runs here on the device, and rounds to bf16 once at the end.

The child imports this by name from its own directory. It needs torch, which the studio's own
environment does not have on a CUDA host, so `coverage.cuda.toml` lists it.
"""

import contextlib
import json
from pathlib import Path

import torch

LEVELS = (0, 0.5, 1, 1.5, 2, 3, 4, 6, -0.0, -0.5, -1, -1.5, -2, -3, -4, -6)

DTYPES = {
    "BF16": torch.bfloat16,
    "F16": torch.float16,
    "F32": torch.float32,
    "F8_E4M3": torch.float8_e4m3fn,
    "U8": torch.uint8,
    "I32": torch.int32,
    "I64": torch.int64,
    "BOOL": torch.bool,
}


@contextlib.contextmanager
def open_shard(path: Path):
    """A reader of one safetensors shard that reads each tensor's bytes in one pass.

    `safe_open` maps the file, so its bytes arrive by page faults wherever a tensor is first
    touched. On the DGX Spark that read the enhancer's 17.9 GB at about 170 MB/s, and it was
    most of the load. Here each tensor's bytes are read in order into memory it owns.
    """
    with open(path, "rb", buffering=0) as handle:
        length = int.from_bytes(handle.read(8), "little")
        header = json.loads(handle.read(length))
        header.pop("__metadata__", None)
        start = 8 + length

        def read(name: str) -> torch.Tensor:
            entry = header[name]
            begin, end = entry["data_offsets"]
            raw = torch.empty(end - begin, dtype=torch.uint8)
            view = memoryview(raw.numpy())
            handle.seek(start + begin)
            done = 0
            while done < len(view):
                count = handle.readinto(view[done:])
                if not count:
                    raise ValueError(f"{Path(path).name} ends inside {name}.")
                done += count
            return raw.view(DTYPES[entry["dtype"]]).reshape(entry["shape"])

        yield read


def dequantize_nvfp4(packed, scales, global_scale, device: str) -> torch.Tensor:
    """bf16 weights from packed codes, block scales and the tensor scale."""
    if packed.dtype != torch.uint8 or packed.ndim != 2 or packed.shape[1] % 8:
        raise ValueError("NVFP4 weights must hold uint8 rows with eight-byte blocks.")
    if tuple(scales.shape) != (packed.shape[0], packed.shape[1] // 8) or global_scale.numel() != 1:
        raise ValueError("NVFP4 scales do not match the packed weights.")
    levels = torch.tensor(LEVELS, dtype=torch.float32, device=device)
    codes = packed.to(device)
    rows, width = codes.shape
    decoded = torch.empty((rows, width * 2), dtype=torch.float32, device=device)
    decoded[:, 0::2] = levels[(codes & 15).long()]
    decoded[:, 1::2] = levels[(codes >> 4).long()]
    decoded.view(rows, width // 8, 16).mul_(scales.to(device=device, dtype=torch.float32)[:, :, None])
    decoded.mul_(global_scale.to(device=device, dtype=torch.float32).reshape(()))
    return decoded.to(torch.bfloat16)
