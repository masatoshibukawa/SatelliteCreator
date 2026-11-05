import pytest

from satellitecreator.core import ledger as ledger_module
from satellitecreator.core.ledger import solve
from satellitecreator.core.registry import Block, Constant, load_constants
from satellitecreator.document import build_document
from satellitecreator.intake import build_intake
from satellitecreator.simulation import BlockState, block_statuses, project_ledger

PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"


def _statuses(prompt: str):
    return {
        item.block: item
        for item in block_statuses(project_ledger(build_intake(prompt, {}).project))
    }


def test_project_ledger_reads_the_orbit_from_the_design():
    ledger = project_ledger(build_intake(PROMPT, {}).project)

    assert ledger.value("altitude_m") == 400_000.0
    assert ledger.value("orbit_period_s") is not None


def test_project_ledger_carries_the_mass_limit_of_the_form_factor():
    ledger = project_ledger(build_intake(PROMPT, {}).project)

    assert ledger.value("max_mass_kg") == 4.5


def test_project_without_a_design_has_no_orbit_values():
    ledger = project_ledger(build_intake("光通信を実証したい", {}).project)

    assert ledger.value("orbit_period_s") is None


def test_orbit_block_is_done_when_the_orbit_is_known():
    orbit = _statuses(PROMPT)[Block.ORBIT]

    assert orbit.state is BlockState.DONE
    assert [item.label for item in orbit.values] == ["軌道周期", "最大の日陰時間", "最小の日照時間"]
    assert orbit.values[0].text == "92.6 分"


def test_orbit_block_waits_for_its_input():
    assert _statuses("光通信を実証したい")[Block.ORBIT].state is BlockState.WAITING


def test_blocks_without_equations_say_they_are_not_built():
    statuses = _statuses(PROMPT)

    for block in (Block.POWER, Block.COMMUNICATION, Block.STRUCTURE):
        assert statuses[block].state is BlockState.NOT_BUILT
        assert statuses[block].values == ()


def test_orbit_block_states_the_assumptions_behind_its_values():
    assert "円軌道" in _statuses(PROMPT)[Block.ORBIT].note


def _use_provisional_earth_radius(monkeypatch) -> None:
    radius = Constant(key="earth_radius_m", label="地球半径", value=6378137.0, provisional=True)
    others = tuple(item for item in load_constants() if item.key != "earth_radius_m")
    monkeypatch.setattr(ledger_module, "load_constants", lambda: (radius, *others))


def test_provisional_values_are_marked_on_the_screen(monkeypatch):
    _use_provisional_earth_radius(monkeypatch)

    ledger = solve({"altitude_m": 400e3, "inclination_deg": 51.6})
    statuses = {item.block: item for item in block_statuses(ledger)}

    assert statuses[Block.ORBIT].values[0].text == "92.6 分（暫定）"


def test_provisional_values_are_marked_in_the_document(monkeypatch):
    _use_provisional_earth_radius(monkeypatch)

    document = build_document(build_intake(PROMPT, {}).project)

    section = next(item for item in document.sections if item.number == "2")
    assert any("（暫定）" in line for line in section.lines)


def test_three_unit_design_uses_the_reference_bus():
    ledger = project_ledger(build_intake(PROMPT, {}).project)

    assert ledger.value("total_mass_kg") == pytest.approx(3.985, abs=0.001)
    assert ledger.get("total_mass_kg").provisional


def test_mass_and_thermal_blocks_are_done_for_a_three_unit_design():
    statuses = _statuses(PROMPT)

    assert statuses[Block.MASS].state is BlockState.DONE
    assert statuses[Block.THERMAL].state is BlockState.DONE
    assert "1 節点" in statuses[Block.THERMAL].note


def test_thermal_block_shows_temperatures_in_celsius_marked_provisional():
    thermal = _statuses(PROMPT)[Block.THERMAL]

    labels = [item.label for item in thermal.values]

    assert labels == ["周回の最高温度", "周回の最低温度", "放熱能力"]
    assert thermal.values[0].text.endswith("℃（暫定）")


def test_thermal_note_says_it_is_not_a_per_unit_temperature():
    note = _statuses(PROMPT)[Block.THERMAL].note

    assert "機器ごとの温度ではありません" in note


def test_form_factor_without_a_reference_bus_waits_and_says_why():
    statuses = _statuses("高度 500 km、傾斜角 97 度の 6U 衛星")

    assert statuses[Block.MASS].state is BlockState.WAITING
    assert "3U" in statuses[Block.MASS].note
    assert statuses[Block.ORBIT].state is BlockState.DONE


def test_requirement_of_the_launch_vehicle_reaches_the_ledger():
    ledger = project_ledger(build_intake(PROMPT, {}).project)

    assert ledger.value("required_natural_frequency_hz") == 100
