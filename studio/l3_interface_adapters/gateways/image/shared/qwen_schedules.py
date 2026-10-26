"""The schedules a Qwen checkpoint record can name: mflux's linear one, ComfyUI's
linear_quadratic sigmas, and ComfyUI's rectified-flow Euler ancestral on those sigmas.

Many Qwen-Image-2.1 finetunes publish ComfyUI settings, so their authors tuned them on
ComfyUI's schedules. mflux ships neither of the two, so this module registers both.

The linear_quadratic nodes are the final flow sigmas. Both classes replace
`_get_sigmas`, and `LinearScheduler` applies the resolution shift and the terminal
rescale only inside its own `_get_sigmas`, so neither applies here. The linear schedule
keeps mflux's own sigmas, shift included, so it reads the model config.

Euler ancestral draws fresh noise at each step. A key from the run's seed starts the
stream, through a hook that mflux calls before the loop, so a seed gives the same image
again. Editing cannot take it: the pinned edit engine hard-codes its Euler loop. An edit
samples the same sigmas with Euler.

This sits beside the backends rather than inside one, because a backend may not import
another backend. `viggle_schedule` and `qwen21_turbo_schedule` are here for the same reason.
"""

from contextlib import contextmanager
from typing import cast

LINEAR = "linear"
LINEAR_QUADRATIC = "qwen_linear_quadratic"
EULER_ANCESTRAL = "qwen_linear_quadratic_euler_ancestral"

# The names a record uses, and the samplers each one allows.
SCHEDULES = ("linear", "linear_quadratic")
SAMPLERS = ("euler", "euler_ancestral")


def sigma_nodes(steps: int) -> list[float]:
    """Comfy-Org/ComfyUI comfy/samplers.py, linear_quadratic_schedule, threshold_noise=0.025."""
    if steps == 1:
        return [1.0, 0.0]
    linear = steps // 2
    quadratic = steps - linear
    difference = linear - 0.025 * steps
    a = difference / (linear * quadratic**2)
    b = 0.025 / linear - 2 * difference / quadratic**2
    c = a * linear**2
    schedule = [i * 0.025 / linear for i in range(linear)]
    schedule.extend(a * i**2 + b * i + c for i in range(linear, steps))
    return [1.0 - value for value in schedule] + [0.0]


def generate_scheduler(schedule: str, sampler: str) -> str:
    """The name that the generate call passes to mflux."""
    if sampler == "euler_ancestral":
        return EULER_ANCESTRAL
    return edit_scheduler(schedule)


def edit_scheduler(schedule: str) -> str:
    """The name that an edit samples. It is always Euler."""
    return LINEAR_QUADRATIC if schedule == "linear_quadratic" else LINEAR


class AncestralSeedHook:
    """Start the noise stream of each image from its seed, also for a cached prompt."""

    def call_before_loop(self, seed, config, **_kwargs):
        config.scheduler.reset_noise(seed)


def register_schedules() -> None:
    """Make both schedules known to mflux by name.

    The gateway calls this when a run starts. Not at import or at build: building a
    backend must not import mflux, because the stub builds every backend on hosts that
    cannot run a model. A second call replaces the entries with equal ones.
    """
    import mlx.core as mx
    from mflux.models.common.schedulers import register_contrib
    from mflux.models.common.schedulers.linear_scheduler import LinearScheduler

    class LinearQuadratic(LinearScheduler):
        def _get_sigmas(self):
            return mx.array(sigma_nodes(self.config.num_inference_steps), dtype=mx.float32)

    class FlowEulerAncestral(LinearScheduler):
        """ComfyUI's sample_euler_ancestral_RF with eta=1 and s_noise=1."""

        def __init__(self, config):
            super().__init__(config)
            self._key = None

        def _get_sigmas(self):
            return mx.array(sigma_nodes(self.config.num_inference_steps), dtype=mx.float32)

        def reset_noise(self, seed):
            # The initial noise uses a key from the same seed. Each draw here uses a
            # split subkey, not that key itself.
            self._key = mx.random.key(seed)

        def step(self, noise, timestep, latents, **_kwargs):
            if self._key is None:
                raise RuntimeError("Euler ancestral needs the seed hook before the loop")
            sigma = cast(float, self._sigmas[timestep].item())
            next_sigma = cast(float, self._sigmas[timestep + 1].item())
            x, velocity = latents.astype(mx.float32), noise.astype(mx.float32)
            if next_sigma == 0:
                return (x + (next_sigma - sigma) * velocity).astype(latents.dtype)
            denoised = x - sigma * velocity
            down = next_sigma**2 / sigma
            alpha_next, alpha_down = 1 - next_sigma, 1 - down
            renoise = max(0.0, next_sigma**2 - down**2 * alpha_next**2 / alpha_down**2) ** 0.5
            ratio = down / sigma
            result = (alpha_next / alpha_down) * (ratio * x + (1 - ratio) * denoised)
            self._key, subkey = mx.random.split(self._key)
            random_noise = mx.random.normal(x.shape, dtype=mx.float32, key=subkey)
            return (result + renoise * random_noise).astype(latents.dtype)

    register_contrib(LinearQuadratic, LINEAR_QUADRATIC)
    register_contrib(FlowEulerAncestral, EULER_ANCESTRAL)


@contextmanager
def edit_schedule(name: str):
    """Make `Config`'s own default this schedule for the length of the block.

    The edit call takes no scheduler argument and builds its `Config` without one, so
    the default is the only way in. Same patch, and same reason, as `viggle_schedule`.
    The linear schedule is already the default, so it needs no patch.
    """
    if name == LINEAR:
        yield
        return
    from mflux.models.common.config.config import Config

    original = Config.__init__

    def with_schedule(self, *args, **kwargs):
        kwargs.setdefault("scheduler", name)
        original(self, *args, **kwargs)

    Config.__init__ = with_schedule
    try:
        yield
    finally:
        Config.__init__ = original
