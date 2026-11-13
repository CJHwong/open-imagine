from studio.l1_entities.capabilities import Estimate
from studio.l3_interface_adapters.gateways.image.flux3.capabilities import (
    GENERATE_ESTIMATE,
    MATCH_CAP,
    REFERENCE_ESTIMATE,
    flux3_capabilities,
)


def seconds(estimate: Estimate, megapixels: float, steps: int = 16, references: int = 1) -> float:
    growth = 1 + estimate.per_reference * (references - 1)
    return steps * estimate.step_cost * growth * megapixels**estimate.exponent + estimate.overhead


def test_the_text_figure_holds_the_three_measured_runs():
    assert [round(seconds(GENERATE_ESTIMATE, mp), 0) for mp in (0.262, 0.590, 1.049)] == [13, 25, 54]


def test_the_reference_figure_holds_both_measured_rows():
    one = [round(seconds(REFERENCE_ESTIMATE, mp, references=1), 0) for mp in (0.262, 0.590, 1.049)]
    two = [round(seconds(REFERENCE_ESTIMATE, mp, references=2), 0) for mp in (0.262, 0.590, 1.049)]
    assert one == [32, 48, 76]
    assert two == [34, 53, 86]


def test_both_modes_offer_the_reference_figure_and_a_match_cap():
    capabilities = flux3_capabilities("bf16")
    generate = capabilities.mode("generate")
    edit = capabilities.mode("edit")
    assert generate.estimate is GENERATE_ESTIMATE
    assert edit.reference_estimate is REFERENCE_ESTIMATE
    assert generate.reference_estimate is REFERENCE_ESTIMATE
    assert GENERATE_ESTIMATE.match_cap == MATCH_CAP == 1024
