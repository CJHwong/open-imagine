"""Persist app preferences atomically; never store operation data here."""

import json
import threading
from pathlib import Path

from studio.l1_entities.errors import StudioError
from studio.l2_use_cases.boundaries.studio_settings_gateway import StudioSettingsGateway


class JsonStudioSettingsGateway(StudioSettingsGateway):
    def __init__(self, path: Path, require_memory_estimate: bool = False):
        self._path = path
        self._lock = threading.Lock()
        self._required = require_memory_estimate
        try:
            raw = json.loads(path.read_text())
        except FileNotFoundError:
            return
        except (OSError, ValueError) as error:
            raise StudioError("Cannot read Studio settings. Check the settings_path file.") from error
        if not isinstance(raw, dict) or not isinstance(raw.get("require_memory_estimate"), bool):
            raise StudioError("Studio settings require a boolean require_memory_estimate.")
        self._required = raw["require_memory_estimate"]

    def require_memory_estimate(self) -> bool:
        with self._lock:
            return self._required

    def set_require_memory_estimate(self, required: bool) -> None:
        with self._lock:
            temporary = self._path.with_suffix(self._path.suffix + ".tmp")
            try:
                self._path.parent.mkdir(parents=True, exist_ok=True)
                temporary.write_text(json.dumps({"require_memory_estimate": required}) + "\n")
                temporary.replace(self._path)
            except OSError as error:
                raise StudioError("Cannot save Studio settings. Check that settings_path is writable.") from error
            finally:
                temporary.unlink(missing_ok=True)
            self._required = required
