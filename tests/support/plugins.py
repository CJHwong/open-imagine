"""Installed model plugins for a test, with no package on disk."""

from types import SimpleNamespace
from unittest.mock import Mock

from studio.l1_entities.voice_capabilities import Capabilities as VoiceCapabilities
from studio.l1_entities.voice_capabilities import ModeSpec as VoiceMode
from studio.l3_interface_adapters.gateways.audio.stub_voice_backend_gateway import StubVoiceBackendGateway
from studio.l3_interface_adapters.gateways.image.stub_backend_gateway import StubBackendGateway
from studio.l3_interface_adapters.gateways.video.stub_video_backend_gateway import StubVideoBackendGateway
from studio.l4_frameworks_and_drivers.model_plugins import GROUPS, ModelPlugins
from studio.plugins import ModelPlugin
from studio.plugins.image import QwenCheckpoint
from studio.plugins.video import LtxPack
from tests.support.fakes import fake_capabilities, fake_video_capabilities

PACK = LtxPack("example_pack", "Example pack", "ltx25")
CHECKPOINT = QwenCheckpoint("example_qwen", "Example Qwen checkpoint")


def fake_plugins() -> dict:
    """One plugin for each media, each with a stub engine."""
    image = fake_capabilities("example_image")
    video = fake_video_capabilities("example_video")
    voice = VoiceCapabilities("example_voice", "Voice", "", (VoiceMode("design", "Generate", ()),), 16)
    return {
        "image": ModelPlugin(image, lambda context: StubBackendGateway(image)),
        "video": ModelPlugin(video, lambda context: StubVideoBackendGateway(video)),
        "voice": ModelPlugin(voice, lambda context: StubVoiceBackendGateway(capabilities=voice)),
    }


def entry(kind: str, name: str, record) -> SimpleNamespace:
    return SimpleNamespace(name=name, group=GROUPS[kind], load=Mock(return_value=record))


def install(monkeypatch, entries: list) -> ModelPlugins:
    monkeypatch.setattr(
        "studio.l4_frameworks_and_drivers.model_plugins.metadata.entry_points",
        lambda group: [item for item in entries if item.group == group],
    )
    return ModelPlugins({})


def pack_entries(*packs: LtxPack) -> list:
    """The image and voice examples, and LTX packs in place of the video example."""
    plugins = fake_plugins()
    return [
        entry("image", "example_image", plugins["image"]),
        entry("voice", "example_voice", plugins["voice"]),
        *(entry("video", pack.backend_id, pack) for pack in packs or (PACK,)),
    ]


def checkpoint_entries(*checkpoints: QwenCheckpoint) -> list:
    """The video and voice examples, and Qwen checkpoints in place of the image example."""
    plugins = fake_plugins()
    return [
        entry("video", "example_video", plugins["video"]),
        entry("voice", "example_voice", plugins["voice"]),
        *(entry("image", checkpoint.backend_id, checkpoint) for checkpoint in checkpoints or (CHECKPOINT,)),
    ]
