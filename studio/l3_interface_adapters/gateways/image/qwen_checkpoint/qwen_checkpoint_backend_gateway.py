"""The image backend for a Qwen checkpoint that a plugin names, on the studio's own engine."""

import sys
from contextlib import contextmanager
from pathlib import Path

from studio.l1_entities.capabilities import Capabilities
from studio.l1_entities.errors import StudioError
from studio.l1_entities.image_job import ImageJob
from studio.l2_use_cases.boundaries.image_backend_gateway import ImageBackendGateway
from studio.l3_interface_adapters.gateways.hidden_paths import hidden
from studio.l3_interface_adapters.gateways.image.shared.qwen_schedules import (
    LINEAR,
    edit_schedule,
    register_schedules,
)
from studio.l3_interface_adapters.gateways.lora_files import LoraFiles

# What mflux reads from a folder. A converted finetune often links the processor, the text
# encoder and the VAE to the base snapshot, so a link counts. mflux's sharded text loader
# needs the index. The official Turbo backend writes one for its single-file encoder, but
# this backend does not write into a folder that the person owns.
REQUIRED_FILES = ("processor/tokenizer.json", "text_encoder/model.safetensors.index.json")
WEIGHT_DIRECTORIES = ("transformer", "vae", "text_encoder")
# The edit loader also reads each part's config and the image processor's. A text-to-image
# export does not write them, so a folder can generate and still fail to edit.
EDIT_FILES = (
    "processor/preprocessor_config.json",
    "transformer/config.json",
    "vae/config.json",
    "text_encoder/config.json",
)


class QwenCheckpointBackendGateway(ImageBackendGateway):
    """A checkpoint in a folder that the plugin's settings name, run by the two models that
    qwen21 drives. The composition root builds them and hands them in, as for Viggle.

    The folder is checked before each load and run, and never at start: the stub builds every
    model, also on a machine that does not hold the weights. A missing folder is refused by the
    model's id. Without the check, mflux would read a blank path as no folder and load the base
    model, which gives an image with no error. The folder's name can be private, so an error
    that quotes it names the checkpoint by its id.

    The generate half samples the record's schedule through an argument. The edit half cannot
    be told, so its call runs inside `edit_schedule`.
    """

    def __init__(
        self,
        generator,
        edit,
        capabilities: Capabilities,
        model_dir: str,
        edit_scheduler: str = LINEAR,
        loras: LoraFiles | None = None,
    ):
        self._generator = generator
        self._edit = edit
        self._capabilities = capabilities
        self._model_dir = model_dir
        self._edit_scheduler = edit_scheduler
        self._loras = loras or LoraFiles()

    def capabilities(self) -> Capabilities:
        # Here and not in the constructor, so a table that names a mode the record lacks
        # fails at start with the section to look in, as for the built-in models.
        return self._loras.offer_image(self._capabilities)

    def load(self) -> None:
        with self._checkpoint("generate"):
            self._generator.load()

    def prepare_batch(self, jobs, should_stop) -> None:
        if not jobs or any(job.mode != "generate" for job in jobs):
            return
        with self._checkpoint("generate"):
            register_schedules()
            self._edit.release()
            self._generator.prepare_batch(jobs, should_stop)

    def run(self, job: ImageJob, on_step, should_stop):
        with self._checkpoint(job.mode):
            # The names have to be known before mflux builds its Config, which is here.
            register_schedules()
            if job.mode == "edit":
                self._generator.release()
                with edit_schedule(self._edit_scheduler):
                    return self._edit.run(job, on_step, should_stop)
            self._edit.release()
            return self._generator.run(job, on_step, should_stop)

    def release(self) -> None:
        self._generator.release()
        self._edit.release()

    @contextmanager
    def _checkpoint(self, mode: str):
        backend_id = self._capabilities.backend_id
        if not self._model_dir:
            raise StudioError(f"Set model_dir under [{backend_id}] to the folder of the checkpoint.")
        # The check is inside, because a folder that cannot be read raises with its path.
        with hidden(((self._model_dir, f"the {backend_id} checkpoint"),)):
            missing = missing_files(Path(self._model_dir), mode)
            if missing:
                print(f"[{backend_id}] incomplete checkpoint at {self._model_dir}", file=sys.stderr, flush=True)
                raise StudioError(
                    f"The weights of the {backend_id} checkpoint are not complete: {', '.join(missing)}. "
                    "The server log names the folder."
                )
            yield


def missing_files(model_dir: Path, mode: str) -> list[str]:
    if not model_dir.is_dir():
        return ["the folder"]
    required = REQUIRED_FILES + EDIT_FILES if mode == "edit" else REQUIRED_FILES
    missing = [relative for relative in required if not (model_dir / relative).is_file()]
    missing.extend(
        f"{directory}/*.safetensors"
        for directory in WEIGHT_DIRECTORIES
        if not any((model_dir / directory).glob("*.safetensors"))
    )
    return missing
