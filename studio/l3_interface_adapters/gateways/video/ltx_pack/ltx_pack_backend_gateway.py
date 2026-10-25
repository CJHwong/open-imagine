"""The video backend for an LTX pack that a plugin names, on the studio's own engine."""

import sys
from collections.abc import Callable
from contextlib import contextmanager
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l1_entities.video_capabilities import VideoCapabilities
from studio.l1_entities.video_job import VideoJob, VideoResult
from studio.l2_use_cases.boundaries.video_backend_gateway import VideoBackendGateway
from studio.l3_interface_adapters.gateways.hidden_paths import hidden
from studio.l3_interface_adapters.gateways.lora_files import LoraFiles


class LtxPackBackendGateway(VideoBackendGateway):
    """A pack in a folder that the plugin's settings name, run by the base packs' runner.

    The folder is checked before each run, and never at start: the stub builds every model,
    also on a machine that does not hold the weights. A missing folder is refused by the
    model's id, so the person learns which setting to fix. The engine would take the path
    for a Hugging Face repo id and stop with an error about the id.

    The folder's name can be private, so an error that quotes it names the pack by its id.
    """

    def __init__(self, runner, capabilities: VideoCapabilities, pack_dir: str, loras: LoraFiles | None = None):
        self._capabilities = (loras or LoraFiles()).offer_video(capabilities)
        self._runner = runner
        self._pack_dir = pack_dir

    def capabilities(self) -> VideoCapabilities:
        return self._capabilities

    def run(
        self,
        job: VideoJob,
        progress: Callable[[int, int, int], None] | None = None,
        cancelled: Callable[[], bool] | None = None,
    ) -> VideoResult:
        with self._pack():
            return self._runner.run(job, progress, cancelled)

    def run_batch(self, jobs, completed, started, progress, cancelled) -> list[VideoResult]:
        with self._pack():
            return self._runner.run_batch(jobs, completed, started, progress, cancelled)

    def release(self) -> None:
        # The pipeline process owns the weights and exits after each clip.
        pass

    @contextmanager
    def _pack(self):
        backend_id = self._capabilities.backend_id
        if not self._pack_dir:
            raise StudioError(f"Set pack_dir under [{backend_id}] to the folder of the pack.")
        if not Path(self._pack_dir).is_dir():
            print(f"[{backend_id}] no pack folder at {self._pack_dir}", file=sys.stderr, flush=True)
            raise StudioError(f"The weights of the {backend_id} pack are not on disk. The server log names the path.")
        with hidden(((self._pack_dir, f"the {backend_id} pack"),)):
            yield
