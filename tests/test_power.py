import pytest

from satellitecreator.catalog import reference_bus
from satellitecreator.core.ledger import solve
from satellitecreator.document import build_document
from satellitecreator.intake import build_intake
from satellitecreator.iteration import LoopStatus, PowerAgent, run_design_loop
from satellitecreator.simulation import project_ledger

BASE = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
HOT = f"{BASE}。消費電力 20 W"


def _with(project, **changes):
    return project.model_copy(update={"design": project.design.model_copy(update=changes)})


@pytest.mark.parametrize(
    ("attitude", "expected_mah"), [("free_rotation", 5243.22), ("sun_pointing", 7961.22)]
)
def test_daily_consumption_reproduces_the_report_table(attitude, expected_mah):
    assert reference_bus("3U").daily_charge_mah(attitude) == pytest.approx(expected_mah, abs=0.5)


def test_battery_energy_comes_from_voltage_and_capacity():
    assert reference_bus("3U").battery_capacity_j == pytest.approx(9.6 * 2.45 * 3600)


def test_usable_power_reproduces_the_report_table():
    ledger = solve(
        {
            "altitude_m": 400e3,
            "inclination_deg": 51.6,
            "sunlit_generated_power_w": 8.7423,
            "charge_efficiency_ratio": 0.692,
        }
    )

    assert ledger.value("usable_sunlit_power_w") == pytest.approx(6.0497, abs=0.001)


def test_energy_balance_uses_the_shortest_sunlight_and_the_full_orbit():
    ledger = project_ledger(build_intake(BASE, {}).project)

    usable = ledger.value("usable_sunlit_power_w")
    assert ledger.value("orbit_generated_energy_j") == pytest.approx(
        usable * ledger.value("min_sunlight_s")
    )
    assert ledger.value("orbit_consumed_energy_j") == pytest.approx(
        ledger.value("average_consumed_power_w") * ledger.value("orbit_period_s")
    )


def test_baseline_design_balances():
    ledger = project_ledger(build_intake(BASE, {}).project)

    assert ledger.value("orbit_generated_energy_j") > ledger.value("orbit_consumed_energy_j")


def test_heater_runs_only_in_eclipse_in_the_energy_budget():
    project = build_intake(BASE, {}).project
    off = project_ledger(project)
    on = project_ledger(_with(project, heater_power_w=5.0))

    extra = on.value("orbit_consumed_energy_j") - off.value("orbit_consumed_energy_j")

    assert extra == pytest.approx(5.0 * off.value("max_eclipse_s"))


def test_stated_peak_power_raises_the_average_for_its_duty():
    base = project_ledger(build_intake(BASE, {}).project)
    hot = project_ledger(build_intake(HOT, {}).project)

    extra_w = hot.value("average_consumed_power_w") - base.value("average_consumed_power_w")

    assert extra_w == pytest.approx((20.0 - 12.586) * 0.5 / 24)


def test_covering_the_body_with_another_finish_loses_body_cells():
    project = build_intake(BASE, {}).project

    cells = project_ledger(project).value("sunlit_generated_power_w")
    painted = project_ledger(_with(project, surface="カプトン")).value("sunlit_generated_power_w")

    assert painted == pytest.approx(cells * 9.8 / 16.4)


def test_sun_pointing_generates_more_and_keeps_paddle_cells_under_any_finish():
    project = build_intake(BASE, {}).project

    pointing = project_ledger(_with(project, attitude="sun_pointing"))
    painted = project_ledger(_with(project, attitude="sun_pointing", surface="カプトン"))

    assert pointing.value("sunlit_generated_power_w") == pytest.approx(12.667)
    assert painted.value("sunlit_generated_power_w") == pytest.approx(12.667)


def test_sun_pointing_costs_more_power_on_average():
    project = build_intake(BASE, {}).project

    free = project_ledger(project).value("average_consumed_power_w")
    pointing = project_ledger(_with(project, attitude="sun_pointing"))

    assert pointing.value("average_consumed_power_w") > free


def test_depth_of_discharge_is_eclipse_energy_over_battery_energy():
    ledger = project_ledger(build_intake(BASE, {}).project)

    expected = (
        ledger.value("average_consumed_power_w")
        * ledger.value("max_eclipse_s")
        / ledger.value("battery_capacity_j")
    )

    assert ledger.value("battery_depth_of_discharge_ratio") == pytest.approx(expected)


def test_power_agent_switches_to_sun_pointing_when_energy_runs_short():
    project = _with(build_intake(BASE, {}).project, surface="カプトン", heater_power_w=9.0)
    ledger = project_ledger(project)

    change = PowerAgent().review(project, ledger, ())

    assert change.project.design.attitude == "sun_pointing"
    assert change.message.agent == "電源"


def test_power_agent_has_no_further_move_once_sun_pointing():
    project = _with(
        build_intake(BASE, {}).project,
        surface="カプトン",
        heater_power_w=30.0,
        attitude="sun_pointing",
    )

    assert PowerAgent().review(project, project_ledger(project), ()) is None


def test_power_agent_stays_quiet_when_the_budget_closes():
    project = build_intake(BASE, {}).project

    assert PowerAgent().review(project, project_ledger(project), ()) is None


def test_design_that_cannot_be_closed_asks_the_user_to_revisit_the_requirement():
    result = run_design_loop(build_intake(f"{BASE}。消費電力 500 W", {}).project)

    assert result.status is LoopStatus.NO_SOLUTION
    assert any("要求" in item and "見直" in item for item in result.questions)


def test_document_reports_the_energy_budget():
    document = build_document(build_intake(BASE, {}).project)

    lines = next(item for item in document.sections if item.number == "2").lines

    assert any(line.startswith("1 周回の発電量") for line in lines)
    assert any(line.startswith("1 周回の消費量") for line in lines)
    item = next(item for item in document.checklist if item.number == 12)
    assert item.state == "partial"
