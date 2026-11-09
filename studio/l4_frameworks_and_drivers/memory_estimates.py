"""Wire built-in calibrated estimators into the generic memory-estimate catalog."""

from functools import partial

from studio.l3_interface_adapters.gateways.image.krea2.memory_estimate import estimate_peak_gib as krea_estimate
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.memory_estimate import (
    estimate_peak_gib as qwen_turbo_estimate,
)
from studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway import CatalogMemoryEstimateGateway
from studio.l3_interface_adapters.gateways.music.yue2.memory_estimate import estimate_peak_gib as yue_estimate
from studio.l3_interface_adapters.gateways.video.ltx25.memory_estimate import estimate_peak_gib as ltx_estimate
from studio.l3_interface_adapters.gateways.voice.drama3.memory_estimate import estimate_peak_gib as drama_estimate


def build_memory_estimates(qwen_turbo_quantize: int | None = None) -> CatalogMemoryEstimateGateway:
    return CatalogMemoryEstimateGateway(
        {
            ("image", "qwen21_turbo"): partial(qwen_turbo_estimate, quantize=qwen_turbo_quantize),
            ("image", "krea2"): krea_estimate,
            ("video", "ltx25_mlx"): ltx_estimate,
            ("voice", "drama3"): drama_estimate,
            ("music", "yue2"): yue_estimate,
        }
    )
