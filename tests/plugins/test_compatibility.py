"""Canonical model-SDK terminology keeps API-v1 imports valid."""

from studio import plugins
from studio.plugins import audio, image, video, voice
from studio.plugins.ltx_checkpoint_registration import LtxCheckpointRegistration
from studio.plugins.qwen_checkpoint_registration import QwenCheckpointRegistration


def test_api_v1_records_are_identity_aliases_not_parallel_contracts():
    assert plugins.ModelPlugin is plugins.GatewayModelRegistration
    assert plugins.PluginContext is plugins.ModelFactoryContext
    assert plugins.API_VERSION == plugins.MODEL_PLUGIN_API_VERSION == 1
    assert image.QwenCheckpoint is QwenCheckpointRegistration
    assert video.LtxPack is LtxCheckpointRegistration
    assert audio.Capabilities is voice.VoiceCapabilities
    assert audio.SpeechJob is voice.SpeechJob
    assert image.ImageCapabilities is image.Capabilities
