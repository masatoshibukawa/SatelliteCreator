import pytest
from pydantic import ValidationError

from satellitecreator.design import (
    Orbit,
    SatelliteDesign,
    check_scope,
    envelope,
    form_factor,
    load_scope_limits,
)


def _design(form_factor_id: str = "3U", altitude_m: float = 400e3) -> SatelliteDesign:
    return SatelliteDesign(
        form_factor=form_factor_id,
        orbit=Orbit(altitude_m=altitude_m, inclination_deg=51.6),
    )


@pytest.mark.parametrize(
    ("form_factor_id", "max_mass_kg"),
    [("1U", 1.5), ("2U", 3.0), ("3U", 4.5), ("6U", 9.0)],
)
def test_form_factor_mass_limits_match_the_contest_rules(form_factor_id, max_mass_kg):
    assert form_factor(form_factor_id).max_mass_kg == max_mass_kg


def test_unknown_form_factor_lookup_raises():
    with pytest.raises(KeyError):
        form_factor("12U")


@pytest.mark.parametrize(
    ("form_factor_id", "size_m"),
    [
        ("1U", (0.1, 0.1, 0.1135)),
        ("2U", (0.1, 0.1, 0.227)),
        ("3U", (0.1, 0.1, 0.3405)),
        ("6U", (0.2263, 0.1, 0.366)),
    ],
)
def test_envelopes_match_the_cubesat_design_specification(form_factor_id, size_m):
    item = envelope(form_factor_id)

    assert (item.width_m, item.depth_m, item.length_m) == size_m


def test_unknown_envelope_lookup_raises():
    with pytest.raises(KeyError):
        envelope("12U")


def test_scope_limits_are_all_sourced():
    limits = load_scope_limits()

    assert all(item.source for item in limits.form_factors)
    assert all(item.source for item in limits.envelopes)
    assert limits.leo_max_altitude.source
    assert limits.leo_max_altitude.value_m == 2_000_000


@pytest.mark.parametrize("altitude_m", [0.0, -1.0])
def test_orbit_rejects_non_positive_altitude(altitude_m):
    with pytest.raises(ValidationError):
        Orbit(altitude_m=altitude_m, inclination_deg=51.6)


@pytest.mark.parametrize("inclination_deg", [-0.1, 180.1])
def test_orbit_rejects_inclination_out_of_range(inclination_deg):
    with pytest.raises(ValidationError):
        Orbit(altitude_m=400e3, inclination_deg=inclination_deg)


def test_design_within_scope_has_no_findings():
    assert check_scope(_design()) == ()


def test_altitude_exactly_at_the_leo_limit_is_in_scope():
    assert check_scope(_design(altitude_m=2_000_000)) == ()


def test_altitude_above_leo_is_out_of_scope():
    assert [item.code for item in check_scope(_design(altitude_m=2_000_001))] == [
        "altitude_out_of_scope"
    ]


def test_unsupported_form_factor_is_out_of_scope():
    assert [item.code for item in check_scope(_design(form_factor_id="12U"))] == [
        "form_factor_out_of_scope"
    ]
