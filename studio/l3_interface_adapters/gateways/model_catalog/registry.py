"""The single explicit list of supported built-in integrations."""

from functools import partial

from studio.l3_interface_adapters.gateways.image.flux2.construction import PROVIDER as flux2_provider
from studio.l3_interface_adapters.gateways.image.flux3.construction import PROVIDER as flux3_provider
from studio.l3_interface_adapters.gateways.image.krea2.construction import PROVIDER as krea2_provider
from studio.l3_interface_adapters.gateways.image.minimax_h3_image.construction import (
    PROVIDER as minimax_h3_image_provider,
)
from studio.l3_interface_adapters.gateways.image.qwen21.construction import PROVIDER as qwen21_provider
from studio.l3_interface_adapters.gateways.image.qwen21_turbo.construction import PROVIDER as qwen21_turbo_provider
from studio.l3_interface_adapters.gateways.image.viggle_turbo.construction import PROVIDER as viggle_turbo_provider
from studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway import CatalogMemoryEstimateGateway
from studio.l3_interface_adapters.gateways.music.yue2.construction import PROVIDER as yue2_provider
from studio.l3_interface_adapters.gateways.video.ltx23.construction import PROVIDER as ltx23_provider
from studio.l3_interface_adapters.gateways.video.ltx25.construction import PROVIDER as ltx25_provider
from studio.l3_interface_adapters.gateways.video.minimax_h3.construction import PROVIDER as minimax_h3_provider
from studio.l3_interface_adapters.gateways.voice.auk.construction import PROVIDER as auk_provider
from studio.l3_interface_adapters.gateways.voice.auk_flash.construction import PROVIDER as auk_flash_provider
from studio.l3_interface_adapters.gateways.voice.drama3.construction import PROVIDER as drama3_provider

BUILTIN_PROVIDERS = (
    qwen21_provider,
    qwen21_turbo_provider,
    flux2_provider,
    flux3_provider,
    krea2_provider,
    minimax_h3_image_provider,
    viggle_turbo_provider,
    ltx25_provider,
    ltx23_provider,
    minimax_h3_provider,
    auk_flash_provider,
    auk_provider,
    drama3_provider,
    yue2_provider,
)


def backend_factories(kind, execute_process):
    return {
        provider.backend_id: partial(provider.create, execute_process=execute_process)
        for provider in BUILTIN_PROVIDERS
        if provider.kind == kind
    }


def build_memory_estimates(config):
    return CatalogMemoryEstimateGateway(
        {
            (provider.kind, provider.backend_id): provider.estimator(config)
            for provider in BUILTIN_PROVIDERS
            if provider.estimator is not None
        }
    )


def provider_for(kind, name):
    return next(
        (provider for provider in BUILTIN_PROVIDERS if provider.kind == kind and provider.backend_id == name), None
    )
