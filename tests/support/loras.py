"""A LoRA table with real files on disk, for the engines that load them."""

from studio.l1_entities.lora import Lora
from studio.l3_interface_adapters.gateways.lora_files import LoraFile, LoraFiles


def lora_table(folder, *ids: str, max_loras: int = 2, trigger: str = "", modes=()) -> LoraFiles:
    files = []
    for lora_id in ids or ("example_warm",):
        path = folder / f"{lora_id}.safetensors"
        path.write_bytes(b"weights")
        files.append(LoraFile(Lora(lora_id, lora_id.replace("_", " "), trigger=trigger), str(path), tuple(modes)))
    return LoraFiles(tuple(files), max_loras)
