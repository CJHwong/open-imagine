"""Preview cleanup while retaining assets used by unselected models."""

from studio.l1_entities.errors import InvalidJob
from studio.l2_use_cases.boundaries.model_storage_gateway import ModelStorageGateway


class InspectModelStorageUseCase:
    def __init__(self, storage: ModelStorageGateway):
        self._storage = storage

    def execute(self, models=None, include_runtime=False):
        inventory = self._storage.inventory()
        if models is None:
            return inventory
        known = {model["id"] for model in inventory["models"]}
        if not isinstance(models, list) or not models or not all(isinstance(model, str) for model in models):
            raise InvalidJob("Choose at least one model to clean up.")
        if len(set(models)) != len(models) or set(models) - known or not isinstance(include_runtime, bool):
            raise InvalidJob("Choose known models and a valid runtime option.")
        selected = set(models)
        removed, retained = [], []
        for asset in inventory["assets"]:
            if not selected.intersection(asset["models"]):
                continue
            reason = asset["blocked"]
            if not reason and set(asset["models"]) - selected:
                reason = "shared"
            if not reason and asset["kind"] == "runtime" and not include_runtime:
                reason = "runtime"
            (retained if reason else removed).append({**asset, "reason": reason})
        return {
            "revision": inventory["revision"],
            "remove": removed,
            "retain": retained,
            "bytes": sum(asset["bytes"] for asset in removed),
        }
