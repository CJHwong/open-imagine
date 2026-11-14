from studio.l1_entities.music_capabilities import MusicCapabilities


def yue2_cuda_capabilities():
    """Generate and plan. Transcribe and cover are not wired on this engine yet."""
    return MusicCapabilities(
        "yue2_cuda",
        "YuE2 (CUDA)",
        "BF16",
        modes=("generate", "plan"),
        description="Complete songs from style and lyrics on an NVIDIA GPU.",
        estimate=None,
    )
