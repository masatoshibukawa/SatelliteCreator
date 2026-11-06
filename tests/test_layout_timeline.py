import pytest

from satellitecreator.catalog import load_reference_buses, reference_bus
from satellitecreator.core.checks import CheckState, evaluate_checks
from satellitecreator.document import build_document
from satellitecreator.intake import build_intake
from satellitecreator.layout import build_layout, load_layout
from satellitecreator.session import run_session
from satellitecreator.simulation import project_ledger
from satellitecreator.timeline import (
    DAY_S,
    GroundStation,
    TimelineInputs,
    build_timeline,
    load_ground_station,
)

ONE_UNIT = "高度 500 km、軌道傾斜角 97.5 度の 1U CubeSat で地球を撮影したい"
THREE_UNIT = "高度 500 km、軌道傾斜角 97.5 度の 3U CubeSat で光通信を実証したい"
STATION = GroundStation(name="test", latitude_deg=38.0, longitude_deg=140.0, provisional=True)


def _design(prompt, equipment=()):
    return build_intake(prompt, {}, equipment=equipment).project.design


def _inputs(**changes):
    values = {
        "earth_radius_m": 6378137.0,
        "sidereal_day_s": 86164.2,
        "orbit_radius_m": 6878137.0,
        "inclination_deg": 97.5,
        "period_s": 5676.0,
        "eclipse_s": 2148.0,
        "min_elevation_deg": 5.0,
        "worst_range_m": 2078e3,
        "worst_margin_db": 2.2,
        "rate_bps": 9600.0,
        "sunlit_power_w": 3.0,
        "average_power_w": 1.2,
        "heater_power_w": 0.0,
        "transmit_extra_power_w": 0.0,
        "battery_capacity_j": 56000.0,
    }
    return TimelineInputs(**{**values, **changes})


def test_catalog_names_every_part_of_every_bus_that_it_places():
    catalog = load_layout()

    for bus in load_reference_buses():
        part_ids = {item.id for item in bus.parts}
        placed = (*catalog.stacks[bus.form_factor], *catalog.external[bus.form_factor])
        assert set(placed) <= part_ids


def test_default_equipment_fits_inside_each_bus():
    for bus, prompt in zip(load_reference_buses(), (THREE_UNIT, ONE_UNIT), strict=True):
        layout = build_layout(_design(prompt), bus)

        assert layout.fits
        assert layout.stack_height_mm > 0


def test_three_unit_order_runs_from_bus_units_to_the_mission_part():
    layout = build_layout(_design(THREE_UNIT), reference_bus("3U"))

    stack = [item.id for item in layout.items if not item.external]

    assert stack.index("ABU") < stack.index("ACU") < stack.index("MOT")


def test_stacked_items_do_not_overlap():
    layout = build_layout(_design(ONE_UNIT), reference_bus("1U"))

    stack = [item for item in layout.items if not item.external]

    for upper, lower in zip(stack, stack[1:], strict=False):
        bottom = upper.center_mm[2] - upper.size_mm[2] / 2
        assert bottom == pytest.approx(lower.center_mm[2] + lower.size_mm[2] / 2)


def test_every_item_says_what_it_is():
    layout = build_layout(_design(THREE_UNIT), reference_bus("3U"))

    assert all(item.label and item.role for item in layout.items)


def test_a_chosen_payload_replaces_the_payload_parts():
    design = _design(ONE_UNIT, ("atmosphere_sensor",))

    layout = build_layout(design, reference_bus("1U"))

    ids = [item.id for item in layout.items]
    assert "atmosphere_sensor" in ids
    assert "camera" not in ids
    chosen = next(item for item in layout.items if item.id == "atmosphere_sensor")
    assert chosen.label == "大気センサ"
    assert chosen.mass_g == 150


def test_chosen_solar_panels_stay_outside_and_keep_the_battery():
    layout = build_layout(_design(ONE_UNIT, ("deployed_panels",)), reference_bus("1U"))

    items = {item.id: item for item in layout.items}
    assert items["deployed_panels"].external
    assert not items["batteries"].external


def test_equipment_that_does_not_fit_fails_the_check():
    project = build_intake(ONE_UNIT, {}, equipment=("camera_large",)).project

    checks = {item.id: item for item in evaluate_checks(project_ledger(project))}

    assert checks["equipment_fits_inside"].state is CheckState.FAILED


def test_default_equipment_passes_the_fit_check():
    project = build_intake(ONE_UNIT, {}).project

    checks = {item.id: item for item in evaluate_checks(project_ledger(project))}

    assert checks["equipment_fits_inside"].state is CheckState.PASSED


def test_battery_low_point_matches_the_depth_of_discharge_without_a_contact_load():
    inputs = _inputs()

    timeline = build_timeline(inputs, STATION)

    depth = inputs.average_power_w * inputs.eclipse_s / inputs.battery_capacity_j
    assert timeline.min_battery_ratio == pytest.approx(1 - depth, abs=0.005)


def test_generated_power_is_zero_for_the_eclipse_share_of_the_day():
    inputs = _inputs()

    timeline = build_timeline(inputs, STATION)

    dark = sum(value == 0 for value in timeline.generated_power_w) / len(timeline.time_s)
    assert dark == pytest.approx(inputs.eclipse_s / inputs.period_s, abs=0.01)


def test_moving_the_transmitter_into_contacts_keeps_the_daily_mean():
    inputs = _inputs(transmit_extra_power_w=2.0)

    timeline = build_timeline(inputs, STATION)

    mean = sum(timeline.consumed_power_w) / len(timeline.consumed_power_w)
    assert mean == pytest.approx(inputs.average_power_w, rel=1e-9)


def test_polar_orbit_sees_a_mid_latitude_station_several_times_a_day():
    timeline = build_timeline(_inputs(), STATION)

    assert 2 <= len(timeline.contacts) <= 8
    assert all(0 < item.end_s - item.start_s <= 900 for item in timeline.contacts)
    assert all(item.max_elevation_deg >= 5 for item in timeline.contacts)


def test_downlink_is_rate_times_contact_time():
    timeline = build_timeline(_inputs(), STATION)

    assert timeline.downlink_bit == pytest.approx(9600 * timeline.contact_s)
    assert timeline.downlinked_bit[-1] == timeline.downlink_bit


def test_equatorial_orbit_never_sees_a_high_latitude_station():
    station = GroundStation(name="north", latitude_deg=70.0, longitude_deg=0.0, provisional=True)

    timeline = build_timeline(_inputs(inclination_deg=0.0), station)

    assert timeline.contacts == ()
    assert timeline.downlink_bit == 0


def test_margin_is_never_below_the_worst_case_during_a_contact():
    timeline = build_timeline(_inputs(), STATION)

    margins = [value for value in timeline.link_margin_db if value is not None]

    assert min(margins) >= 2.2 - 1e-6
    assert max(margins) > 2.2


def test_timeline_is_deterministic():
    assert build_timeline(_inputs(), STATION) == build_timeline(_inputs(), STATION)


def test_session_carries_layout_and_a_full_day_timeline():
    result = run_session(ONE_UNIT, {})

    assert result.layout_fits
    assert any(item.id == "batteries" for item in result.layout.items)
    assert result.timeline.time_s[-1] < DAY_S
    assert result.timeline.station == load_ground_station().name


def test_session_has_no_layout_or_timeline_without_a_bus():
    result = run_session("高度 500 km、傾斜角 97 度の 6U 衛星", {})

    assert result.layout is None
    assert result.timeline is None


def test_document_reports_the_contact_time():
    document = build_document(build_intake(ONE_UNIT, {}).project)

    section = next(item for item in document.sections if item.number == "5.4")

    assert any("1 日のダウンリンク量" in line for line in section.lines)
