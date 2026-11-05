import math

import pytest
from pydantic import ValidationError

from satellitecreator.core import checks as checks_module
from satellitecreator.core import ledger as ledger_module
from satellitecreator.core.checks import CheckState, evaluate_checks
from satellitecreator.core.formulas import FORMULAS
from satellitecreator.core.ledger import Ledger, LedgerEntry, Origin, solve
from satellitecreator.core.registry import (
    Block,
    CheckSpec,
    Constant,
    Equation,
    InputSpec,
    load_checks,
    load_constants,
    load_equations,
    load_inputs,
    validate_checks,
    validate_equations,
)
from satellitecreator.requirements import Comparator
from satellitecreator.schema import UNIT_SUFFIXES

SOURCE = "https://example.com/doc.pdf"


def _equation(**overrides) -> Equation:
    fields = {
        "output": "orbit_radius_m",
        "label": "軌道半径",
        "formula": "r = R + h",
        "inputs": ("altitude_m", "earth_radius_m"),
        "block": Block.ORBIT,
        "source": SOURCE,
    }
    return Equation(**{**fields, **overrides})


def test_every_constant_and_equation_has_a_source():
    assert all(item.source or item.provisional for item in load_constants())
    assert all(item.source or item.provisional for item in load_equations())


def test_every_check_has_a_source():
    assert all(item.source or item.provisional for item in load_checks())


def test_every_quantity_key_has_a_unit_suffix():
    keys = [item.key for item in load_constants()] + [item.output for item in load_equations()]

    assert all(key.endswith(UNIT_SUFFIXES) for key in keys)


def test_each_equation_has_a_formula_function_with_matching_inputs():
    assert validate_equations(load_equations(), FORMULAS, load_constants(), load_inputs()) is None


def test_two_equations_for_one_quantity_are_rejected():
    equations = (_equation(), _equation(formula="r = h + R"))

    with pytest.raises(ValueError, match="one place"):
        validate_equations(equations, FORMULAS, load_constants(), load_inputs())


def test_equation_without_a_function_is_rejected():
    equations = (_equation(output="no_such_quantity_m"),)

    with pytest.raises(ValueError, match="no formula function"):
        validate_equations(equations, FORMULAS, load_constants(), load_inputs())


def test_equation_whose_inputs_differ_from_its_function_is_rejected():
    equations = (_equation(inputs=("altitude_m",)),)

    with pytest.raises(ValueError, match="inputs"):
        validate_equations(equations, FORMULAS, load_constants(), load_inputs())


def test_equation_that_redefines_a_constant_is_rejected():
    equations = (_equation(output="earth_radius_m"),)

    with pytest.raises(ValueError, match="one place"):
        validate_equations(
            equations, {**FORMULAS, "earth_radius_m": lambda: 1.0}, load_constants(), load_inputs()
        )


def test_equation_that_redefines_an_input_is_rejected():
    inputs = (*load_inputs(), InputSpec(key="orbit_radius_m", label="軌道半径"))

    with pytest.raises(ValueError, match="one place"):
        validate_equations((_equation(),), FORMULAS, load_constants(), inputs)


def test_input_listed_twice_is_rejected():
    inputs = (*load_inputs(), load_inputs()[0])

    with pytest.raises(ValueError, match="one place"):
        validate_equations((), FORMULAS, load_constants(), inputs)


def test_planned_quantity_that_an_equation_already_produces_is_rejected():
    with pytest.raises(ValueError, match="one place"):
        validate_equations(
            (_equation(),), FORMULAS, load_constants(), load_inputs(), ("orbit_radius_m",)
        )


def test_equation_reading_an_unknown_quantity_is_rejected():
    def typo_output_m(altitud_m: float) -> float:
        return altitud_m

    equation = _equation(output="typo_output_m", inputs=("altitud_m",))

    with pytest.raises(ValueError, match="unknown quantity"):
        validate_equations(
            (equation,), {"typo_output_m": typo_output_m}, load_constants(), load_inputs()
        )


def test_circular_equations_are_rejected():
    def first_m(second_m: float) -> float:
        return second_m

    def second_m(first_m: float) -> float:
        return first_m

    equations = (
        _equation(output="first_m", inputs=("second_m",)),
        _equation(output="second_m", inputs=("first_m",)),
    )
    formulas = {"first_m": first_m, "second_m": second_m}

    with pytest.raises(ValueError, match="cycle"):
        validate_equations(equations, formulas, load_constants(), load_inputs())


def test_check_naming_an_unknown_quantity_is_rejected():
    spec = CheckSpec(
        id="typo",
        label="typo",
        block=Block.MASS,
        left="total_mas_kg",
        comparator=Comparator.AT_MOST,
        right_value=1.0,
        source=SOURCE,
    )

    with pytest.raises(ValueError, match="unknown quantity"):
        validate_checks((spec,), frozenset({"total_mass_kg"}))


def test_orbit_period_follows_keplers_third_law():
    ledger = solve({"altitude_m": 400e3})

    radius_m = 6378137.0 + 400e3
    expected = 2 * math.pi * math.sqrt(radius_m**3 / 3.9860e14)

    assert ledger.value("orbit_period_s") == pytest.approx(expected)


def test_maximum_eclipse_matches_the_nasa_derivation_at_zero_beta():
    ledger = solve({"altitude_m": 400e3})

    radius_ratio = 6378137.0 / (6378137.0 + 400e3)
    entry_angle_rad = math.pi - math.asin(radius_ratio)
    expected = 2 * (math.pi - entry_angle_rad) / (2 * math.pi)

    assert ledger.value("max_eclipse_fraction_ratio") == pytest.approx(expected)


def test_eclipse_and_sunlight_add_up_to_the_period():
    ledger = solve({"altitude_m": 550e3})

    total = ledger.value("max_eclipse_s") + ledger.value("min_sunlight_s")

    assert total == pytest.approx(ledger.value("orbit_period_s"))


def test_higher_orbit_has_a_longer_period_and_a_smaller_eclipse_fraction():
    low = solve({"altitude_m": 300e3})
    high = solve({"altitude_m": 800e3})

    assert high.value("orbit_period_s") > low.value("orbit_period_s")
    assert high.value("max_eclipse_fraction_ratio") < low.value("max_eclipse_fraction_ratio")


def test_ledger_entry_records_how_the_value_was_made():
    entry = solve({"altitude_m": 400e3}).get("orbit_period_s")

    assert entry.origin is Origin.EQUATION
    assert entry.formula
    assert entry.inputs == ("orbit_radius_m", "earth_mu_m3s2")
    assert entry.source


def test_shared_quantity_is_a_single_ledger_entry():
    keys = [item.key for item in solve({"altitude_m": 400e3}).entries]

    assert len(keys) == len(set(keys))


def test_quantities_without_inputs_are_reported_missing():
    ledger = solve({})

    assert ledger.value("orbit_period_s") is None
    assert "orbit_period_s" in ledger.missing


def test_unknown_input_is_rejected():
    with pytest.raises(ValueError, match="unknown input"):
        solve({"no_such_input_m": 1.0})


def test_input_cannot_overwrite_a_calculated_quantity():
    with pytest.raises(ValueError, match="unknown input"):
        solve({"orbit_period_s": 1.0})


def test_provisional_input_is_marked_and_passed_on():
    ledger = solve({"parts_mass_kg": 3.9, "mass_margin_kg": 0.1}, provisional={"parts_mass_kg"})

    assert ledger.get("parts_mass_kg").provisional
    assert not ledger.get("mass_margin_kg").provisional
    assert ledger.get("total_mass_kg").provisional


def test_input_must_be_finite():
    with pytest.raises(ValueError, match="finite"):
        solve({"altitude_m": math.inf})


def test_solve_is_deterministic():
    assert solve({"altitude_m": 400e3}) == solve({"altitude_m": 400e3})


def _check_state(check_id: str, ledger) -> CheckState:
    results = {item.id: item for item in evaluate_checks(ledger)}
    return results[check_id].state


def test_check_without_its_quantities_has_not_run():
    ledger = solve({"altitude_m": 400e3, "max_mass_kg": 4.5})

    assert _check_state("mass_within_limit", ledger) is CheckState.NOT_RUN


def test_not_run_check_names_what_is_missing():
    ledger = solve({"altitude_m": 400e3})

    result = next(item for item in evaluate_checks(ledger) if item.id == "mass_within_limit")

    assert "total_mass_kg" in result.missing


def test_check_passes_and_fails_on_the_ledger_values():
    passing = solve({"max_mass_kg": 4.5, "parts_mass_kg": 3.9, "mass_margin_kg": 0.1})
    failing = solve({"max_mass_kg": 4.5, "parts_mass_kg": 4.9, "mass_margin_kg": 0.1})

    assert _check_state("mass_within_limit", passing) is CheckState.PASSED
    assert _check_state("mass_within_limit", failing) is CheckState.FAILED


def _ledger_with(**values: float) -> Ledger:
    entries = tuple(
        LedgerEntry(key=key, label=key, value=value, origin=Origin.INPUT)
        for key, value in values.items()
    )
    return Ledger(entries=entries)


def test_link_margin_of_exactly_zero_passes_as_the_standard_allows():
    assert _check_state("link_margin_positive", _ledger_with(link_margin_db=0.0)) is (
        CheckState.PASSED
    )


def test_negative_link_margin_fails():
    assert _check_state("link_margin_positive", _ledger_with(link_margin_db=-0.1)) is (
        CheckState.FAILED
    )


def test_equality_check_compares_within_rounding(monkeypatch):
    spec = CheckSpec(
        id="same",
        label="same",
        block=Block.MASS,
        left="a_kg",
        comparator=Comparator.EQUAL,
        right="b_kg",
        source=SOURCE,
    )
    monkeypatch.setattr(checks_module, "load_checks", lambda: (spec,))

    assert _check_state("same", _ledger_with(a_kg=1.0, b_kg=1.0 + 1e-12)) is CheckState.PASSED
    assert _check_state("same", _ledger_with(a_kg=1.0, b_kg=1.1)) is CheckState.FAILED


def test_provisional_check_says_so_in_its_result():
    results = {item.id: item for item in evaluate_checks(_ledger_with())}

    assert results["orbit_lifetime_covers_mission"].provisional
    assert not results["link_margin_positive"].provisional


def test_check_that_reads_a_stand_in_value_is_marked_provisional():
    ledger = solve(
        {"max_mass_kg": 4.5, "parts_mass_kg": 3.9, "mass_margin_kg": 0.1},
        provisional={"parts_mass_kg"},
    )

    result = next(item for item in evaluate_checks(ledger) if item.id == "mass_within_limit")

    assert result.state is CheckState.PASSED
    assert result.provisional


def test_check_on_firm_values_is_not_marked_provisional():
    ledger = solve({"max_mass_kg": 4.5, "parts_mass_kg": 3.9, "mass_margin_kg": 0.1})

    result = next(item for item in evaluate_checks(ledger) if item.id == "mass_within_limit")

    assert not result.provisional


def test_check_needs_exactly_one_right_side():
    fields = {
        "id": "x",
        "label": "x",
        "block": Block.MASS,
        "left": "total_mass_kg",
        "comparator": Comparator.AT_MOST,
        "source": SOURCE,
    }

    with pytest.raises(ValidationError, match="exactly one"):
        CheckSpec(**fields)
    with pytest.raises(ValidationError, match="exactly one"):
        CheckSpec(**fields, right="max_mass_kg", right_value=1.0)


def test_formula_that_returns_a_non_finite_value_is_rejected(monkeypatch):
    monkeypatch.setitem(FORMULAS, "orbit_radius_m", lambda altitude_m, earth_radius_m: math.nan)

    with pytest.raises(ValueError, match="not finite"):
        solve({"altitude_m": 400e3})


def test_provisional_input_marks_every_value_derived_from_it(monkeypatch):
    provisional_radius = Constant(
        key="earth_radius_m", label="地球半径", value=6378137.0, provisional=True
    )
    others = tuple(item for item in load_constants() if item.key != "earth_radius_m")
    monkeypatch.setattr(ledger_module, "load_constants", lambda: (provisional_radius, *others))

    ledger = solve({"altitude_m": 400e3})

    assert ledger.get("orbit_radius_m").provisional
    assert ledger.get("orbit_period_s").provisional


def test_check_against_a_fixed_threshold_comes_from_the_standard():
    spec = next(item for item in load_checks() if item.id == "link_margin_positive")

    assert spec.comparator is Comparator.AT_LEAST
    assert spec.right_value == 0
    assert "JERG-2-420" in spec.source
