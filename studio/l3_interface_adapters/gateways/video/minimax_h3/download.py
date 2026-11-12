"""Download the three pinned weight sources without loading a model.

The DiT is the pre-quantized MLX pack, so no local quantization step follows the download.
"""

import argparse
from pathlib import Path

from .runtime import DEFAULT_MODELS

SOURCES = (
    (
        "pipenetwork/MiniMax-H3-MLX-8bit",
        "e55f97c8ebf340066de8d6b4554a2a6767fe54e9",
        "h3-dit-q8",
        (
            "model-00001-of-00007.safetensors",
            "model-00002-of-00007.safetensors",
            "model-00003-of-00007.safetensors",
            "model-00004-of-00007.safetensors",
            "model-00005-of-00007.safetensors",
            "model-00006-of-00007.safetensors",
            "model-00007-of-00007.safetensors",
            "model.safetensors.index.json",
            "config.json",
            "quant_config.json",
            "LICENSE",
            "README.md",
        ),
    ),
    (
        "ddalcu/MiniMax-H3-FL2VA-MLX-Serve-8bit",
        "64314cde0ac6d90f132bc94ae58e0c82f77396c6",
        "ddalcu-q8",
        (
            "text_encoder.safetensors",
            "video_vae.safetensors",
            "audio_vae.safetensors",
            "config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
            "LICENSE",
            "NOTICE",
            "MODIFICATIONS.md",
        ),
    ),
    (
        "MiniMaxAI/MiniMax-H3",
        "42ed227ee7df40d41602854ae760620d6eb651fe",
        "upstream-meta",
        ("FL2VA/text_encoder/config.json", "FL2VA/model_index.json", "LICENSE"),
    ),
)


def download(root, fetch):
    for repo, revision, folder, files in SOURCES:
        for filename in files:
            fetch(repo, filename=filename, revision=revision, local_dir=root / folder)


def main():
    from huggingface_hub import hf_hub_download

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=Path(DEFAULT_MODELS).expanduser())
    args = parser.parse_args()
    download(args.model_dir, hf_hub_download)


if __name__ == "__main__":
    main()
