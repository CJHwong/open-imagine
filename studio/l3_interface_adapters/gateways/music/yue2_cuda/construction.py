"""Composition factory for music/yue2_cuda: one entry per measured build.

The picker is the backend list, so a build the studio can run is an entry. Both entries
start the same child with a different `--quantize`, and each one carries its own badge, its
own estimate and its own memory figure.
"""

import os
import shutil
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.music.yue2_cuda.storage_assets import storage_assets_for
from studio.l3_interface_adapters.gateways.music.yue2_cuda.yue2_cuda_backend_gateway import Yue2CudaBackendGateway
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild

DEFAULT_MODEL = "m-a-p/YuE2-3B"
DEFAULT_PACK_DIR = "~/.cache/open-imagine/yue2-nvfp4"
"""Where `quantize = "nvfp4"` keeps the packed weights it builds on first use."""

# backend id -> (name in the picker, the build this entry runs, its resident memory in GiB).
# bf16 is 18.1 GiB because it holds the weights as they ship; nvfp4 is 9.1 because the pack
# quarters the lyrics stages. Both from the measured first run of each build, DGX Spark,
# 2026-11-15.
BUILDS = {
    "yue2_cuda": ("YuE2", "bf16", 18.1),
    "yue2_cuda_nvfp4": ("YuE2 NVFP4", "nvfp4", 9.1),
}

QUANTIZERS = {"bf16", "fp8", "nvfp4"}


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("YuE2 on CUDA needs uv on PATH.")
    return found


def backend_factory(backend_id: str):
    """The factory for one entry. The entry names the build it runs, and the section keeps
    its own settings, so two entries can keep two packs."""
    name, default_quantize, _ = BUILDS[backend_id]

    def build(config: ModelConfigurationGateway, **_):
        settings = config.backend(backend_id)
        model = str(settings.get("model", DEFAULT_MODEL))
        quantize = str(settings.get("quantize", default_quantize))
        if quantize not in QUANTIZERS:
            raise ModelConfigurationError(
                f"[{backend_id}].quantize is {quantize!r}; it must be one of {', '.join(sorted(QUANTIZERS))}."
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
        return Yue2CudaBackendGateway(StdioChild(command), backend_id=backend_id, name=name, badge=quantize)

    return build


PROVIDER = ModelProvider(
    "yue2_cuda",
    "music",
    backend_factory("yue2_cuda"),
    engine="cuda",
    storage_assets=storage_assets_for("yue2_cuda"),
    storage_name="YuE2",
    resident_gib=BUILDS["yue2_cuda"][2],
)

NVFP4_PROVIDER = ModelProvider(
    "yue2_cuda_nvfp4",
    "music",
    backend_factory("yue2_cuda_nvfp4"),
    engine="cuda",
    # The same checkpoint as the bf16 entry, plus the pack it builds on first use, which no
    # provider declares. The storage page shows the repository once under this name.
    storage_assets=storage_assets_for("yue2_cuda_nvfp4"),
    storage_name="YuE2",
    resident_gib=BUILDS["yue2_cuda_nvfp4"][2],
)
