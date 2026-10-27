"""A Qwen-Image-2.1 checkpoint on the studio's own engine: the plugin names it, and the host
builds it.

The record holds no code. The folder, the LoRAs and the rewriter models go in the
[example_qwen] section of the settings. With the base model's own folder and the linear
schedule, it draws what qwen21 draws.
"""

from studio.plugins.image import QwenCheckpoint

plugin = QwenCheckpoint(
    backend_id="example_qwen",
    name="Example Qwen checkpoint",
    description="Plugin example: a Qwen-Image-2.1 checkpoint from a folder, on the studio's mflux engine.",
)
