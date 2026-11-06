import pytest

from satellitecreator.gates import evaluate_gate
from satellitecreator.intake import build_intake, parse_mission_duration_s
from satellitecreator.process import Review
from satellitecreator.session import ReviewState, run_session
from satellitecreator.simulation import project_ledger

BASE = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
ANSWERS = {
    "stakeholders": "大学の研究室",
    "minimum_success": "地上で光信号を検出する",
    "mission_payload": "レーザ通信端末を搭載する",
    "communication": "S 帯でデータを降ろす",
    "power": "太陽電池で賄う",
    "attitude_control": "地上局を指向する",
    "thermal_control": "レーザ端末を保温する",
    "data_handling": "記録して地上へ送る",
    "operations_concept": "上空通過時に通信する",
}


def _ledger():
    return project_ledger(build_intake(BASE, {}).project)


def test_slant_range_reproduces_the_report():
    assert _ledger().value("slant_range_m") == pytest.approx(1_805_000, rel=0.001)


def test_free_space_loss_reproduces_the_report():
    assert _ledger().value("free_space_loss_db") == pytest.approx(164.76, abs=0.05)


def test_link_margin_reproduces_the_report():
    assert _ledger().value("link_margin_db") == pytest.approx(6.85, abs=0.1)


def test_higher_orbit_has_a_smaller_link_margin():
    high = project_ledger(build_intake(BASE.replace("400 km", "800 km"), {}).project)

    assert high.value("link_margin_db") < _ledger().value("link_margin_db")


def test_natural_frequency_is_near_the_lowest_value_in_the_report():
    assert _ledger().value("natural_frequency_hz") == pytest.approx(116.57, rel=0.3)


def test_structure_values_are_provisional():
    assert _ledger().get("natural_frequency_hz").provisional


def test_all_blocks_are_calculated_for_a_three_unit_design():
    result = run_session(BASE, {})

    assert {item.state for item in result.simulations} == {"done"}


def test_link_and_frequency_checks_pass_for_the_baseline():
    states = {item.id: item.state for item in run_session(BASE, {}).checks}

    assert states["link_margin_positive"] == "passed"
    assert states["natural_frequency_meets_launcher"] == "passed"


def _reviews(result):
    return {item.review: item for item in result.reviews}


def test_fully_answered_design_reaches_pdr():
    reviews = _reviews(run_session(BASE, ANSWERS))

    assert reviews[Review.SRR].state is ReviewState.PASSED
    assert reviews[Review.SDR].state is ReviewState.PASSED
    assert reviews[Review.PDR].state is ReviewState.PASSED


def test_cdr_stays_blocked_while_any_check_has_not_run():
    cdr = _reviews(run_session(BASE, ANSWERS))[Review.CDR]

    assert cdr.state is ReviewState.BLOCKED
    assert {item.code for item in cdr.findings} == {"check_not_run"}
    assert {item.subject for item in cdr.findings} == {"orbit_lifetime_covers_mission"}


def test_stated_mission_duration_lets_the_design_pass_cdr():
    answers = {**ANSWERS, "mission_duration": "3 か月"}

    assert _reviews(run_session(BASE, answers))[Review.CDR].state is ReviewState.PASSED


def test_mission_longer_than_the_orbit_lifetime_fails():
    states = {
        item.id: item.state
        for item in run_session(BASE, {**ANSWERS, "mission_duration": "5 年"}).checks
    }

    assert states["orbit_lifetime_covers_mission"] == "failed"


@pytest.mark.parametrize(
    ("text", "bare", "expected"),
    [
        ("ミッション期間 2 年", False, 2 * 365.25 * 86400),
        ("運用期間は 6 か月", False, 6 * 30.4375 * 86400),
        ("6ヶ月", True, 6 * 30.4375 * 86400),
        ("2 年", False, None),
        ("未定", True, None),
        ("ミッション期間 約 2 年", False, None),
    ],
)
def test_parse_mission_duration(text, bare, expected):
    assert parse_mission_duration_s(text, bare=bare) == expected


def test_orbit_lifetime_grows_with_altitude():
    high = project_ledger(build_intake(BASE.replace("400 km", "600 km"), {}).project)

    assert high.value("orbit_lifetime_s") > _ledger().value("orbit_lifetime_s")


def test_margin_of_safety_is_positive_and_provisional():
    entry = _ledger().get("margin_of_safety_ratio")

    assert entry.value > 0
    assert entry.provisional


def test_pdr_blocks_on_a_failed_check():
    project = build_intake(f"{BASE}。消費電力 500 W", {}).project

    findings = evaluate_gate(project, Review.PDR).findings

    assert "check_failed" in {item.code for item in findings}


def test_pdr_blocks_when_a_block_has_no_result():
    project = build_intake("高度 500 km、傾斜角 97 度の 6U 衛星", {}).project

    assert "analysis_missing" in {item.code for item in evaluate_gate(project, Review.PDR).findings}


def test_subsystem_requirements_are_derived_only_from_settled_requirements():
    result = run_session(BASE, {})

    assert not [item for item in result.requirements if item.id.startswith("SS-")]


def test_subsystem_requirements_trace_to_system_requirements():
    result = run_session(BASE, ANSWERS)

    derived = [item for item in result.requirements if item.id.startswith("SS-")]

    assert derived
    assert all(item.parents[0].startswith("SR-") for item in derived)


def test_passes_that_rest_on_stand_in_values_are_marked():
    reviews = _reviews(run_session(BASE, {**ANSWERS, "mission_duration": "3 か月"}))

    assert reviews[Review.PDR].provisional
    assert reviews[Review.CDR].provisional
    assert not reviews[Review.SRR].provisional


def test_unverified_subsystem_requirements_stay_assumptions():
    result = run_session(BASE, ANSWERS)

    assumed = [
        item
        for item in result.requirements
        if item.id.startswith("SS-") and item.status == "assumed"
    ]

    assert {item.function for item in assumed} == {"mission", "attitude_control", "data_handling"}
    assert all(item.rationale for item in assumed)


def test_lifetime_stops_growing_above_the_valid_altitude():
    at_limit = project_ledger(build_intake(BASE.replace("400 km", "600 km"), {}).project)
    above = project_ledger(build_intake(BASE.replace("400 km", "800 km"), {}).project)

    ratio = above.value("orbit_lifetime_s") / at_limit.value("orbit_lifetime_s")

    assert ratio < 1.1
