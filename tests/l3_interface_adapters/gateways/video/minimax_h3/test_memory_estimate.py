import pytest

from studio.l1_entities.errors import InsufficientMemory
from studio.l3_interface_adapters.api.resource_admission import GIB
from tests.support.memory_estimates import admission_for, estimate
from tests.support.memory_estimates import calibrated_mac_estimate_platform as calibrated_mac_estimate_platform


def h3(**options):
    return estimate("video", "minimax_h3", **options)


@pytest.mark.parametrize(
    ("width", "height", "num_frames"),
    ((512, 288, 73), (512, 512, 175), (1280, 704, 73), (1024, 576, 175), (576, 1024, 175)),
)
def test_h3_keeps_the_smaller_run_figure_for_clips_up_to_its_rows(width, height, num_frames):
    assert h3(width=width, height=height, num_frames=num_frames) == pytest.approx(35.6)


@pytest.mark.parametrize(("width", "height"), ((1280, 704), (704, 1280)))
def test_h3_estimates_its_largest_measured_clip_in_either_orientation(width, height):
    assert h3(width=width, height=height, num_frames=175) == pytest.approx(49.6)


def test_h3_follows_a_straight_line_between_the_two_runs():
    # 37 latent frames of 40 x 22 rows, between 52 x 32 x 18 and 52 x 40 x 22.
    expected = 35.6 + (49.6 - 35.6) * (37 * 880 - 52 * 576) / (52 * 880 - 52 * 576)

    assert h3(width=1280, height=704, num_frames=124) == pytest.approx(expected)


def test_h3_counts_each_still_as_one_more_latent_frame_and_a_track_as_none():
    stills = [{"frame_index": 0}, {"frame_index": 174}]
    expected = 35.6 + (49.6 - 35.6) * (54 * 576 - 52 * 576) / (52 * 880 - 52 * 576)

    assert h3(width=1024, height=576, num_frames=175, references=stills) == pytest.approx(expected)
    assert h3(width=1024, height=576, num_frames=175, audio={"data": "track"}) == pytest.approx(35.6)


def test_h3_admission_refuses_its_largest_clip_on_an_idle_mac_and_takes_a_shorter_one():
    # An idle 64 GiB Mac reported 87% free before the measured runs.
    admission = admission_for(lambda: (64 * GIB, int(0.87 * 64 * GIB)))
    request = {"kind": "video", "backend": "minimax_h3", "width": 1280, "height": 704}

    with pytest.raises(InsufficientMemory, match=r"49\.6 GiB"):
        admission({**request, "num_frames": 175})
    assert admission({**request, "num_frames": 124}) is None


@pytest.mark.parametrize("loras", ([{"id": "lora", "strength": 0.7}], '[{"id": "lora", "strength": 0.7}]'))
@pytest.mark.parametrize(("width", "height", "num_frames"), ((512, 288, 73), (1024, 576, 175), (576, 1024, 175)))
def test_h3_adds_the_measured_lora_figure_to_clips_up_to_the_smaller_run(width, height, num_frames, loras):
    assert h3(width=width, height=height, num_frames=num_frames, loras=loras) == pytest.approx(35.6 + 2.5)


def test_h3_fast_mode_keeps_the_figure_of_the_base_schedule():
    # Four forwards on the same weights peaked at the same 29.2 GiB worker footprint as eight.
    for size in ({"width": 1024, "height": 576, "num_frames": 124}, {"width": 1280, "height": 704, "num_frames": 73}):
        assert h3(**size, fast_mode=True) == pytest.approx(h3(**size))


def test_h3_grows_the_lora_figure_with_the_rows():
    # 52 latent frames of 40 x 22 rows, against 52 x 32 x 18 in the measured run.
    expected = 49.6 + 2.5 * 880 / 576

    assert h3(width=1280, height=704, num_frames=175, loras=[{"id": "lora"}]) == pytest.approx(expected)


def test_h3_admission_takes_one_lora_on_the_measured_clip_and_refuses_it_on_the_largest():
    admission = admission_for(lambda: (64 * GIB, int(0.87 * 64 * GIB)))
    request = {"kind": "video", "backend": "minimax_h3", "num_frames": 175, "loras": [{"id": "lora"}]}

    assert admission({**request, "width": 1024, "height": 576}) is None
    with pytest.raises(InsufficientMemory, match=r"53\.4 GiB"):
        admission({**request, "width": 1280, "height": 704})


@pytest.mark.parametrize(
    "changes",
    (
        {"mode": "edit"},
        {"loras": [{"id": "lora"}, {"id": "other"}]},
        {"loras": "not json"},
        {"loras": {"id": "lora"}},
        {"references": "still"},
        {"width": None},
        {"height": "bad"},
        {"num_frames": 0},
        {"width": 512, "height": 288, "num_frames": 192},
        {"num_frames": 74},
        {"width": 1312},
        {"width": 288, "height": 1312},
        {"num_frames": 175, "references": [{"frame_index": 0}]},
    ),
)
def test_h3_fails_closed_for_unmeasured_modes_and_inputs(changes):
    request = {"width": 1280, "height": 704, "num_frames": 124, **changes}

    assert h3(**request) is None
