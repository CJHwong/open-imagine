from studio.l1_entities.music_capabilities import MusicEstimate
from studio.l3_interface_adapters.gateways.music.yue2.capabilities import yue2_capabilities

MEASURED = MusicEstimate(
    generate_base_seconds=159.4,
    generate_seconds_per_lyric_character=0.0258,
    instrumental_extra_seconds=123.8,
    plan_seconds=10.1,
    cover_seconds=18.2,
    transcribe_seconds=6.1,
)


def measured(mode: str, lyrics_characters: int = 0, instrumental: bool = False) -> float:
    figure = MEASURED.seconds(mode, lyrics_characters, instrumental)
    assert figure is not None
    return figure


def test_the_generate_figure_holds_the_two_measured_lyric_lengths():
    assert round(measured("generate", 33), 1) == 160.3
    assert round(measured("generate", 3048), 1) == 238.0


def test_an_instrumental_pays_for_the_melody_plan_it_transfers():
    assert round(measured("generate", 0, instrumental=True), 1) == 283.2
    assert measured("generate", 0) + MEASURED.instrumental_extra_seconds == measured("generate", 0, True)


def test_each_other_mode_has_its_own_measured_figure():
    assert measured("plan", 18) == 10.1
    assert measured("cover", 18) == 18.2
    assert measured("transcribe") == 6.1
    assert MEASURED.seconds("unknown") is None


def test_a_negative_or_missing_lyric_length_does_not_shorten_the_base():
    assert measured("generate", -20) == MEASURED.generate_base_seconds
    assert measured("generate") == MEASURED.generate_base_seconds


def test_yue2_offers_the_estimate_it_was_measured_for():
    capabilities = yue2_capabilities()
    assert capabilities.estimate is not None
    assert round(capabilities.estimate.seconds("generate", 33) or 0, 1) == 160.3
    assert capabilities.estimate.seconds("plan") == 10.1
