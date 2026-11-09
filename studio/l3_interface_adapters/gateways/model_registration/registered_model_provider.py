"""Translate public SDK declarations to the inward provider record."""

from functools import partial

from studio.l2_use_cases.model_provider import ModelProvider
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.construction import qwen_checkpoint_backend
from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter_configuration import (
    build_rewriter as qwen_rewriter,
)
from studio.l3_interface_adapters.gateways.model_registration.model_backend_factory import ModelBackendFactory
from studio.l3_interface_adapters.gateways.video.ltx_checkpoint.construction import ltx_checkpoint_backend
from studio.l3_interface_adapters.gateways.video.ltx_runtime.rewriter_configuration import (
    build_rewriter as ltx_rewriter,
)
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration


def registered_model_provider(catalog, kind, name, execute_process):
    registration = catalog.declaration(kind, name)
    if isinstance(registration, QwenCheckpointRegistration):
        return ModelProvider(
            name, kind, partial(qwen_checkpoint_backend, checkpoint=registration), rewriter=qwen_rewriter
        )
    if isinstance(registration, LtxCheckpointRegistration):
        return ModelProvider(name, kind, partial(ltx_checkpoint_backend, pack=registration), rewriter=ltx_rewriter)
    factory = ModelBackendFactory(catalog, execute_process)
    return ModelProvider(
        name,
        kind,
        partial(factory.build, kind, name),
        rewriter=(lambda config, backend_id, **kwargs: factory.rewriter(kind, name, config, **kwargs))
        if registration.rewriter
        else None,
        requires_mlx=False,
    )
