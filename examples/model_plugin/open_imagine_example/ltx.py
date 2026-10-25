"""An LTX-2.5 pack on the studio's own engine: the plugin names it, and the host builds it.

The record holds no code. The folder and any LoRAs go in the [example_ltx] section of the
settings, and the engine's settings stay under [mlx_video].
"""

from studio.plugins.video import LtxPack

plugin = LtxPack(
    backend_id="example_ltx",
    name="Example LTX pack",
    family="ltx25",
    description="Plugin example: an LTX-2.5 pack from a folder, on the studio's MLX engine.",
)
