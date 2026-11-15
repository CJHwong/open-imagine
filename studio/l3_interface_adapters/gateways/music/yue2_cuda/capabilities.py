from studio.l1_entities.music_capabilities import MusicCapabilities


def yue2_cuda_capabilities():
    """Every mode the MLX backend offers. Transcribe runs the pinned upstream script on CUDA."""
    return MusicCapabilities(
        "yue2_cuda",
        "YuE2 (CUDA)",
        "BF16",
        description="Complete songs from style and lyrics, with melody, chord and cover from a recording.",
        estimate=None,
    )
