import pytest

from satellitecreator.catalog import reference_bus


def test_reference_bus_is_available_for_three_units():
    bus = reference_bus("3U")

    assert bus is not None
    assert bus.source


def test_other_form_factors_have_no_reference_bus_yet():
    assert reference_bus("6U") is None


def test_part_masses_add_up_to_the_table_total_in_the_report():
    bus = reference_bus("3U")

    assert bus.parts_mass_kg == pytest.approx(3.882, abs=0.001)


def test_parts_and_margin_reproduce_the_total_mass_in_the_report():
    bus = reference_bus("3U")

    assert bus.parts_mass_kg + bus.mass_margin_kg == pytest.approx(3.985, abs=0.001)


def test_power_range_matches_the_report_table():
    bus = reference_bus("3U")

    assert bus.min_consumed_power_w == pytest.approx(1.229)
    assert bus.max_consumed_power_w == pytest.approx(12.586)


def test_allowable_temperatures_are_kept_in_kelvin():
    bus = reference_bus("3U")

    assert bus.allowable_min_temperature_k == pytest.approx(263.15)
    assert bus.allowable_max_temperature_k == pytest.approx(323.15)
