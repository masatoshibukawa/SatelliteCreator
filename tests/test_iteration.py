import pytest

from satellitecreator.catalog import surface_finish
from satellitecreator.core.ledger import Ledger, LedgerEntry, Origin
from satellitecreator.intake import build_intake, parse_peak_power_w
from satellitecreator.iteration import LoopStatus, ThermalAgent, main, run_design_loop
from satellitecreator.session import run_session
from satellitecreator.simulation import project_ledger

BASE = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
HOT = f"{BASE}。消費電力 20 W"


def _loop(prompt: str):
    return run_design_loop(build_intake(prompt, {}).project)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("消費電力 20 W", 20.0),
        ("最大消費電力は12.5W", 12.5),
        ("光通信", None),
        ("消費電力 約 20 W", None),
    ],
)
def test_parse_peak_power(text, expected):
    assert parse_peak_power_w(text) == expected


def test_stated_peak_power_reaches_the_ledger():
    ledger = project_ledger(build_intake(HOT, {}).project)

    assert ledger.value("max_consumed_power_w") == 20.0


def test_stated_peak_power_makes_the_starting_design_too_hot():
    ledger = project_ledger(build_intake(HOT, {}).project)

    assert ledger.value("temperature_margin_k") < 0


def test_design_that_already_passes_needs_no_change():
    result = _loop(BASE)

    assert result.status is LoopStatus.CONVERGED
    assert len(result.iterations) == 1
    assert result.iterations[0].messages == ()


def test_loop_repairs_a_hot_design():
    result = _loop(HOT)

    assert result.status is LoopStatus.CONVERGED
    assert len(result.iterations) > 1
    assert project_ledger(result.project).value("temperature_margin_k") >= 0


def test_loop_changes_the_surface_then_adds_a_heater():
    design = _loop(HOT).project.design

    assert design.surface is not None
    assert design.heater_power_w > 0


def test_every_change_is_recorded_with_the_agent_and_its_reason():
    result = _loop(HOT)

    messages = [item for record in result.iterations for item in record.messages]

    assert messages
    assert all(item.agent and item.text for item in messages)


def test_each_iteration_records_the_margin_it_saw():
    result = _loop(HOT)

    assert result.iterations[0].temperature_margin_k < 0
    assert result.iterations[-1].temperature_margin_k >= 0


def test_loop_stops_when_no_agent_can_fix_the_design():
    result = _loop(f"{BASE}。消費電力 500 W")

    assert result.status is LoopStatus.NO_SOLUTION


def test_loop_respects_the_iteration_limit():
    result = run_design_loop(build_intake(HOT, {}).project, max_iterations=2)

    assert result.status is LoopStatus.LIMIT_REACHED
    assert len(result.iterations) == 2


def test_missing_orbit_is_asked_back_to_the_user():
    result = _loop("光通信を実証したい")

    assert result.status is LoopStatus.NEEDS_INPUT
    assert "軌道の高度は何 km にしますか？" in result.questions


def test_form_factor_without_equipment_data_is_asked_back():
    result = _loop("高度 500 km、傾斜角 97 度の 6U 衛星")

    assert result.status is LoopStatus.NEEDS_INPUT
    assert any("3U" in item for item in result.questions)


def test_open_requirements_stay_listed_after_convergence():
    result = _loop(BASE)

    assert "この衛星の成果を受け取る人や組織は誰ですか？" not in result.questions
    assert any("電源" in item for item in result.questions)


def test_loop_is_deterministic():
    assert _loop(HOT) == _loop(HOT)


def test_loop_uses_a_replaceable_agent():
    class Silent:
        name = "silent"

        def review(self, project, ledger, history):
            return None

    result = run_design_loop(build_intake(HOT, {}).project, agents=(Silent(),))

    assert result.status is LoopStatus.NO_SOLUTION


def test_surface_choice_changes_the_absorptivity_in_the_ledger():
    project = _loop(HOT).project

    ledger = project_ledger(project)

    finish = surface_finish(project.design.surface)
    assert ledger.value("surface_absorptivity_ratio") == finish.absorptivity


def test_heater_raises_only_the_minimum_power():
    project = _loop(HOT).project

    ledger = project_ledger(project)

    assert ledger.value("min_consumed_power_w") == pytest.approx(
        1.229 + project.design.heater_power_w
    )
    assert ledger.value("max_consumed_power_w") == 20.0


def test_session_uses_the_repaired_design_everywhere():
    result = run_session(HOT, {})

    assert result.iteration.status is LoopStatus.CONVERGED
    checks = {item.id: item.state for item in result.checks}
    assert checks["temperature_margin_positive"] == "passed"
    text = "\n".join(next(s for s in result.document.sections if s.number == "5.1").lines)
    assert "表面" in text
    assert "ヒータ" in text


def test_zero_iterations_is_rejected():
    with pytest.raises(ValueError, match="at least 1"):
        run_design_loop(build_intake(HOT, {}).project, max_iterations=0)


def test_command_prints_the_log_and_reports_success(capsys):
    status = main(["--prompt", HOT])

    output = capsys.readouterr().out
    assert status == 0
    assert "熱:" in output
    assert "結果: converged" in output


def test_command_lists_questions_and_reports_failure(capsys):
    status = main(["--prompt", "光通信を実証したい"])

    assert status == 1
    assert "質問:" in capsys.readouterr().out


def _thermal_ledger(hot_k: float, cold_k: float) -> Ledger:
    values = {
        "allowable_max_temperature_k": 323.15,
        "allowable_min_temperature_k": 263.15,
        "orbit_max_temperature_k": hot_k,
        "orbit_min_temperature_k": cold_k,
    }
    return Ledger(
        entries=tuple(
            LedgerEntry(key=key, label=key, value=value, origin=Origin.INPUT)
            for key, value in values.items()
        )
    )


def test_thermal_agent_has_nothing_to_say_when_temperatures_are_fine():
    project = build_intake(BASE, {}).project

    assert ThermalAgent().review(project, _thermal_ledger(300.0, 280.0), ()) is None


def test_thermal_agent_stops_adding_heat_at_the_heater_limit():
    project = build_intake(BASE, {}).project
    at_limit = project.model_copy(
        update={"design": project.design.model_copy(update={"heater_power_w": 10.0})}
    )

    assert ThermalAgent().review(at_limit, _thermal_ledger(300.0, 250.0), ()) is None
