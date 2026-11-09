"""Composition factory for image/qwen_checkpoint."""

from functools import partial

from studio.l1_entities.model_configuration_error import ModelConfigurationError
from studio.l2_use_cases.boundaries.model_configuration_gateway import ModelConfigurationGateway
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.capabilities import qwen_checkpoint_capabilities
from studio.l3_interface_adapters.gateways.image.qwen_checkpoint.qwen_checkpoint_backend_gateway import (
    QwenCheckpointBackendGateway,
)
from studio.l3_interface_adapters.gateways.image.qwen_runtime import edit as qwen_edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime import generator as qwen_generator
from studio.l3_interface_adapters.gateways.image.qwen_runtime.edit import Qwen21Edit
from studio.l3_interface_adapters.gateways.image.qwen_runtime.generator import Qwen21Generator
from studio.l3_interface_adapters.gateways.image.shared.mflux_runtime import base_model_config
from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import (
    AncestralSeedHook,
    edit_scheduler,
    generate_scheduler,
)
from studio.l3_interface_adapters.gateways.model_configuration.lora_table import parse_lora_tables
from studio.l3_interface_adapters.gateways.model_configuration.lora_table_policy import LoraTablePolicy
from studio.l3_interface_adapters.gateways.model_configuration.offering import badge, offering
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration

LORA_POLICY = LoraTablePolicy(mode_scoped=True)


def qwen_checkpoint_backend(
    config: ModelConfigurationGateway, checkpoint: QwenCheckpointRegistration, **_
) -> QwenCheckpointBackendGateway:
    """A checkpoint that a plugin names, run by the two models that qwen21 drives.

    The folder, the quantization, the LoRAs and the rewriter models come from the plugin's
    own section. The folder gets the base model's config, because the weights come from the
    base model. The gateway checks the folder when a run starts, as the LTX packs do:
    `--all-backends` offers every installed checkpoint, with or without a section.
    """
    backend_id = checkpoint.backend_id
    settings = config.backend(backend_id)
    model_dir = str(settings.get("model_dir", ""))
    quantize = settings.get("quantize")
    try:
        capabilities = qwen_checkpoint_capabilities(
            backend_id,
            checkpoint.name,
            badge=badge(quantize),
            description=checkpoint.description,
            scheduler=checkpoint.scheduler,
            generate_sampler=checkpoint.generate_sampler,
            steps=checkpoint.steps,
            generate_size=checkpoint.generate_size,
            max_edit_references=checkpoint.max_edit_references,
        )
    except ValueError as error:
        raise ModelConfigurationError(f"Cannot build the Qwen checkpoint {backend_id}: {error}") from None
    loras = parse_lora_tables(config.backend(backend_id), backend_id, policy=LORA_POLICY)
    callbacks = (AncestralSeedHook(),) if checkpoint.generate_sampler == "euler_ancestral" else ()
    return offering(
        QwenCheckpointBackendGateway(
            Qwen21Generator(
                quantize,
                build=partial(qwen_generator.build_model, model_config=base_model_config, callbacks=callbacks),
                scheduler=generate_scheduler(checkpoint.scheduler, checkpoint.generate_sampler),
                model_path=model_dir,
                lora_files=loras,
            ),
            Qwen21Edit(
                quantize,
                build=partial(qwen_edit.build_model, model_config=base_model_config),
                model_path=model_dir,
                lora_files=loras,
            ),
            capabilities,
            model_dir,
            edit_scheduler=edit_scheduler(checkpoint.scheduler),
            loras=loras,
        ),
        backend_id,
    )
