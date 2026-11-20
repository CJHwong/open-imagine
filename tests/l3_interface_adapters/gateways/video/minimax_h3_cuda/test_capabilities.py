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
