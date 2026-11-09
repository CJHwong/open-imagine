from dataclasses import replace
from types import SimpleNamespace
from typing import cast
from unittest.mock import Mock

import pytest

from studio.l1_entities.lora import Lora
from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l1_entities.voice_capabilities import ModeSpec as VoiceMode
from studio.l3_interface_adapters.gateways.model_registration.factory_context import create_context
from studio.l3_interface_adapters.gateways.model_registration.installed_model_catalog import (
    GROUPS,
    InstalledModelCatalog,
)
from studio.l3_interface_adapters.gateways.model_registration.model_backend_factory import ModelBackendFactory
from studio.l3_interface_adapters.gateways.no_prompt_rewriter_gateway import NoPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.image_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.stub.prompt_rewriter_gateway import StubPromptRewriterGateway
from studio.l3_interface_adapters.gateways.stub.video_backend_gateway import StubVideoBackendGateway
from studio.l3_interface_adapters.gateways.stub.voice_backend_gateway import StubVoiceBackendGateway
from studio.l4_frameworks_and_drivers.config import Config, ConfigError
from studio.l4_frameworks_and_drivers.python_entry_points import entry_points
from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
from studio.plugins import API_VERSION, ModelPlugin
from tests.support.fakes import fake_capabilities, fake_video_capabilities
from tests.support.plugins import CHECKPOINT, PACK, checkpoint_entries, entry, install, pack_entries


def configuration():
    return Config(
        "example_image",
        ("example_image",),
        "example_video",
        ("example_video",),
        {"example_image": {"key": "value"}},
        "example_voice",
        ("example_voice",),
    )


def declarations():
    image = fake_capabilities("example_image")
    video = fake_video_capabilities("example_video")
    voice = VoiceCapabilities("example_voice", "Voice", "", (VoiceMode("design", "Generate", ()),), 16)
    return {
        "image": ModelPlugin(image, lambda context: StubBackendGateway(image)),
        "video": ModelPlugin(video, lambda context: StubVideoBackendGateway(video)),
        "voice": ModelPlugin(voice, lambda context: StubVoiceBackendGateway(capabilities=voice)),
    }


def installed(monkeypatch, plugins=None, entries=None):
    plugins = declarations() if plugins is None else plugins
    entries = (
        entries
        if entries is not None
        else [
            SimpleNamespace(name=plugin.capabilities.backend_id, group=GROUPS[kind], load=Mock(return_value=plugin))
            for kind, plugin in plugins.items()
        ]
    )
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.python_entry_points.metadata.entry_points",
        lambda group: [entry for entry in entries if entry.group == group],
    )
    return InstalledModelCatalog({}, entry_points), entries


def test_discovery_does_not_import_models_and_selected_declarations_are_cached(monkeypatch):
    registry, entries = installed(monkeypatch)
    assert registry.ids("image") == ("example_image",)
    assert all(not entry.load.called for entry in entries)
    assert registry.declaration("image", "example_image") is registry.declaration("image", "example_image")
    entries[0].load.assert_called_once()
    assert not entries[1].load.called


@pytest.mark.parametrize("name", ["Upper", "with-dash", "1model", "bad/path"])
def test_ids_are_safe_and_consistent_with_existing_backend_configuration(monkeypatch, name):
    with pytest.raises(ConfigError, match="Plugin id"):
        installed(monkeypatch, entries=[SimpleNamespace(name=name, group=GROUPS["image"])])


def test_duplicate_ids_cannot_shadow_builtins_or_other_media(monkeypatch):
    entries = [SimpleNamespace(name="same", group=GROUPS[kind]) for kind in ("image", "video")]
    with pytest.raises(ConfigError, match="Duplicate model id"):
        installed(monkeypatch, entries=entries)
    installed(monkeypatch, entries=entries[:1])
    with pytest.raises(ConfigError, match="Duplicate model id"):
        InstalledModelCatalog({"image": {"same": object()}}, entry_points)


@pytest.mark.parametrize(
    "bad",
    [
        object(),
        replace(declarations()["image"], api_version=2),
        replace(declarations()["image"], capabilities=fake_capabilities("different")),
        replace(declarations()["image"], capabilities=declarations()["voice"].capabilities),
        replace(declarations()["image"], create=None),
        replace(declarations()["image"], rewriter=3),
    ],
)
def test_selected_invalid_declarations_have_actionable_errors(monkeypatch, bad):
    registry, _ = installed(
        monkeypatch, entries=[SimpleNamespace(name="example_image", group=GROUPS["image"], load=lambda: bad)]
    )
    with pytest.raises(ConfigError, match=r"Cannot load model plugin open_imagine.models.image/example_image"):
        registry.declaration("image", "example_image")


def test_import_failure_names_the_plugin(monkeypatch):
    entry = SimpleNamespace(name="broken", group=GROUPS["image"], load=Mock(side_effect=ImportError("missing extra")))
    registry, _ = installed(monkeypatch, entries=[entry])
    with pytest.raises(ConfigError, match="missing extra"):
        registry.declaration("image", "broken")


@pytest.mark.parametrize("kind", ["image", "video", "voice"])
@pytest.mark.parametrize("stub", [False, True])
def test_each_media_uses_its_boundary_and_stub_never_constructs_the_engine(monkeypatch, kind, stub):
    plugins = declarations()
    original = plugins[kind]
    factory = Mock(side_effect=original.create)
    plugins[kind] = replace(original, create=factory)
    registry, _ = installed(monkeypatch, plugins)
    gateway = ModelBackendFactory(registry, SubprocessRunner().execute).build(
        kind, original.capabilities.backend_id, configuration(), stub
    )
    assert gateway.capabilities() == original.capabilities
    assert factory.call_count == (0 if stub else 1)


def test_context_has_resolved_settings_and_cancellable_host_process_driver(monkeypatch):
    context = create_context(configuration(), "example_image", SubprocessRunner().execute)
    assert context.settings == {"key": "value"} and callable(context.run_process)
    assert context.capabilities is None and context.lora_paths == {}
    with pytest.raises(TypeError):
        cast(dict, context.settings)["key"] = "changed"


def lora_tables(**settings):
    """The example video model's section with two LoRA tables, as studio.toml resolves them."""
    tables = [
        {"id": "motion", "label": "Motion", "path": "/private/motion.safetensors", "trigger": "in motion"},
        {"id": "detail", "label": "Detail", "path": "/private/detail.safetensors", "strength": 0.5},
    ]
    return replace(configuration(), sections={"example_video": {"loras": tables, **settings}})


def taking_loras(factory=None):
    """A video declaration that takes the LoRA tables, and the contexts its factory saw."""
    seen = []

    def create(context):
        seen.append(context)
        return StubVideoBackendGateway(context.capabilities)

    video = replace(declarations()["video"], create=factory or create, loras=True)
    return {"video": video}, seen


@pytest.mark.parametrize("stub", [False, True])
def test_a_plugin_that_takes_loras_offers_its_tables_by_id(monkeypatch, stub):
    plugins, seen = taking_loras()
    registry, _ = installed(monkeypatch, plugins)

    gateway = ModelBackendFactory(registry, SubprocessRunner().execute).build(
        "video", "example_video", lora_tables(max_loras=2), stub
    )

    offered = gateway.capabilities()
    assert [lora.id for lora in offered.loras] == ["motion", "detail"] and offered.max_loras == 2
    assert offered.loras[0].trigger == "in motion" and offered.loras[1].strength == 0.5
    assert replace(offered, loras=(), max_loras=0) == plugins["video"].capabilities
    assert "/private/" not in repr(offered)
    if stub:
        assert seen == []
    else:
        (context,) = seen
        assert context.capabilities == offered
        assert context.lora_paths == {"motion": "/private/motion.safetensors", "detail": "/private/detail.safetensors"}
        with pytest.raises(TypeError):
            context.lora_paths["motion"] = "/elsewhere"


def test_a_plugin_that_takes_loras_keeps_its_record_without_tables(monkeypatch):
    plugins, seen = taking_loras()
    registry, _ = installed(monkeypatch, plugins)

    gateway = ModelBackendFactory(registry, SubprocessRunner().execute).build("video", "example_video", configuration())

    assert gateway.capabilities() == plugins["video"].capabilities == seen[0].capabilities
    assert seen[0].lora_paths == {}


def test_a_plugin_that_takes_loras_must_report_the_offered_record(monkeypatch):
    video = declarations()["video"]
    plugins, _ = taking_loras(lambda context: StubVideoBackendGateway(video.capabilities))
    registry, _ = installed(monkeypatch, plugins)

    with pytest.raises(ConfigError, match="Cannot construct video model plugin"):
        ModelBackendFactory(registry, SubprocessRunner().execute).build("video", "example_video", lora_tables())


@pytest.mark.parametrize(
    "table,reason",
    [
        ({"id": "motion", "label": "Motion"}, "needs path"),
        # The rules of a video model: one LoRA set applies to every mode.
        ({"id": "motion", "label": "Motion", "path": "/m.safetensors", "modes": ["generate"]}, "remove modes"),
    ],
)
def test_a_table_for_a_plugin_that_takes_loras_follows_the_built_in_video_rules(monkeypatch, table, reason):
    plugins, _ = taking_loras()
    registry, _ = installed(monkeypatch, plugins)
    config = replace(configuration(), sections={"example_video": {"loras": [table]}})

    with pytest.raises(ConfigError, match=reason):
        ModelBackendFactory(registry, SubprocessRunner().execute).build("video", "example_video", config)


def test_a_plugin_that_takes_no_loras_leaves_its_tables_to_itself(monkeypatch):
    seen = []
    video = declarations()["video"]
    plugins = {"video": replace(video, create=lambda context: seen.append(context) or video.create(context))}
    registry, _ = installed(monkeypatch, plugins)

    gateway = ModelBackendFactory(registry, SubprocessRunner().execute).build("video", "example_video", lora_tables())

    assert gateway.capabilities() == video.capabilities
    assert seen[0].capabilities is None and seen[0].lora_paths == {}
    assert seen[0].settings["loras"][0]["path"] == "/private/motion.safetensors"


@pytest.mark.parametrize(
    "kind,changes,reason",
    [
        ("video", {"loras": "yes"}, "loras must be True or False"),
        ("image", {"loras": True}, "only a video model takes LoRA tables"),
        ("voice", {"loras": True}, "only a video model takes LoRA tables"),
        (
            "video",
            {
                "loras": True,
                "capabilities": replace(
                    fake_video_capabilities("example_video"), loras=(Lora("own", "Own"),), max_loras=1
                ),
            },
            "declares no LoRAs of its own",
        ),
    ],
)
def test_a_declaration_that_takes_loras_is_checked(monkeypatch, kind, changes, reason):
    bad = replace(declarations()[kind], **changes)
    name = bad.capabilities.backend_id
    registry, _ = installed(monkeypatch, entries=[SimpleNamespace(name=name, group=GROUPS[kind], load=lambda: bad)])

    with pytest.raises(ConfigError, match=reason):
        registry.declaration(kind, name)


def test_a_record_that_gives_its_api_version_by_position_keeps_its_meaning(monkeypatch):
    video = declarations()["video"]
    positional = ModelPlugin(video.capabilities, video.create, None, API_VERSION)
    name = video.capabilities.backend_id
    registry, _ = installed(
        monkeypatch, entries=[SimpleNamespace(name=name, group=GROUPS["video"], load=lambda: positional)]
    )

    assert registry.declaration("video", name) is positional and positional.loras is False


@pytest.mark.parametrize(
    "factory",
    [
        lambda context: object(),
        lambda context: StubBackendGateway(fake_capabilities("wrong")),
        Mock(side_effect=RuntimeError("failed factory")),
    ],
)
def test_factory_errors_and_capability_mismatches_are_rejected(monkeypatch, factory):
    registry, _ = installed(monkeypatch, {"image": replace(declarations()["image"], create=factory)})
    with pytest.raises(ConfigError, match="Cannot construct image model plugin"):
        ModelBackendFactory(registry, SubprocessRunner().execute).build("image", "example_image", configuration())


def test_rewriters_are_optional_typed_lazy_and_stubbed(monkeypatch):
    registry, _ = installed(monkeypatch)
    assert isinstance(
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("image", "example_image", configuration()),
        NoPromptRewriterGateway,
    )
    factory = Mock(return_value=NoPromptRewriterGateway())
    registry, _ = installed(monkeypatch, {"image": replace(declarations()["image"], rewriter=factory)})
    assert isinstance(
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter(
            "image", "example_image", configuration(), True
        ),
        StubPromptRewriterGateway,
    )
    factory.assert_not_called()
    assert isinstance(
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("image", "example_image", configuration()),
        NoPromptRewriterGateway,
    )
    factory.return_value = object()
    with pytest.raises(ConfigError, match="rewriter must return"):
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("image", "example_image", configuration())
    factory.side_effect = RuntimeError("rewrite failed")
    with pytest.raises(ConfigError, match="rewrite failed"):
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("image", "example_image", configuration())


def test_public_media_sdk_imports_the_host_contracts():
    from studio.plugins import audio, image, video

    assert (
        image.ImageBackendGateway
        is __import__(
            "studio.l2_use_cases.boundaries.image_backend_gateway", fromlist=["ImageBackendGateway"]
        ).ImageBackendGateway
    )
    assert (
        video.VideoBackendGateway
        is __import__(
            "studio.l2_use_cases.boundaries.video_backend_gateway", fromlist=["VideoBackendGateway"]
        ).VideoBackendGateway
    )
    assert audio.Capabilities is VoiceCapabilities


def test_composition_builds_all_three_external_models_without_platform_or_engine_loading(monkeypatch, tmp_path):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    monkeypatch.setattr(
        main, "require_mlx", Mock(side_effect=AssertionError("plugin-only composition must not impose MLX"))
    )
    studio = main.create_studio(configuration(), plugins=registry, private_results_dir=tmp_path / "private")
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert studio.active_capabilities().backend_id == "example_image"
        assert studio.video_catalog.active_id() == "example_video"
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_stub_composition_preserves_plugin_capabilities_and_rewrite_absence(monkeypatch):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    studio = main.create_studio(configuration(), stub=True, plugins=registry)
    try:
        assert studio.video_catalog is not None and studio.video_rewriter is not None
        assert studio.active_capabilities().backend_id == "example_image"
        assert studio.rewriter is not None and studio.video_rewriter is not None
        assert studio.rewriter.modes() == ()
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_image_plugin_rewriter_follows_the_selected_backend(monkeypatch):
    from studio.l4_frameworks_and_drivers.main import build_rewriters

    registry, _ = installed(
        monkeypatch, {"image": replace(declarations()["image"], rewriter=lambda context: StubPromptRewriterGateway())}
    )
    assert build_rewriters(configuration(), registry)["example_image"].modes() == ("generate", "edit")


def test_video_rewrite_switches_between_plugin_and_builtin_without_cross_model_enhancement(monkeypatch):
    from studio.l4_frameworks_and_drivers import main

    registry, _ = installed(monkeypatch)
    config = replace(configuration(), visible_video_backends=("example_video", "ltx25_mlx"))
    studio = main.create_studio(config, stub=True, plugins=registry)
    try:
        assert studio.video_rewriter is not None and studio.video_catalog is not None
        assert studio.video_rewriter.modes() == ()
        studio.video_catalog.set_active("ltx25_mlx")
        assert studio.video_rewriter.modes() == ("generate", "edit")
        studio.video_catalog.set_active("example_video")
        assert studio.video_rewriter.modes() == ()
    finally:
        studio.shutdown()


def test_video_plugin_rewrite_and_release_share_the_model_thread(monkeypatch, tmp_path):
    import threading

    from studio.l4_frameworks_and_drivers import main

    calls = []

    class Rewriter(StubPromptRewriterGateway):
        def rewrite(self, prompt, mode, references, on_writing, should_stop):
            calls.append(threading.get_ident())
            return super().rewrite(prompt, mode, references, on_writing, should_stop)

        def release(self):
            calls.append(threading.get_ident())

    registry, _ = installed(
        monkeypatch, {**declarations(), "video": replace(declarations()["video"], rewriter=lambda context: Rewriter())}
    )
    studio = main.create_studio(configuration(), plugins=registry, private_results_dir=tmp_path / "private")
    assert studio.video_rewriter is not None
    studio.video_rewriter.rewrite("A landscape", "generate", (), lambda: None, lambda: False)
    studio.shutdown()
    assert len(calls) == 2
    assert calls[0] == calls[1] != threading.get_ident()


def test_example_video_reports_encoder_failure_instead_of_callback_type_error(monkeypatch, tmp_path):
    from pathlib import Path

    from studio.l1_entities.errors import StudioError
    from studio.l4_frameworks_and_drivers.subprocess_runner import SubprocessRunner
    from studio.plugins import PluginContext
    from studio.plugins.video import VideoJob

    monkeypatch.syspath_prepend(str(Path(__file__).parents[4] / "examples/model_plugin"))
    from importlib import import_module

    video = import_module("open_imagine_example.video")

    encoder = tmp_path / "ffmpeg"
    encoder.write_text("#!/bin/sh\necho 'fixture encoder error' >&2\nexit 7\n")
    encoder.chmod(0o755)
    monkeypatch.setattr(video.shutil, "which", lambda name: str(encoder))
    gateway = video.ExampleVideoGateway(PluginContext({}, SubprocessRunner().execute))
    with pytest.raises(StudioError, match=r"Example Video failed \(7\): fixture encoder error"):
        gateway.run(VideoJob("test", 256, 256, 17, 8, 7))


def test_an_ltx_pack_is_a_video_declaration_that_the_host_builds(monkeypatch):
    registry = install(monkeypatch, pack_entries())

    assert registry.declaration("video", "example_pack") is PACK
    with pytest.raises(ConfigError, match="own engine, so the host builds it"):
        ModelBackendFactory(registry, SubprocessRunner().execute).build("video", "example_pack", configuration())
    with pytest.raises(ConfigError, match="own engine, so the host builds it"):
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("video", "example_pack", configuration())


@pytest.mark.parametrize(
    ("pack", "group", "message"),
    [
        (PACK, "image", "an LtxCheckpointRegistration is a video model"),
        (replace(PACK, api_version=2), "video", "expected LtxCheckpointRegistration API version 1"),
        (
            replace(PACK, backend_id="other"),
            "video",
            "expected an LtxCheckpointRegistration with backend_id 'example_pack'",
        ),
        (replace(PACK, family=["ltx25"]), "video", "an LtxCheckpointRegistration's family must be text"),
        (replace(PACK, description=None), "video", "an LtxCheckpointRegistration's description must be text"),
        (replace(PACK, edit="no"), "video", "an LtxCheckpointRegistration's edit must be True or False"),
        (replace(PACK, fast_mode=1), "video", "an LtxCheckpointRegistration's fast_mode must be True or False"),
    ],
)
def test_a_pack_record_that_the_host_cannot_trust_is_refused_by_name(monkeypatch, pack, group, message):
    registry = install(monkeypatch, [entry(group, "example_pack", pack)])
    with pytest.raises(ConfigError, match=rf"open_imagine.models.{group}/example_pack: {message}"):
        registry.declaration(group, "example_pack")


def test_a_qwen_checkpoint_is_an_image_declaration_that_the_host_builds(monkeypatch):
    registry = install(monkeypatch, checkpoint_entries())

    assert registry.declaration("image", "example_qwen") is CHECKPOINT
    with pytest.raises(ConfigError, match="own engine, so the host builds it"):
        ModelBackendFactory(registry, SubprocessRunner().execute).build("image", "example_qwen", configuration())
    with pytest.raises(ConfigError, match="own engine, so the host builds it"):
        ModelBackendFactory(registry, SubprocessRunner().execute).rewriter("image", "example_qwen", configuration())


@pytest.mark.parametrize(
    ("checkpoint", "group", "message"),
    [
        (CHECKPOINT, "video", "a QwenCheckpointRegistration is an image model"),
        (replace(CHECKPOINT, api_version=2), "image", "expected QwenCheckpointRegistration API version 1"),
        (
            replace(CHECKPOINT, backend_id="other"),
            "image",
            "expected a QwenCheckpointRegistration with backend_id 'example_qwen'",
        ),
        (replace(CHECKPOINT, name=None), "image", "a QwenCheckpointRegistration's name must be text"),
        (replace(CHECKPOINT, scheduler=1), "image", "a QwenCheckpointRegistration's scheduler must be text"),
        (
            replace(CHECKPOINT, generate_size=(1024, 1024)),
            "image",
            "a QwenCheckpointRegistration's generate_size must be text",
        ),
        (
            replace(CHECKPOINT, steps=[12, 8, 40]),
            "image",
            "a QwenCheckpointRegistration.s steps must be three whole numbers",
        ),
        (
            replace(CHECKPOINT, steps=(12, 8)),
            "image",
            "a QwenCheckpointRegistration.s steps must be three whole numbers",
        ),
        (
            replace(CHECKPOINT, steps=(12.0, 8, 40)),
            "image",
            "a QwenCheckpointRegistration.s steps must be three whole numbers",
        ),
        (
            replace(CHECKPOINT, steps=(12, True, 40)),
            "image",
            "a QwenCheckpointRegistration.s steps must be three whole numbers",
        ),
        (
            replace(CHECKPOINT, max_edit_references=True),
            "image",
            "a QwenCheckpointRegistration.s max_edit_references must be a whole number",
        ),
    ],
)
def test_a_checkpoint_record_that_the_host_cannot_trust_is_refused_by_name(monkeypatch, checkpoint, group, message):
    registry = install(monkeypatch, [entry(group, "example_qwen", checkpoint)])
    with pytest.raises(ConfigError, match=rf"open_imagine.models.{group}/example_qwen: {message}"):
        registry.declaration(group, "example_qwen")
