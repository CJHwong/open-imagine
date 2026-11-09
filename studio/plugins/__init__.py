"""Public model SDK. Legacy API-v1 names remain aliases of the canonical records."""

from studio.l1_entities.prompt_rewrite import PromptRewrite
from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.plugins.api_version import MODEL_PLUGIN_API_VERSION
from studio.plugins.gateway_model_registration import GatewayModelRegistration
from studio.plugins.model_factory_context import ModelFactoryContext
from studio.plugins.registration import ModelRegistration

API_VERSION = MODEL_PLUGIN_API_VERSION
ModelPlugin = GatewayModelRegistration
PluginContext = ModelFactoryContext

__all__ = [
    "API_VERSION",
    "MODEL_PLUGIN_API_VERSION",
    "GatewayModelRegistration",
    "ModelFactoryContext",
    "ModelPlugin",
    "ModelRegistration",
    "PluginContext",
    "PromptRewrite",
    "PromptRewriterGateway",
]
