"""Which engines this host can run, and the refusal when it lacks one it was asked for.

A backend names its engine. This module answers what the host has, so the choice is
made once, at composition, and no adapter branches on the platform. The two engines
are MLX (mflux, mlx-vlm, the LTX MLX port) and CUDA (an NVIDIA driver with a CUDA
child environment). See `gateways/image/qwen21/PORTABILITY.md` for the measured
differences between the machines.
"""

import shutil
import subprocess

MLX = "mlx"
CUDA = "cuda"

_ENGINES = {
    MLX: "MLX",
    CUDA: "CUDA",
}


class EngineUnavailable(Exception):
    """No engine for this machine. The message names the remedy."""


def mlx_available() -> bool:
    """Whether MLX can use a GPU on this machine.

    The generic device check covers Metal and CUDA builds.
    """
    try:
        import mlx.core as mx
    except ImportError:
        return False
    gpu = mx.Device(mx.DeviceType.gpu)
    return mx.is_available(gpu)


def cuda_available() -> bool:
    """Whether this host has an NVIDIA driver.

    The server does not import torch. A CUDA engine runs in its own child
    environment, so the driver is the whole of what this process can check, and the
    child reports a broken torch when it starts.
    """
    if shutil.which("nvidia-smi") is None:
        return False
    try:
        result = subprocess.run(["nvidia-smi", "-L"], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0 and "GPU" in result.stdout


def available_engines() -> frozenset[str]:
    """The engines this host can run right now."""
    available = set()
    if mlx_available():
        available.add(MLX)
    if cuda_available():
        available.add(CUDA)
    return frozenset(available)


def require_engines(required: set[str]) -> None:
    """Refuse a real studio whose named backends need an engine this host lacks.

    The stub passes through, so the page stays workable on a host that cannot run a
    model. The refusal happens before the port is bound, so such a host never
    occupies it.
    """
    if not required:
        return
    missing = required - available_engines()
    if not missing:
        return
    names = ", ".join(_ENGINES.get(engine, engine) for engine in sorted(missing))
    raise EngineUnavailable(
        f"this machine has no {names} GPU, so the backends that need it cannot run. "
        "Run the studio with --stub to work on the page, or offer only the backends this host can run. "
        "See studio/l3_interface_adapters/gateways/image/qwen21/PORTABILITY.md."
    )
