"""LTX's shared enhancer belongs to one Studio instance."""

from studio.l3_interface_adapters.gateways.video.gemma3.gemma3_prompt_rewriter_gateway import (
    Gemma3PromptRewriterGateway,
)
from studio.l3_interface_adapters.gateways.video.gemma3.prompt_enhancer import Gemma3PromptEnhancer


def enhancer(services):
    key = "ltx_prompt_enhancer"
    if key not in services.shared:
        services.shared[key] = Gemma3PromptEnhancer(services.run_process)
    return services.shared[key]


def build_rewriter(config, backend_id, *, services):
    return Gemma3PromptRewriterGateway(enhancer(services))
