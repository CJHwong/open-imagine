#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12,<3.13"
# dependencies = [
#   "huggingface_hub==1.32.0",
#   "numpy>=2,<3",
# ]
# ///
"""Turn the nvfp4 H3-Image prompt enhancer into a bf16 checkpoint mlx_vlm can convert.

The release stores each quantized linear as three tensors: `weight` holds two E2M1 values
per byte with the first in the low nibble, `weight_scale` holds one E4M3 scale per 16
weights, and `weight_scale_2` holds one F32 scale for the whole tensor. This script
dequantizes one tensor at a time, drops every scale tensor, and writes a normal bf16
checkpoint that keeps every non-weight file.

The safetensors files are read and written here rather than through a library: the source
holds F8_E4M3 and BF16 tensors, and the numpy converter has no dtype for either.

    uv run --script scripts/convert_h3_image_pe.py --out <bf16 dir>
"""

from __future__ import annotations

import argparse
import json
import shutil
import struct
from pathlib import Path

import numpy as np
from huggingface_hub import snapshot_download

REPOSITORY = "MiniMaxAI/MiniMax-H3-Image-PE"
REVISION = "35603d4b63949afa12cb098227fffefedf081afa"
GROUP = 16
SHARD_BYTES = 8 * 1024**3
COPY = (
    "generation_config.json",
    "chat_template.jinja",
    "processor_config.json",
    "tokenizer.json",
    "tokenizer_config.json",
    "vocab.json",
    "merges.txt",
)

# E2M1 values by code, sign in bit 3: 0, .5, 1, 1.5, 2, 3, 4, 6.
E2M1 = np.array(
    [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, -0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0], dtype=np.float32
)


def e4m3_table() -> np.ndarray:
    """The 256 byte values of E4M3 as float32. The two NaN encodings become 0."""
    codes = np.arange(256, dtype=np.uint32)
    sign = np.where((codes >> 7) & 1, -1.0, 1.0).astype(np.float32)
    exponent = ((codes >> 3) & 0xF).astype(np.int32)
    mantissa = (codes & 0x7).astype(np.float32)
    normal = sign * np.exp2(exponent - 7) * (1 + mantissa / 8)
    subnormal = sign * np.exp2(-6) * (mantissa / 8)
    values = np.where(exponent == 0, subnormal, normal)
    return np.where((exponent == 15) & (mantissa == 7), 0.0, values).astype(np.float32)


E4M3 = e4m3_table()


def dequantize(packed: np.ndarray, scale: np.ndarray, global_scale: np.ndarray) -> np.ndarray:
    """The float32 matrix behind one nvfp4 linear."""
    values = np.empty((packed.shape[0], packed.shape[1] * 2), dtype=np.float32)
    values[:, 0::2] = E2M1[(packed & 0x0F).astype(np.uint8)]
    values[:, 1::2] = E2M1[(packed >> 4).astype(np.uint8)]
    if values.shape[1] % GROUP:
        raise ValueError(f"a width of {values.shape[1]} is not a multiple of {GROUP}")
    group_scale = np.repeat(E4M3[scale.astype(np.uint8)], GROUP, axis=1)
    return values * group_scale * np.float32(global_scale)


class Safetensors:
    """The tensors of one safetensors file, read as float32 or raw bytes."""

    def __init__(self, path: Path):
        self._raw = np.memmap(path, dtype=np.uint8, mode="r")
        size = struct.unpack("<Q", self._raw[:8].tobytes())[0]
        self.header = json.loads(self._raw[8 : 8 + size].tobytes())
        self._base = 8 + size

    def names(self) -> list[str]:
        return [name for name in self.header if name != "__metadata__"]

    def get(self, name: str) -> np.ndarray:
        entry = self.header[name]
        start, stop = entry["data_offsets"]
        raw = self._raw[self._base + start : self._base + stop]
        dtype, shape = entry["dtype"], tuple(entry["shape"])
        if dtype == "BF16":
            wide = raw.view("<u2").astype(np.uint32) << 16
            return wide.view(np.float32).reshape(shape)
        if dtype == "F32":
            return raw.view("<f4").reshape(shape).astype(np.float32)
        if dtype in ("U8", "F8_E4M3"):
            return np.asarray(raw).reshape(shape)
        raise ValueError(f"{name} holds {dtype}, which this converter does not read")


def bf16_bytes(tensor: np.ndarray) -> bytes:
    """The BF16 bytes of a float tensor, rounded to nearest even."""
    wide = tensor.astype(np.float32).view(np.uint32)
    rounded = (wide + 0x8000 + ((wide >> 16) & 1)).astype(np.uint32) >> 16
    return rounded.astype("<u2").tobytes()


def save_shard(path: Path, tensors: dict[str, np.ndarray]) -> None:
    """Write one BF16 safetensors file, with float tensors as BF16 and bytes untouched."""
    header, blobs, offset = {}, [], 0
    for name, tensor in tensors.items():
        data = tensor.tobytes() if tensor.dtype == np.uint8 else bf16_bytes(tensor)
        header[name] = {
            "dtype": "U8" if tensor.dtype == np.uint8 else "BF16",
            "shape": list(tensor.shape),
            "data_offsets": [offset, offset + len(data)],
        }
        offset += len(data)
        blobs.append(data)
    encoded = json.dumps(header, separators=(",", ":")).encode()
    encoded += b" " * ((8 - len(encoded) % 8) % 8)
    with path.open("wb") as handle:
        handle.write(struct.pack("<Q", len(encoded)))
        handle.write(encoded)
        for data in blobs:
            handle.write(data)


class Writer:
    """Collects converted tensors into shards and records the index."""

    def __init__(self, out: Path):
        self.out = out
        self.index = 0
        self.bytes = 0
        self.shard: dict[str, np.ndarray] = {}
        self.weight_map: dict[str, str] = {}
        self.total = 0

    def add(self, name: str, tensor: np.ndarray) -> None:
        self.shard[name] = tensor
        self.bytes += tensor.nbytes
        self.total += tensor.nbytes
        if self.bytes > SHARD_BYTES:
            self.flush()

    def flush(self) -> None:
        if not self.shard:
            return
        self.index += 1
        name = f"model-{self.index:05d}.safetensors"
        save_shard(self.out / name, self.shard)
        self.weight_map.update({key: name for key in self.shard})
        print(f"  wrote {name} ({self.bytes / 1e9:.2f} GB, {len(self.shard)} tensors)", flush=True)
        self.bytes, self.shard = 0, {}


def index_map(source: Path) -> dict[str, str]:
    return json.loads((source / "model.safetensors.index.json").read_text())["weight_map"]


def convert(source: Path, out: Path) -> Writer:
    """Dequantize every linear the release quantized, then copy the rest.

    A weight and its two scales do not always share a shard, so the reader follows the index
    rather than one file at a time. A per-shard test left one weight packed, and the model
    then loaded it at half its width.
    """
    index = index_map(source)
    quantized = {
        name.removesuffix(".weight") for name in index if name.endswith(".weight") and f"{name}_scale" in index
    }
    readers: dict[str, Safetensors] = {}

    def get(name: str) -> np.ndarray:
        shard = index[name]
        if shard not in readers:
            readers[shard] = Safetensors(source / shard)
        return readers[shard].get(name)

    writer = Writer(out)
    for base in sorted(quantized):
        writer.add(
            f"{base}.weight",
            dequantize(get(f"{base}.weight"), get(f"{base}.weight_scale"), get(f"{base}.weight_scale_2")),
        )
    packed = {f"{base}.weight" for base in quantized}
    for name in sorted(index):
        # Every scale tensor carries quantization only, so none of them reaches the mirror.
        if name.endswith((".input_scale", ".weight_scale", ".weight_scale_2")) or name in packed:
            continue
        writer.add(name, get(name))
    writer.flush()
    return writer


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--source", type=Path, help="Read this snapshot instead of downloading the pinned one")
    args = parser.parse_args()
    source = args.source or Path(snapshot_download(REPOSITORY, revision=REVISION))
    args.out.mkdir(parents=True, exist_ok=True)
    writer = convert(source, args.out)
    (args.out / "model.safetensors.index.json").write_text(
        json.dumps({"metadata": {"total_size": writer.total}, "weight_map": writer.weight_map}, indent=1)
    )
    for name in COPY:
        if (source / name).is_file():
            shutil.copyfile(source / name, args.out / name)
    if (source / "prompt").is_dir():
        shutil.copytree(source / "prompt", args.out / "prompt", dirs_exist_ok=True)
    config = json.loads((source / "config.json").read_text())
    config.pop("quantization_config", None)
    (args.out / "config.json").write_text(json.dumps(config, indent=1))
    print(f"done: {len(writer.weight_map)} tensors in {writer.index} shards at {args.out}", flush=True)


if __name__ == "__main__":
    main()
