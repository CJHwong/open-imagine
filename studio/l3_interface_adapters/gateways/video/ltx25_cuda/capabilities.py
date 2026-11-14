"""The LTX-2.5 form on the CUDA engine.

The shapes, frame counts and reference rules are the model's, so they come from the same
shared record the MLX backend uses. What differs is the identity and the precision the
weights actually run at.
"""

from dataclasses import replace

from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l3_interface_adapters.gateways.video.shared.capabilities import ltx25_mlx_capabilities


def ltx25_cuda_capabilities() -> VideoCapabilities:
    return replace(
        ltx25_mlx_capabilities(),
        backend_id="ltx25_cuda",
        name="LTX-2.5 (CUDA)",
        badge="bf16",
        description="Clips with a soundtrack on an NVIDIA GPU, from the diffusers pipeline.",
        precision="bf16",
    )
