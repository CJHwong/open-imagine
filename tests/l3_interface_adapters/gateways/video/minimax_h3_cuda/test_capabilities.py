from studio.l3_interface_adapters.gateways.video.minimax_h3_cuda.capabilities import (
    CAPABILITIES,
    MAX_FRAMES,
    MIN_FRAMES,
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
