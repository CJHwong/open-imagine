"""What a clip costs, before it runs.

A program that plans a queue reads this figure with the settings that the clip will run
with. It reads the model's `VideoEstimate` only, so it loads no weights. The figure is
provisional: its constants come from a handful of runs on one machine, and the first step of
a clip moves with the machine's memory, so two runs of one clip can differ by a quarter.
"""

from dataclasses import dataclass

from studio.l1_entities.video_capabilities import VideoAdapter, VideoEstimate

# A latent token covers 32 x 32 pixels, and a latent frame covers 8 frames after the first.
TOKEN_SIDE = 32
FRAMES_PER_LATENT = 8
# The steps that the runner asks for: the distilled path, the guided path of an audio track
# or a keyframe on 2.3, and an effect, with the refinement of an effect that conditions stage 2.
DISTILLED_STEPS = (8, 3)
GUIDED_STEPS = (30, 3)
EDIT_STEPS = 8
REFINE_STEPS = 3
FAST_MODE = "Fast mode speedup"


@dataclass(frozen=True)
class ClipEstimate:
    """The seconds that a clip costs, in the shape of an image estimate.

    `basis` is "provisional" when the model declares a `VideoEstimate`, and "unavailable"
    when it does not. The seconds are then None. `setup_seconds` is the fixed part of the
    clip, and `per_item_seconds` the rest. Both are rounded so that they add up to
    `total_seconds`, which is to the nearest 10 s. `excludes` names the time that the figure
    does not hold.
    """

    basis: str
    steps: int
    width: int
    height: int
    reference_count: int
    per_item_seconds: float | None = None
    setup_seconds: float | None = None
    total_seconds: float | None = None
    excludes: tuple[str, ...] = ()


def estimate_clip(
    model: VideoEstimate | None,
    width: int,
    height: int,
    num_frames: int,
    *,
    references: int = 0,
    loras: int = 0,
    audio: bool = False,
    enhance: bool = True,
    fast_mode: bool = False,
    adapter: VideoAdapter | None = None,
) -> ClipEstimate:
    """The estimate of one clip. `adapter` is the effect of an Edit, and None for Generate.

    Fast mode is counted at the default speed: no run measured how much it saves, so the
    figure names the saving in its excludes.
    """
    guided = adapter is None and (audio or (references > 0 and model is not None and model.guided_with_references))
    steps = _steps(adapter, guided)
    if model is None:
        return ClipEstimate("unavailable", steps, width, height, references)
    count = tokens(width, height, num_frames)
    if adapter is None:
        setup = model.fixed_seconds - (0.0 if enhance else model.enhance_seconds)
        clip = setup + model.scale * model.pack_factor * run_seconds(model, width, height, num_frames)
        clip *= model.guided_factor if guided else 1.0
    else:
        # An edit is never enhanced, so its floor is the loads alone. The effect's factor scales
        # the fit only: an effect that samples faster still loads the same weights.
        setup = model.fixed_seconds - model.enhance_seconds
        clip = max(setup, (model.edit[0] + model.edit[1] * count) * adapter.cost_factor)
    total = _tens(clip + loras * model.lora_seconds)
    setup = min(_tens(setup), total)
    excludes = model.excludes + ((FAST_MODE,) if fast_mode else ())
    return ClipEstimate(
        "provisional", steps, width, height, references, float(total - setup), float(setup), float(total), excludes
    )


def run_seconds(model: VideoEstimate, width: int, height: int, num_frames: int) -> float:
    """The seconds of the fit for a Generate run: the loads, the steps of stage 1 on a quarter
    of the tokens, the steps of stage 2 on all of them, and the decode. The first step of
    stage 1 counts with the loads, so stage 1 times one step fewer."""
    count = tokens(width, height, num_frames)
    quarter = count / 4
    step_1 = model.stage_1[0] * quarter + model.stage_1[1] * quarter**2
    step_2 = model.stage_2[0] * count + model.stage_2[1] * count**2
    decode = max(0.0, model.decode[0] + model.decode[1] * num_frames * width * height / 1e6)
    first, second = DISTILLED_STEPS
    return model.load[0] + model.load[1] * count + (first - 1) * step_1 + second * step_2 + decode


def tokens(width: int, height: int, num_frames: int) -> float:
    """The thousands of latent tokens of a clip of this size and length."""
    latent_frames = (num_frames - 1) // FRAMES_PER_LATENT + 1
    return latent_frames * (width // TOKEN_SIDE) * (height // TOKEN_SIDE) / 1000


def _steps(adapter: VideoAdapter | None, guided: bool) -> int:
    if adapter is not None:
        return EDIT_STEPS + (REFINE_STEPS if adapter.stage_2_conditioning else 0)
    return sum(GUIDED_STEPS if guided else DISTILLED_STEPS)


def _tens(seconds: float) -> int:
    """The nearest 10 s. Python's round() takes a half to even."""
    return round(seconds / 10) * 10
