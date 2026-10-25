from dataclasses import replace

import pytest

from studio.l1_entities.errors import InvalidJob
from studio.l1_entities.lora import Lora, LoraUse, check_offer, parse_loras, with_triggers

WARM = Lora("warm", "Warm light", strength=0.8, min_strength=0.1, max_strength=1.5, recommended=(0.6, 1.0))
GRAIN = Lora("grain", "Film grain", trigger="film grain")
OFFER = (WARM, GRAIN)


def test_a_pick_takes_its_strength_or_the_lora_s_own():
    picks = parse_loras([{"id": "warm", "strength": 1.2}, {"id": "grain"}], OFFER, 2)

    assert picks == (LoraUse("warm", 1.2), LoraUse("grain", 1.0))


def test_a_form_field_carries_the_same_list_as_json():
    assert parse_loras('[{"id": "warm", "strength": 1}]', OFFER, 1) == (LoraUse("warm", 1.0),)


@pytest.mark.parametrize("raw", [None, "", "  ", []])
def test_no_pick_is_no_lora(raw):
    assert parse_loras(raw, OFFER, 2) == ()
    assert parse_loras(raw, (), 0) == ()  # a model with no LoRAs still takes an empty pick


@pytest.mark.parametrize(
    ("raw", "message"),
    [
        ("[", "JSON list"),
        ({"id": "warm"}, "list of"),
        ([{"id": "warm"}, {"id": "grain"}, {"id": "warm"}], "at most 2 LoRAs"),
        (["warm"], "an object"),
        ([{"id": "cold"}], "one of warm, grain"),
        ([{"strength": 1}], "one of warm, grain"),
        ([{"id": "warm", "strength": "high"}], "must be a number"),
        ([{"id": "warm", "strength": True}], "must be a number"),
        ([{"id": "warm", "strength": float("nan")}], "must be a number"),
        ([{"id": "warm", "strength": 10**400}], "must be a number"),
        ([{"id": "warm", "strength": 1.6}], "between 0.1 and 1.5"),
        ([{"id": "warm"}, {"id": "warm"}], "picked twice"),
    ],
)
def test_a_bad_pick_is_refused_with_its_reason(raw, message):
    with pytest.raises(InvalidJob, match=message):
        parse_loras(raw, OFFER, 2)


def test_a_model_with_no_loras_refuses_a_pick():
    with pytest.raises(InvalidJob, match="offers no LoRAs"):
        parse_loras([{"id": "warm"}], (), 0)


def test_one_lora_is_named_in_the_singular():
    with pytest.raises(InvalidJob, match=r"at most 1 LoRA\.$"):
        parse_loras([{"id": "warm"}, {"id": "grain"}], OFFER, 1)


def test_trigger_words_follow_the_prompt_once():
    picks = (LoraUse("grain", 1.0), LoraUse("warm", 0.8))

    assert with_triggers("a harbor at dawn ", picks, OFFER) == "a harbor at dawn, film grain"
    assert with_triggers("Film Grain over a harbor", picks, OFFER) == "Film Grain over a harbor"
    assert with_triggers("", picks, OFFER) == "film grain"
    assert with_triggers("a harbor", (), OFFER) == "a harbor"


def test_two_loras_with_the_same_trigger_add_it_once():
    other = Lora("grain_two", "Grain two", trigger="film grain")
    picks = (LoraUse("grain", 1.0), LoraUse("grain_two", 1.0))

    assert with_triggers("a harbor", picks, (GRAIN, other)) == "a harbor, film grain"


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"id": "Warm"}, "lowercase"),
        ({"id": "warm-light"}, "lowercase"),
        ({"strength": 3.0}, "outside its own strength range"),
        ({"strength_step": 0}, "step above 0"),
        ({"recommended": (0.5, 2.5)}, "recommends a range"),
        ({"recommended": (1.0, 0.5)}, "recommends a range"),
    ],
)
def test_a_bad_declaration_fails_where_it_is_written(fields, message):
    with pytest.raises(ValueError, match=message):
        replace(Lora("warm", "Warm"), **fields)


def test_an_offer_needs_unique_ids_and_room_for_one():
    check_offer(OFFER, 2, "demo")
    check_offer((), 0, "demo")
    with pytest.raises(ValueError, match="twice"):
        check_offer((WARM, WARM), 2, "demo")
    with pytest.raises(ValueError, match="at least 1"):
        check_offer(OFFER, 0, "demo")
    with pytest.raises(ValueError, match="0 or more"):
        check_offer((), -1, "demo")
