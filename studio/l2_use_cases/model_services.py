"""Injected host services and instance-scoped shared runtime resources."""

from dataclasses import dataclass, field
from typing import Any

from studio.l2_use_cases.boundaries.process_gateway import ProcessGateway


@dataclass
class ModelServices:
    run_process: ProcessGateway
    shared: dict[str, Any] = field(default_factory=dict)
