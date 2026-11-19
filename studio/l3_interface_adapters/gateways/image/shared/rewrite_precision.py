"""The precision a CUDA prompt rewriter holds its language model in."""

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway

# `rewrite_quantize` is a width in bits, as it is for the MLX rewriter. A CUDA child holds
# its card at full precision or in fp8; each child's docstring holds the measurement.
REWRITE_PRECISIONS = {0: "bf16", 8: "fp8"}


def rewrite_precision(config: ModelConfigurationGateway, backend_id: str) -> str:
    quantize = config.backend(backend_id).get("rewrite_quantize", 0)
    # bool is an int in Python: `false` equals 0 and would pass as full precision.
    if isinstance(quantize, bool) or quantize not in REWRITE_PRECISIONS:
        raise ModelConfigurationError(f"rewrite_quantize under [{backend_id}] must be 0 or 8, not {quantize!r}")
    return REWRITE_PRECISIONS[quantize]
