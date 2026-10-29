from studio.l1_entities.music_capabilities import MusicCapabilities


def yue2_capabilities():
    # No estimate until the complete Studio child path has been measured on this machine.
    return MusicCapabilities("yue2", "YuE2 (MLX Q8)", "Q8 AR / BF16 audio")
