"""Composition factory for video/ltx25_cuda."""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.stdio_child import StdioChild
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.ltx25_cuda_backend_gateway import Ltx25CudaBackendGateway
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.rewriter import Ltx25CudaRewriter, RewrittenPrompts
from studio.l3_interface_adapters.gateways.video.ltx25_cuda.storage_assets import storage_assets

DEFAULT_MODEL = "Lightricks/LTX-2.5-Diffusers"


def uv_launcher() -> str:
    """The uv that runs the studio, so the child's environment matches its version."""
    found = os.environ.get("UV") or shutil.which("uv")
    if not found:
        raise ModelConfigurationError("LTX-2.5 on CUDA needs uv on PATH.")
    return found


@dataclass(frozen=True)
class SharedChild:
    """The video child, and the record of the prompts its enhancer wrote."""

    child: StdioChild
    rewritten: RewrittenPrompts = field(default_factory=RewrittenPrompts)


def _new_child(config: ModelConfigurationGateway) -> SharedChild:
    model = str(config.backend("ltx25_cuda").get("model", DEFAULT_MODEL))
    script = Path(__file__).with_name("ltx25_cuda_child.py")
    return SharedChild(
        StdioChild([uv_launcher(), "run", "--python", "3.12", "--script", str(script), "--model", model])
    )


def _resident(config: ModelConfigurationGateway, services) -> SharedChild:
    """The child the backend and its rewriter share in one studio. The enhancer is part of the
    video pipeline, so a second child would hold the video model twice. A build outside a
    studio, which only a test or a single backend makes, gets a child of its own."""
    if services is None:
        return _new_child(config)
    shared = services.shared.get("ltx25_cuda")
    if not isinstance(shared, SharedChild):
        shared = services.shared["ltx25_cuda"] = _new_child(config)
    return shared


def ltx25_cuda_backend(config: ModelConfigurationGateway, services=None, **_):
    shared = _resident(config, services)
    return Ltx25CudaBackendGateway(shared.child, shared.rewritten)


def build_rewriter(config: ModelConfigurationGateway, backend_id: str, *, services=None, **_):
    shared = _resident(config, services)
    return Ltx25CudaRewriter(shared.child, shared.rewritten)


PROVIDER = ModelProvider(
    "ltx25_cuda",
    "video",
    ltx25_cuda_backend,
    engine="cuda",
    rewriter=build_rewriter,
    storage_assets=storage_assets,
    storage_name="LTX-2.5",
    # 80.3 GB of module weights, measured on the DGX Spark, 2026-11-15.
    resident_gib=80.0,
)
