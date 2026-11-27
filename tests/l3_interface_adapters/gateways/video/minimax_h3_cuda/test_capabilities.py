import pytest

from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import (
    CAPABILITIES,
    MAX_FRAMES,
    MIN_FRAMES,
    flash_capabilities,
    minimax_h3_cuda_capabilities,
)


def test_every_size_is_on_the_32_pixel_grid_and_under_the_pipeline_area_cap():
    for shape in CAPABILITIES.shapes:
        assert shape.width % 32 == 0 and shape.height % 32 == 0
        assert shape.width * shape.height <= 768 * 1344


def test_every_length_is_on_the_17n_plus_5_grid_between_5_and_15_seconds():
    """The pipeline refused 73 and 97 frames on the DGX Spark: it takes 120 to 360 at 24 fps."""
    counts = range(MIN_FRAMES, MAX_FRAMES + 1, CAPABILITIES.frame_step)
    assert all((count - 5) % 17 == 0 and 120 <= count <= 360 for count in counts)
    assert MIN_FRAMES - 17 < 120 and MAX_FRAMES + 17 > 360
    assert set(CAPABILITIES.duration_presets) <= set(counts)


def test_the_form_takes_two_stills_a_track_and_fast_mode():
    capabilities = minimax_h3_cuda_capabilities()
    assert capabilities.mode("generate").accepts_audio and capabilities.max_references == 2
    assert capabilities.fast_mode and capabilities.can_skip_audio and capabilities.precision == "nvfp4"


def test_the_audio_note_says_the_clip_does_not_carry_the_track():
    """The form's own note promises the track; this backend returns the sound it generated."""
    assert "does not carry it" in minimax_h3_cuda_capabilities().audio_track_note


def test_the_estimate_reads_the_measured_full_run_from_its_fast_runs():
    """1024 x 576 at 124 frames took 380.8 s in Fast mode: 19 forwards of 17.86 s and a 40.9 s
    tail. The figure counts the 49 forwards of a full run, about 920 s."""
    from studio.l1_entities.video_estimate import estimate_clip

    figure = estimate_clip(minimax_h3_cuda_capabilities().estimate, 1024, 576, 124)
    assert figure.steps == 49 and figure.total_seconds is not None
    assert abs(figure.total_seconds - (19 * 17.86 + 30 * 17.86 + 40.9)) / figure.total_seconds < 0.08


def test_the_fast_estimate_counts_the_measured_nineteen_forwards():
    """Fast mode took 716.7 s at 1280 x 704: 19 forwards of 33.09 s and an 87.5 s tail. The plan
    now counts the 19 forwards and names no speedup in its excludes."""
    from studio.l1_entities.video_estimate import estimate_clip

    figure = estimate_clip(minimax_h3_cuda_capabilities().estimate, 1280, 704, 124, fast_mode=True)
    assert figure.steps == 19 and figure.total_seconds is not None
    assert abs(figure.total_seconds - 716.7) / 716.7 < 0.02
    assert "Fast mode speedup" not in figure.excludes


def test_the_form_takes_nine_pictures_and_the_track_as_a_reference_beside_no_keyframe():
    mode = minimax_h3_cuda_capabilities().mode("generate")
    assert (mode.max_pictures, mode.reference_audio, mode.pictures_with_keyframes) == (9, True, False)
    assert mode.keyframes_at_ends


def test_the_estimate_reads_both_measured_picture_runs():
    """Two pictures took 992 s at 512 x 288 over 49 forwards. At 1024 x 576 they took 873 s
    over 19 forwards, which the figure counts as 49: 30 more forwards of 42.96 s."""
    from studio.l1_entities.video_estimate import estimate_clip

    estimate = minimax_h3_cuda_capabilities().estimate
    small = estimate_clip(estimate, 512, 288, 124, pictures=2).total_seconds
    large = estimate_clip(estimate, 1024, 576, 124, pictures=2).total_seconds
    assert small is not None and abs(small - 992) / 992 < 0.03
    assert large is not None and abs(large - (873 + 30 * 42.96)) / large < 0.03


def test_a_picture_beside_a_track_keeps_the_measured_track_factor():
    from studio.l1_entities.video_estimate import estimate_clip

    estimate = minimax_h3_cuda_capabilities().estimate
    one = estimate_clip(estimate, 512, 288, 124, pictures=1, audio=True).total_seconds
    assert one == estimate_clip(estimate, 512, 288, 124, audio=True).total_seconds


def test_flash_keeps_the_base_form_without_fast_mode():
    flash, base = flash_capabilities(), minimax_h3_cuda_capabilities()
    assert (flash.shapes, flash.min_frames, flash.max_frames, flash.modes) == (
        base.shapes,
        base.min_frames,
        base.max_frames,
        base.modes,
    )
    assert not flash.fast_mode and not flash.fast_mode_note


@pytest.mark.parametrize(
    ("width", "height", "frames", "measured"),
    [
        (512, 288, 124, 32.1),
        (512, 512, 124, 58.2),
        (1024, 576, 124, 138.5),
        (1280, 704, 124, 261.7),
        (512, 288, 345, 109.3),
    ],
)
def test_the_flash_estimate_reads_each_measured_text_clip_within_a_tenth(width, height, frames, measured):
    """The fit reads each within 8%; the figure rounds to 10 s, which moves the 1024 x 576 clip to 8.3%."""
    from studio.l1_entities.video_estimate import estimate_clip

    figure = estimate_clip(flash_capabilities().estimate, width, height, frames)
    assert figure.steps == 6 and figure.total_seconds is not None
    assert abs(figure.total_seconds - measured) / measured <= 0.1


def test_the_flash_estimate_reads_both_picture_runs_and_the_track():
    """Two pictures took 142.5 s at 512 x 288 and 304.9 s at 1024 x 576; a picture and a track
    took 82.2 s. The figure rounds to 10 s."""
    from studio.l1_entities.video_estimate import estimate_clip

    estimate = flash_capabilities().estimate
    for width, height, measured in ((512, 288, 142.5), (1024, 576, 304.9)):
        figure = estimate_clip(estimate, width, height, 124, pictures=2).total_seconds
        assert figure is not None and abs(figure - measured) / measured < 0.06
    track = estimate_clip(estimate, 512, 288, 124, pictures=1, audio=True).total_seconds
    assert track is not None and abs(track - 82.2) / 82.2 < 0.1
