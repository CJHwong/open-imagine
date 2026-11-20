"""Real MiniMax H3 on a CUDA GPU. Needs the DGX Spark and its weights."""

from pathlib import Path

import pytest

from studio.l1_entities.video_job import VideoJob
from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.construction import minimax_h3_cuda_backend
from studio.l4_frameworks_and_drivers.config import load_config


@pytest.mark.live
def test_live_minimax_h3_cuda_returns_a_clip_with_its_steps():
    config = load_config(Path(__file__).resolve().parents[5] / "studio.cuda.toml")
    backend = minimax_h3_cuda_backend(config)
    steps = []
    try:
        job = VideoJob(
            prompt="A red sailboat crosses calm water, waves lapping. Fixed camera.",
            width=512,
            height=288,
            num_frames=124,
            frame_rate=24,
            seed=7,
            fast_mode=True,
        )
        clip = backend.run(job, lambda step, total, _: steps.append((step, total)))
        assert clip.mp4 is not None and clip.mp4[4:8] == b"ftyp"
        assert (clip.width, clip.height, clip.num_frames) == (512, 288, 124)
        assert steps[-1] == (19, 19)
    finally:
        backend.release()
