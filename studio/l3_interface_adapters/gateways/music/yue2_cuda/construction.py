"""Composition factory for music/yue2_cuda."""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.music.yue2_cuda.storage_assets import storage_assets
from studio.l3_interface_adapters.gateways.music.yue2_cuda.yue2_cuda_backend_gateway import Yue2CudaBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "m-a-p/YuE2-3B"
DEFAULT_PACK_DIR = "~/.cache/open-imagine/yue2-nvfp4"
"""Where `quantize = "nvfp4"` keeps the packed weights it builds on first use."""


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("YuE2 on CUDA needs uv on PATH.")
    return found


QUANTIZERS = {"bf16", "fp8", "nvfp4"}


def yue2_cuda_backend(config: ModelConfigurationGateway, **_):
    settings = config.backend("yue2_cuda")
    model = str(settings.get("model", DEFAULT_MODEL))
    quantize = str(settings.get("quantize", "bf16"))
    if quantize not in QUANTIZERS:
        raise ModelConfigurationError(
            f"[yue2_cuda].quantize is {quantize!r}; it must be one of {', '.join(sorted(QUANTIZERS))}."
        )
    script = Path(__file__).with_name("yue2_cuda_child.py")
    pack_dir = str(settings.get("pack_dir", DEFAULT_PACK_DIR))
    command = [
        uv_launcher(),
        "run",
        "--python",
        "3.12",
        "--script",
        str(script),
        "--model",
        model,
        "--quantize",
        quantize,
        "--pack-dir",
        str(Path(pack_dir).expanduser()),
    ]
    return Yue2CudaBackendGateway(StdioChild(command))


PROVIDER = ModelProvider(
    "yue2_cuda",
    "music",
    yue2_cuda_backend,
    engine="cuda",
    storage_assets=storage_assets,
    storage_name="YuE2",
    # The 1.8 GB pack plus the acoustic decoder and vocoder, DGX Spark, 2026-11-15.
    resident_gib=10.0,
)
