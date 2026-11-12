"""The composition root: builds every part and wires them. No side effects beyond that."""

import threading
from collections.abc import Callable
from pathlib import Path

from studio.l2_use_cases.boundaries.prompt_rewriter_gateway import PromptRewriterGateway
from studio.l2_use_cases.boundaries.studio_settings_gateway import StudioSettingsGateway
from studio.l2_use_cases.cancel_rewrite_use_case import CancelRewriteUseCase
from studio.l2_use_cases.cancel_run_use_case import CancelRunUseCase
from studio.l2_use_cases.complete_operation_use_case import CompleteOperationUseCase
from studio.l2_use_cases.describe_studio_use_case import DescribeStudioUseCase
from studio.l2_use_cases.inspect_model_storage_use_case import InspectModelStorageUseCase
from studio.l2_use_cases.model_services import ModelServices
from studio.l2_use_cases.plan_image_use_case import PlanImageUseCase
from studio.l2_use_cases.plan_video_use_case import PlanVideoUseCase
from studio.l2_use_cases.prepare_batch_use_case import PrepareBatchUseCase
from studio.l2_use_cases.read_progress_use_case import ReadProgressUseCase
from studio.l2_use_cases.read_rewrite_progress_use_case import ReadRewriteProgressUseCase
from studio.l2_use_cases.release_model_use_case import ReleaseModelUseCase
from studio.l2_use_cases.remove_model_assets_use_case import RemoveModelAssetsUseCase
from studio.l2_use_cases.rewrite_prompt_use_case import RewritePromptUseCase
from studio.l2_use_cases.run_image_use_case import RunImageUseCase
from studio.l2_use_cases.run_music_use_case import RunMusicUseCase
from studio.l2_use_cases.run_video_use_case import RunVideoUseCase
from studio.l2_use_cases.run_voice_use_case import RunVoiceUseCase
from studio.l2_use_cases.switch_backend_use_case import SwitchBackendUseCase
from studio.l2_use_cases.switch_music_backend_use_case import SwitchMusicBackendUseCase
from studio.l2_use_cases.switch_video_backend_use_case import SwitchVideoBackendUseCase
from studio.l2_use_cases.switch_voice_backend_use_case import SwitchVoiceBackendUseCase
from studio.l3_interface_adapters.api.json_api import JsonApi
from studio.l3_interface_adapters.api.resource_admission import ResourceAdmission
from studio.l3_interface_adapters.controllers.form_controller import FormController
from studio.l3_interface_adapters.controllers.music_controller import MusicController
from studio.l3_interface_adapters.controllers.video_controller import VideoController
from studio.l3_interface_adapters.controllers.voice_controller import VoiceController
from studio.l3_interface_adapters.gateways.catalog_prompt_rewriter_gateway import CatalogPromptRewriterGateway
from studio.l3_interface_adapters.gateways.gpu_thread import GpuThread
from studio.l3_interface_adapters.gateways.image.thread_confined_backend_gateway import ThreadConfinedBackendGateway
from studio.l3_interface_adapters.gateways.in_memory.backend_catalog_gateway import InMemoryBackendCatalogGateway
from studio.l3_interface_adapters.gateways.in_memory.model_residency_gateway import InMemoryModelResidencyGateway
from studio.l3_interface_adapters.gateways.in_memory.music_backend_catalog_gateway import (
    InMemoryMusicBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.in_memory.operation_gateway import InMemoryOperationGateway
from studio.l3_interface_adapters.gateways.in_memory.progress_gateway import InMemoryProgressGateway
from studio.l3_interface_adapters.gateways.in_memory.reference_store_gateway import InMemoryReferenceStoreGateway
from studio.l3_interface_adapters.gateways.in_memory.rewrite_progress_gateway import InMemoryRewriteProgressGateway
from studio.l3_interface_adapters.gateways.in_memory.studio_settings_gateway import InMemoryStudioSettingsGateway
from studio.l3_interface_adapters.gateways.in_memory.video_backend_catalog_gateway import (
    InMemoryVideoBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.in_memory.voice_backend_catalog_gateway import (
    InMemoryVoiceBackendCatalogGateway,
)
from studio.l3_interface_adapters.gateways.memory.catalog_memory_estimate_gateway import CatalogMemoryEstimateGateway
from studio.l3_interface_adapters.gateways.model_catalog.composite_model_catalog_gateway import (
    CompositeModelCatalogGateway,
)
from studio.l3_interface_adapters.gateways.model_catalog.plugin_factories import plugin_factories
from studio.l3_interface_adapters.gateways.model_catalog.registry import (
    BUILTIN_PROVIDERS,
    backend_factories,
    build_memory_estimates,
)
from studio.l3_interface_adapters.gateways.model_catalog.rewriters import build_rewriters as build_rewriters
from studio.l3_interface_adapters.gateways.model_catalog.storage_definitions import (
    protected_model_paths,
    storage_definitions,
)
from studio.l3_interface_adapters.gateways.model_registration.installed_model_catalog import InstalledModelCatalog
from studio.l3_interface_adapters.gateways.stub.image_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.stub.music_backend_gateway import StubMusicBackendGateway
from studio.l3_interface_adapters.gateways.stub.video_backend_gateway import StubVideoBackendGateway
from studio.l3_interface_adapters.gateways.stub.voice_backend_gateway import StubVoiceBackendGateway
from studio.l3_interface_adapters.gateways.thread_confined_prompt_rewriter import ThreadConfinedPromptRewriter
from studio.l3_interface_adapters.presenters.html_presenter import HtmlPresenter
from studio.l3_interface_adapters.presenters.locale import LocaleCatalog
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.connect import DumbpipeTransport
from studio.l4_frameworks_and_drivers.engines import require_mlx
from studio.l4_frameworks_and_drivers.http_server import make_handler
from studio.l4_frameworks_and_drivers.json_studio_settings_gateway import JsonStudioSettingsGateway
from studio.l4_frameworks_and_drivers.model_asset_storage_gateway import ModelAssetStorageGateway
from studio.l4_frameworks_and_drivers.python_entry_points import entry_points
from studio.l4_frameworks_and_drivers.studio import Studio as Studio
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.l4_frameworks_and_drivers.system_memory import memory_headroom

IMAGE_BACKEND_FACTORIES = backend_factories("image", SubprocessRunner().execute)
VIDEO_BACKEND_FACTORIES = backend_factories("video", SubprocessRunner().execute)
VOICE_BACKEND_FACTORIES = backend_factories("voice", SubprocessRunner().execute)
MUSIC_BACKEND_FACTORIES = backend_factories("music", SubprocessRunner().execute)

_build_rewriters = build_rewriters


def build_rewriters(config, plugins=None, stub=False):
    return _build_rewriters(config, plugins, stub, execute_process=SubprocessRunner().execute)


PAGE = Path(__file__).with_name("web") / "page.html"

GIB = 1024**3
# The stub has no GPU and no memory probe. A boundary policy still needs a number, and
# 64 GiB is the machine every estimator was calibrated on.
STUB_MEMORY_GIB = 64.0


def resident_memory() -> dict[str, float]:
    """The idle footprint of each built-in model that declares one."""
    return {
        provider.backend_id: provider.resident_gib
        for provider in BUILTIN_PROVIDERS
        if provider.resident_gib is not None
    }


def build_image_backends(config: Config, plugins: InstalledModelCatalog | None = None, stub: bool = False) -> dict:
    """The backends the page offers, and no others: an unused one needs no settings.
    Each loads nothing until it is used."""
    registry = {**IMAGE_BACKEND_FACTORIES, **plugin_factories(plugins, "image", stub, SubprocessRunner().execute)}
    unknown = [backend_id for backend_id in config.visible_backends if backend_id not in registry]
    if unknown:
        raise ConfigError(f"no backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {backend_id: registry[backend_id](config) for backend_id in config.visible_backends}


def build_video_backends(
    config: Config,
    enhanced_prompt=None,
    plugins: InstalledModelCatalog | None = None,
    stub: bool = False,
    *,
    services=None,
) -> dict:
    registry = {
        **VIDEO_BACKEND_FACTORIES,
        **plugin_factories(plugins, "video", stub, SubprocessRunner().execute, services),
    }
    unknown = [backend_id for backend_id in config.visible_video_backends if backend_id not in registry]
    if unknown:
        raise ConfigError(f"no video backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {
        backend_id: registry[backend_id](config, enhanced_prompt=enhanced_prompt, services=services)
        for backend_id in config.visible_video_backends
    }


def build_voice_backends(config: Config, plugins: InstalledModelCatalog | None = None, stub: bool = False):
    registry = {**VOICE_BACKEND_FACTORIES, **plugin_factories(plugins, "voice", stub, SubprocessRunner().execute)}
    unknown = [name for name in config.visible_voice_backends if name not in registry]
    if unknown:
        raise ConfigError(f"no voice backend called {', '.join(unknown)}. Known: {', '.join(registry)}")
    return {name: registry[name](config) for name in config.visible_voice_backends}


def build_music_backends(config: Config, stub=False):
    unknown = set(config.visible_music_backends) - MUSIC_BACKEND_FACTORIES.keys()
    if unknown:
        raise ConfigError(f"no music backend called {', '.join(sorted(unknown))}")
    return {
        name: StubMusicBackendGateway(MUSIC_BACKEND_FACTORIES[name](config).capabilities())
        if stub
        else MUSIC_BACKEND_FACTORIES[name](config)
        for name in config.visible_music_backends
    }


def discover_plugins() -> InstalledModelCatalog:
    return InstalledModelCatalog(
        {
            "image": IMAGE_BACKEND_FACTORIES,
            "video": VIDEO_BACKEND_FACTORIES,
            "voice": VOICE_BACKEND_FACTORIES,
            "music": MUSIC_BACKEND_FACTORIES,
        },
        entry_points,
    )


def create_studio(
    config: Config,
    stub: bool = False,
    plugins: InstalledModelCatalog | None = None,
    allowed_origins: tuple[str, ...] = (),
    private_results_dir: Path | None = None,
    port: int | None = None,
) -> Studio:
    """With `stub`, each backend keeps its form and fakes its engine: for work on the page.
    `allowed_origins` are the pages at another address that may post, such as a proxy."""
    plugins = plugins if plugins is not None else discover_plugins()
    backends = build_image_backends(config, plugins, stub)
    services = ModelServices(SubprocessRunner().execute)
    catalog = CompositeModelCatalogGateway(BUILTIN_PROVIDERS, plugins, services.run_process)
    # Backend constructors and rewriters share only this instance's runtime resources.
    video_backends = build_video_backends(config, plugins=plugins, stub=stub, services=services)
    voice_backends = build_voice_backends(config, plugins, stub)
    music_backends = build_music_backends(config, stub)
    rewriters = _build_rewriters(config, plugins, stub, execute_process=services.run_process, services=services)
    video_rewriters = _build_rewriters(
        config,
        plugins,
        stub,
        execute_process=services.run_process,
        services=services,
        kind="video",
        names=config.visible_video_backends,
    )
    if stub:
        voice_backends = {
            name: StubVoiceBackendGateway(backend.capabilities()) for name, backend in voice_backends.items()
        }
        backends = {name: StubBackendGateway(backend.capabilities()) for name, backend in backends.items()}
        video_backends = {
            name: StubVideoBackendGateway(backend.capabilities()) for name, backend in video_backends.items()
        }
    elif any(
        catalog.provider(kind, name).requires_mlx
        for kind, gateways in (("image", backends), ("video", video_backends), ("voice", voice_backends))
        for name in gateways
    ):
        require_mlx()
    if private_results_dir is None and not stub:
        private_results_dir = Path.home() / ".local" / "share" / "open-imagine" / "private-results"
    total_memory_gib = None
    if config.memory_policy == "boundary":
        total_memory_gib = STUB_MEMORY_GIB if stub else memory_headroom()[0] / GIB
    connect = None
    if config.connect_enabled:
        assert config.connect_identity_path is not None  # load_config always resolves it
        connect = DumbpipeTransport(
            config.connect_dumbpipe_path or None,
            config.connect_identity_path,
            port or config.connect_studio_port,
        )
    return assemble_studio(
        backends,
        rewriters,
        config.default_backend,
        config.visible_backends,
        video_backends=video_backends,
        default_video_id=config.default_video_backend,
        visible_video_ids=config.visible_video_backends,
        music_backends=music_backends,
        default_music_id=config.default_music_backend,
        visible_music_ids=config.visible_music_backends,
        voice_backends=voice_backends,
        default_voice_id=config.default_voice_backend,
        visible_voice_ids=config.visible_voice_backends,
        video_rewriters=video_rewriters,
        allowed_origins=allowed_origins,
        private_results_dir=private_results_dir,
        resource_memory_headroom=None if stub else memory_headroom,
        memory_estimates=build_memory_estimates(config),
        model_storage=None
        if stub
        else ModelAssetStorageGateway(
            storage_definitions(BUILTIN_PROVIDERS, plugins, config),
            [
                Path.home() / "Library/Caches/models",
                Path.home() / "Library/Caches/open-imagine/engines",
                *(Path(root) for provider in BUILTIN_PROVIDERS for root in provider.storage_roots),
            ],
            protected_paths=(*protected_model_paths(BUILTIN_PROVIDERS, plugins, config), str(private_results_dir)),
        ),
        settings=(
            JsonStudioSettingsGateway(config.settings_path, config.require_memory_estimate)
            if config.settings_path is not None and not stub
            else InMemoryStudioSettingsGateway(config.require_memory_estimate)
        ),
        resident_memory=resident_memory(),
        memory_policy=config.memory_policy,
        memory_boundary_percent=config.memory_boundary_percent,
        total_memory_gib=total_memory_gib,
        queue_max_size=config.queue_max_size,
        connect=connect,
    )


def assemble_studio(
    backends: dict,
    rewriters: dict,
    default_id: str,
    visible_ids: tuple[str, ...],
    video_backends: dict | None = None,
    default_video_id: str | None = None,
    visible_video_ids: tuple[str, ...] = (),
    music_backends=None,
    default_music_id="yue2",
    visible_music_ids=(),
    voice_backend=None,
    voice_backends=None,
    default_voice_id="auk",
    visible_voice_ids=(),
    video_rewriter: PromptRewriterGateway | None = None,
    video_rewriters: dict | None = None,
    allowed_origins: tuple[str, ...] = (),
    private_results_dir: Path | None = None,
    resource_memory_headroom: Callable[[], tuple[int, int]] | None = None,
    memory_estimates=None,
    settings: StudioSettingsGateway | None = None,
    model_storage=None,
    resident_memory: dict[str, float] | None = None,
    memory_policy: str = "immediate",
    memory_boundary_percent: int = 84,
    total_memory_gib: float | None = None,
    queue_max_size: int = 0,
    connect=None,
) -> Studio:
    """Wire both model catalogs and one shared model-memory slot."""
    settings = settings if settings is not None else InMemoryStudioSettingsGateway()
    gpu = GpuThread()
    engine_lock = threading.Lock()
    confined = {name: ThreadConfinedBackendGateway(backend, gpu) for name, backend in backends.items()}
    catalog = InMemoryBackendCatalogGateway(confined, default_id=default_id, visible_ids=visible_ids)
    video_catalog = None
    if video_backends:
        selected_video_id = default_video_id or next(iter(video_backends))
        offered_video_ids = visible_video_ids or tuple(video_backends)
        video_catalog = InMemoryVideoBackendCatalogGateway(
            video_backends,
            default_id=selected_video_id,
            visible_ids=offered_video_ids,
        )
    if voice_backend is not None:
        voice_backends = {"auk": voice_backend}
    voice_catalog = None
    if voice_backends:
        voice_catalog = InMemoryVoiceBackendCatalogGateway(
            voice_backends, default_voice_id, visible_voice_ids or tuple(voice_backends)
        )
    if video_rewriters is not None and video_catalog is not None:
        video_rewriter = CatalogPromptRewriterGateway(video_rewriters, video_catalog)
    if video_rewriter is not None:
        video_rewriter = ThreadConfinedPromptRewriter(video_rewriter, gpu)
    music_catalog = None
    if music_backends:
        music_catalog = InMemoryMusicBackendCatalogGateway(
            music_backends, default_music_id, visible_music_ids or tuple(music_backends)
        )
    runtimes = {**confined, **(video_backends or {}), **(voice_backends or {}), **(music_backends or {})}
    boundary_gib = None
    if memory_policy == "boundary" and total_memory_gib is not None:
        boundary_gib = total_memory_gib * memory_boundary_percent / 100
    residency = InMemoryModelResidencyGateway(
        runtimes,
        policy=memory_policy,
        boundary_gib=boundary_gib,
        footprints=resident_memory,
    )
    resource_admission = (
        ResourceAdmission(
            resource_memory_headroom,
            memory_estimates if memory_estimates is not None else CatalogMemoryEstimateGateway({}),
            settings,
        )
        if resource_memory_headroom
        else None
    )
    rewriter = ThreadConfinedPromptRewriter(CatalogPromptRewriterGateway(rewriters, catalog), gpu)
    progress = InMemoryProgressGateway(external_cancel=lambda: api.cancellation_requested())
    # The rewrite publishes its own phase, because the page draws that button from
    # it: a rewrite is worth stopping, and only once the model is writing.
    rewrite_progress = InMemoryRewriteProgressGateway(external_cancel=lambda: api.cancellation_requested())
    cancel = CancelRunUseCase(progress, residency)
    video_controller = None
    if video_catalog is not None:
        video_controller = VideoController(
            RunVideoUseCase(video_catalog, progress, engine_lock, residency),
            video_catalog,
            SwitchVideoBackendUseCase(video_catalog, engine_lock, residency),
            PlanVideoUseCase(video_catalog),
        )
    controller = FormController(
        describe=DescribeStudioUseCase(catalog, rewriter, video_catalog, video_rewriter),
        run=RunImageUseCase(
            catalog,
            progress,
            InMemoryReferenceStoreGateway(),
            engine_lock=engine_lock,
            rewriter=rewriter,
            residency=residency,
        ),
        read_progress=ReadProgressUseCase(progress),
        cancel=cancel,
        switch=SwitchBackendUseCase(catalog, engine_lock, residency),
        rewrite=RewritePromptUseCase(
            rewriter,
            catalog,
            rewrite_progress,
            video_rewriter=video_rewriter,
            engine_lock=engine_lock,
            residency=residency,
        ),
        read_rewrite_progress=ReadRewriteProgressUseCase(rewrite_progress),
        cancel_rewrite=CancelRewriteUseCase(rewrite_progress),
        release_model=ReleaseModelUseCase(engine_lock, residency),
        plan=PlanImageUseCase(catalog),
    )
    presenter = HtmlPresenter(PAGE.read_text(encoding="utf-8"), LocaleCatalog(PAGE.parent / "i18n"))
    # The JSON API rides on the same controllers: one route map, two transports.
    voice_controller = None
    if voice_catalog is not None:
        backend = voice_catalog.get(voice_catalog.active_id())
        voice_controller = VoiceController(
            RunVoiceUseCase(backend, progress, engine_lock, residency, voice_catalog),
            backend.capabilities(),
            voice_catalog,
            SwitchVoiceBackendUseCase(voice_catalog, engine_lock, residency),
        )
    music_controller = None
    if music_catalog is not None:
        music_backend = music_catalog.get(music_catalog.active_id())
        music_controller = MusicController(
            RunMusicUseCase(music_backend, progress, engine_lock, residency, music_catalog),
            music_catalog,
            SwitchMusicBackendUseCase(music_catalog, engine_lock, residency),
        )
    operations = InMemoryOperationGateway(private_directory=private_results_dir, max_queue=queue_max_size)
    api = JsonApi(
        controller,
        video_controller,
        voice_controller,
        music=music_controller,
        operations=operations,
        completion=CompleteOperationUseCase(operations),
        batches=PrepareBatchUseCase(),
        resource_admission=resource_admission,
        settings=settings,
        inspect_storage=InspectModelStorageUseCase(model_storage) if model_storage else None,
        remove_assets=RemoveModelAssetsUseCase(model_storage, engine_lock, residency) if model_storage else None,
        memory_status=residency.status,
    )
    return Studio(
        handler=make_handler(controller, presenter, video_controller, api, allowed_origins, connect),
        catalog=catalog,
        video_catalog=video_catalog,
        residency=residency,
        cancel=cancel,
        operations=operations,
        rewriter=rewriter,
        video_rewriter=video_rewriter,
        connect=connect,
    )
