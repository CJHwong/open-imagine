"""Download the three pinned weight sources without loading a model."""

import argparse
from pathlib import Path

from .runtime import DEFAULT_MODELS

SOURCES = (
    (
        "DeepBeepMeep/MiniMax-H3",
        "1393e9b5638161ed1206bf75cdb57043f75f6526",
        "deepbeep-pruned-bf16",
        ("MiniMax-H3-FL2VA-pruned_bf16.safetensors",),
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
