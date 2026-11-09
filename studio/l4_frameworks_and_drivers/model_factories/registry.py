"""Explicit built-in backend and rewriter registrations."""

from studio.l3_interface_adapters.gateways.image.qwen_runtime.rewriter import Qwen21Rewriter
from studio.l4_frameworks_and_drivers.model_factories.image.flux2 import flux2_backend
from studio.l4_frameworks_and_drivers.model_factories.image.flux3 import flux3_backend
from studio.l4_frameworks_and_drivers.model_factories.image.krea2 import krea2_backend
from studio.l4_frameworks_and_drivers.model_factories.image.qwen21 import qwen21_backend
from studio.l4_frameworks_and_drivers.model_factories.image.qwen21_turbo import qwen21_turbo_backend
from studio.l4_frameworks_and_drivers.model_factories.image.viggle_turbo import viggle_turbo_backend
from studio.l4_frameworks_and_drivers.model_factories.music.yue2 import music_yue2_backend
from studio.l4_frameworks_and_drivers.model_factories.video.ltx23 import ltx23_mlx_backend
from studio.l4_frameworks_and_drivers.model_factories.video.ltx25 import ltx25_mlx_backend
from studio.l4_frameworks_and_drivers.model_factories.voice.auk import voice_auk_backend
from studio.l4_frameworks_and_drivers.model_factories.voice.auk_flash import voice_auk_flash_backend
from studio.l4_frameworks_and_drivers.model_factories.voice.drama3 import voice_drama_backend

IMAGE_BACKEND_FACTORIES = {
    "qwen21": qwen21_backend,
    "qwen21_turbo": qwen21_turbo_backend,
    "flux2": flux2_backend,
    "flux3": flux3_backend,
    "krea2": krea2_backend,
    "viggle_turbo": viggle_turbo_backend,
}

VIDEO_BACKEND_FACTORIES = {
    "ltx25_mlx": ltx25_mlx_backend,
    "ltx23_mlx": ltx23_mlx_backend,
}

VOICE_BACKEND_FACTORIES = {
    "auk": voice_auk_flash_backend,
    "auk_base": voice_auk_backend,
    "drama3": voice_drama_backend,
}

MUSIC_BACKEND_FACTORIES = {"yue2": music_yue2_backend}

IMAGE_REWRITER_FACTORIES = {"qwen21": Qwen21Rewriter, "qwen21_turbo": Qwen21Rewriter, "viggle_turbo": Qwen21Rewriter}
