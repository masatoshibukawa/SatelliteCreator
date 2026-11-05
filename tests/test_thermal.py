import pytest

from satellitecreator.core.formulas import (
    max_beta_deg,
    max_eclipse_fraction_ratio,
    min_eclipse_fraction_ratio,
    orbit_max_temperature_k,
    orbit_min_temperature_k,
)
from satellitecreator.core.ledger import solve

SIGMA = 5.670374419e-8
EARTH_RADIUS_M = 6378137.0
THREE_U = {
    "altitude_m": 400e3,
    "inclination_deg": 51.6,
    "envelope_width_m": 0.1,
    "envelope_depth_m": 0.1,
    "envelope_length_m": 0.3405,
    "surface_absorptivity_ratio": 0.92,
    "surface_emissivity_ratio": 0.80,
    "parts_mass_kg": 3.882,
    "mass_margin_kg": 0.103,
    "max_consumed_power_w": 12.586,
    "min_consumed_power_w": 1.229,
    "allowable_max_temperature_k": 323.15,
    "allowable_min_temperature_k": 263.15,
}


def _heat_inputs(**overrides):
    fields = {
        "sun_absorbed_w": 50.0,
        "albedo_high_absorbed_w": 26.0,
        "albedo_low_absorbed_w": 13.0,
        "earth_ir_high_absorbed_w": 11.0,
        "earth_ir_low_absorbed_w": 8.0,
        "surface_emissivity_ratio": 0.8,
        "surface_area_m2": 0.156,
        "stefan_boltzmann_wm2k4": SIGMA,
        "thermal_capacity_jpk": 3600.0,
        "orbit_period_s": 5550.0,
    }
    return {**fields, **overrides}


def _hot(power_w: float = 5.0, beta_deg: float = 60.0, eclipse_s: float = 1500.0, **overrides):
    return orbit_max_temperature_k(
        max_beta_deg=beta_deg,
        max_consumed_power_w=power_w,
        min_eclipse_s=eclipse_s,
        **_heat_inputs(**overrides),
    )


def _cold(power_w: float = 5.0, eclipse_s: float = 2170.0, **overrides):
    return orbit_min_temperature_k(
        min_consumed_power_w=power_w, max_eclipse_s=eclipse_s, **_heat_inputs(**overrides)
    )


def test_surface_area_of_a_three_unit_box():
    assert solve(THREE_U).value("surface_area_m2") == pytest.approx(0.1562)


@pytest.mark.parametrize(
    ("inclination_deg", "expected"),
    [(0.0, 23.45), (51.6, 75.05), (97.5, 90.0), (120.0, 83.45), (180.0, 23.45)],
)
def test_largest_beta_angle_follows_inclination_and_obliquity(inclination_deg, expected):
    assert max_beta_deg(inclination_deg, 23.45) == pytest.approx(expected)


def test_eclipse_at_zero_beta_equals_the_maximum_eclipse():
    radius_m = EARTH_RADIUS_M + 400e3

    assert min_eclipse_fraction_ratio(EARTH_RADIUS_M, radius_m, 0.0) == pytest.approx(
        max_eclipse_fraction_ratio(EARTH_RADIUS_M, radius_m)
    )


def test_orbit_above_the_critical_beta_has_no_eclipse():
    assert min_eclipse_fraction_ratio(EARTH_RADIUS_M, EARTH_RADIUS_M + 400e3, 75.0) == 0.0


def test_equatorial_orbit_never_escapes_eclipse():
    ledger = solve({**THREE_U, "inclination_deg": 0.0})

    assert ledger.value("min_eclipse_s") > 0


def test_iss_like_orbit_has_eclipse_free_periods():
    assert solve(THREE_U).value("min_eclipse_s") == 0.0


def test_without_eclipse_the_temperature_settles_at_the_radiative_balance():
    expected = ((50.0 + 11.0 + 5.0) / (0.8 * SIGMA * 0.156)) ** 0.25

    assert _hot(beta_deg=90.0, eclipse_s=0.0) == pytest.approx(expected, abs=0.01)


def test_hot_case_is_warmer_with_less_eclipse():
    assert _hot(eclipse_s=0.0) > _hot(eclipse_s=2000.0)


def test_hot_case_takes_the_warmer_of_the_paired_environment_tolerances():
    albedo_dominant = _hot(beta_deg=0.0, albedo_high_absorbed_w=80.0)
    infrared_dominant = _hot(beta_deg=90.0, earth_ir_high_absorbed_w=40.0)

    assert albedo_dominant > _hot(beta_deg=0.0)
    assert infrared_dominant > _hot(beta_deg=90.0)


def test_high_albedo_is_never_paired_with_high_infrared():
    expected = ((50.0 + 11.0 + 5.0) / (0.8 * SIGMA * 0.156)) ** 0.25

    paired = _hot(beta_deg=90.0, eclipse_s=0.0, albedo_high_absorbed_w=11.0)

    assert paired == pytest.approx(expected, abs=0.01)


def test_cold_case_is_colder_than_the_hot_case():
    assert _cold(power_w=1.0) < _hot(power_w=12.0)


def test_cold_case_gets_colder_with_more_eclipse():
    assert _cold(eclipse_s=2500.0) < _cold(eclipse_s=1500.0)


def test_more_internal_power_raises_the_temperature():
    assert _hot(power_w=12.0) > _hot(power_w=1.0)
    assert _cold(power_w=12.0) > _cold(power_w=1.0)


def test_larger_thermal_capacity_narrows_the_cold_excursion():
    assert _cold(thermal_capacity_jpk=9000.0) > _cold(thermal_capacity_jpk=1000.0)


def test_temperature_calculation_is_deterministic():
    assert solve(THREE_U) == solve(THREE_U)


def test_smaller_satellite_can_radiate_less_heat():
    one_unit = {**THREE_U, "envelope_length_m": 0.1135}

    small = solve(one_unit).value("max_radiated_power_w")
    large = solve(THREE_U).value("max_radiated_power_w")

    assert small < large


def test_radiating_capacity_follows_the_stefan_boltzmann_law():
    ledger = solve(THREE_U)

    expected = 0.80 * SIGMA * ledger.value("surface_area_m2") * 323.15**4

    assert ledger.value("max_radiated_power_w") == pytest.approx(expected)


def test_margin_is_the_smaller_of_the_hot_and_cold_margins():
    ledger = solve(THREE_U)

    hot = 323.15 - ledger.value("orbit_max_temperature_k")
    cold = ledger.value("orbit_min_temperature_k") - 263.15

    assert ledger.value("temperature_margin_k") == pytest.approx(min(hot, cold))


def test_thermal_results_are_provisional():
    ledger = solve(THREE_U)

    assert ledger.get("orbit_max_temperature_k").provisional
