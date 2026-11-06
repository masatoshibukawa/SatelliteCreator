import json
from pathlib import Path

import pytest

from satellitecreator.catalog import reference_bus
from satellitecreator.intake import build_intake
from satellitecreator.iteration import LoopStatus, PowerAgent, run_design_loop
from satellitecreator.launch_request import build_launch_request, to_json
from satellitecreator.session import ReviewState, run_session
from satellitecreator.simulation import project_ledger

EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "one_unit"
PROMPT = (EXAMPLE_DIR / "request.txt").read_text(encoding="utf-8").strip()
ANSWERS = {
    "stakeholders": "大学の研究室",
    "minimum_success": "1 枚の地球画像を地上へ降ろす",
    "mission_payload": "小型カメラを搭載する",
    "communication": "UHF で画像を降ろす",
    "power": "太陽電池で賄う",
    "attitude_control": "受動磁気で安定させる",
    "thermal_control": "バッテリを保温する",
    "data_handling": "画像を記録して送る",
    "operations_concept": "上空通過時に通信する",
}


def test_power_values_come_from_the_published_m_cubed_table():
    bus = reference_bus("1U")

    assert bus.min_consumed_power_w == pytest.approx(0.216 + 0.6165 + 0.2275)
    assert bus.max_consumed_power_w == pytest.approx(0.2925 + 0.6165 + 1.0 + 0.25 + 1.254)
    assert bus.battery_capacity_j == pytest.approx(4 * 3.89 * 3600, rel=0.001)


def test_bus_is_marked_provisional_and_names_its_source():
    bus = reference_bus("1U")

    assert bus.provisional
    assert "space.pitt.edu" in bus.source


def test_mass_is_within_the_one_unit_limit():
    ledger = project_ledger(build_intake(PROMPT, {}).project)

    assert ledger.value("total_mass_kg") <= ledger.value("max_mass_kg")


def test_every_block_is_calculated():
    assert {item.state for item in run_session(PROMPT, {}).simulations} == {"done"}


def test_loop_reaches_a_passing_design():
    result = run_design_loop(build_intake(PROMPT, {}).project)

    assert result.status is LoopStatus.CONVERGED


def test_all_checks_that_can_run_pass():
    states = {item.id: item.state for item in run_session(PROMPT, ANSWERS).checks}

    assert "failed" not in states.values()


def test_answered_one_unit_design_passes_every_review():
    answers = {**ANSWERS, "mission_duration": "1 か月"}

    reviews = run_session(PROMPT, answers).reviews

    assert {item.state for item in reviews} == {ReviewState.PASSED}


def test_launch_request_is_built_with_the_agreed_fields():
    request = build_launch_request(build_intake(PROMPT, {}).project, "OneU")

    assert request.envelope_mm.height == 113.5
    assert request.provisional is True
    assert "space.pitt.edu" in request.sources["payload_mass_kg"]


def test_example_file_matches_what_the_code_produces():
    project = run_design_loop(build_intake(PROMPT, {}).project).project
    expected = to_json(build_launch_request(project, "SatelliteCreator 1U")) + "\n"

    assert (EXAMPLE_DIR / "launch_request.json").read_text(encoding="utf-8") == expected


def test_example_keeps_the_agreed_format():
    data = json.loads((EXAMPLE_DIR / "launch_request.json").read_text(encoding="utf-8"))

    assert data["schema_version"] == 1
    assert data["target_perigee_m"] == data["target_apogee_m"]


def test_power_agent_does_not_switch_when_pointing_would_not_help():
    project = build_intake(PROMPT, {}).project
    starved = project.model_copy(
        update={"design": project.design.model_copy(update={"heater_power_w": 50.0})}
    )

    assert PowerAgent().review(starved, project_ledger(starved), ()) is None
