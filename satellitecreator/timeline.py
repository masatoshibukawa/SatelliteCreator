"""One day of power and communication, stepped through time.

Assumptions: circular orbit, spherical Earth, node at longitude 0, and the Sun in the orbit plane
as in the worst case of the design core. Values for one orbit come from the ledger, so the
timeline only spreads them over time.
"""

from __future__ import annotations

import math
from functools import cache

from pydantic import Field

from satellitecreator.catalog import ReferenceBus, reference_bus
from satellitecreator.core.ledger import Ledger
from satellitecreator.core.registry import load_constants
from satellitecreator.loading import load_yaml
from satellitecreator.project import Project
from satellitecreator.schema import Frozen, Sourced

STEP_S = 60
DAY_S = 86400
_COMMUNICATION_MODE = "通信"
_STANDBY_MODE = "待機"


class GroundStation(Sourced):
    name: str
    latitude_deg: float = Field(ge=-90, le=90)
    longitude_deg: float = Field(ge=-180, le=180)


class TimelineInputs(Frozen):
    earth_radius_m: float
    sidereal_day_s: float
    orbit_radius_m: float
    inclination_deg: float
    period_s: float
    eclipse_s: float
    min_elevation_deg: float
    worst_range_m: float
    worst_margin_db: float
    rate_bps: float
    sunlit_power_w: float
    average_power_w: float
    heater_power_w: float
    transmit_extra_power_w: float
    battery_capacity_j: float


class ContactWindow(Frozen):
    start_s: float
    end_s: float
    max_elevation_deg: float
    downlink_bit: float


class Timeline(Frozen):
    station: str
    time_s: tuple[float, ...]
    generated_power_w: tuple[float, ...]
    consumed_power_w: tuple[float, ...]
    battery_ratio: tuple[float, ...]
    link_margin_db: tuple[float | None, ...]
    downlinked_bit: tuple[float, ...]
    contacts: tuple[ContactWindow, ...]
    contact_s: float
    downlink_bit: float
    min_battery_ratio: float


@cache
def load_ground_station() -> GroundStation:
    return GroundStation(**load_yaml("catalog/ground_stations.yaml")["ground_station"])


def _argument_rad(inputs: TimelineInputs, time_s: float) -> float:
    return 2 * math.pi * time_s / inputs.period_s


def _in_eclipse(inputs: TimelineInputs, time_s: float) -> bool:
    """Phase 0 faces the Sun, so the eclipse is centred half an orbit later."""
    phase_s = time_s % inputs.period_s
    return abs(phase_s - inputs.period_s / 2) < inputs.eclipse_s / 2


def _look_angle(
    inputs: TimelineInputs, station: GroundStation, time_s: float
) -> tuple[float, float]:
    """Elevation in degrees and range in metres from the station to the satellite."""
    argument = _argument_rad(inputs, time_s)
    inclination = math.radians(inputs.inclination_deg)
    satellite = (
        inputs.orbit_radius_m * math.cos(argument),
        inputs.orbit_radius_m * math.sin(argument) * math.cos(inclination),
        inputs.orbit_radius_m * math.sin(argument) * math.sin(inclination),
    )
    latitude = math.radians(station.latitude_deg)
    longitude = math.radians(station.longitude_deg) + 2 * math.pi * time_s / inputs.sidereal_day_s
    zenith = (
        math.cos(latitude) * math.cos(longitude),
        math.cos(latitude) * math.sin(longitude),
        math.sin(latitude),
    )
    offset = tuple(
        position - inputs.earth_radius_m * axis
        for position, axis in zip(satellite, zenith, strict=True)
    )
    distance = math.sqrt(sum(value**2 for value in offset))
    height = sum(value * axis for value, axis in zip(offset, zenith, strict=True))
    return math.degrees(math.asin(height / distance)), distance


def _contacts(
    times: tuple[float, ...], elevations: tuple[float, ...], visible: tuple[bool, ...], rate: float
) -> tuple[ContactWindow, ...]:
    windows: list[ContactWindow] = []
    start: int | None = None
    for index, is_visible in enumerate((*visible, False)):
        if is_visible and start is None:
            start = index
        if not is_visible and start is not None:
            end_s = times[index - 1] + STEP_S
            windows.append(
                ContactWindow(
                    start_s=times[start],
                    end_s=end_s,
                    max_elevation_deg=max(elevations[start:index]),
                    downlink_bit=rate * (end_s - times[start]),
                )
            )
            start = None
    return tuple(windows)


def build_timeline(inputs: TimelineInputs, station: GroundStation) -> Timeline:
    times = tuple(float(value) for value in range(0, DAY_S, STEP_S))
    looks = tuple(_look_angle(inputs, station, value) for value in times)
    elevations = tuple(item[0] for item in looks)
    visible = tuple(value >= inputs.min_elevation_deg for value in elevations)
    margins = tuple(
        inputs.worst_margin_db + 20 * math.log10(inputs.worst_range_m / item[1])
        if is_visible
        else None
        for item, is_visible in zip(looks, visible, strict=True)
    )
    contacts = _contacts(times, elevations, visible, inputs.rate_bps)
    contact_s = sum(item.end_s - item.start_s for item in contacts)
    # The orbit average already holds the transmitter, so moving it into the contacts keeps the
    # daily mean equal to the design core's value.
    idle_power_w = inputs.average_power_w - inputs.transmit_extra_power_w * contact_s / DAY_S

    generated: list[float] = []
    consumed: list[float] = []
    battery: list[float] = []
    downlinked: list[float] = []
    stored_j = inputs.battery_capacity_j
    sent_bit = 0.0
    for time_s, is_visible in zip(times, visible, strict=True):
        eclipse = _in_eclipse(inputs, time_s)
        power_in = 0.0 if eclipse else inputs.sunlit_power_w
        power_out = (
            idle_power_w
            + (inputs.heater_power_w if eclipse else 0.0)
            + (inputs.transmit_extra_power_w if is_visible else 0.0)
        )
        stored_j = min(stored_j + (power_in - power_out) * STEP_S, inputs.battery_capacity_j)
        stored_j = max(stored_j, 0.0)
        sent_bit += inputs.rate_bps * STEP_S if is_visible else 0.0
        generated.append(power_in)
        consumed.append(power_out)
        battery.append(stored_j / inputs.battery_capacity_j)
        downlinked.append(sent_bit)
    return Timeline(
        station=station.name,
        time_s=times,
        generated_power_w=tuple(generated),
        consumed_power_w=tuple(consumed),
        battery_ratio=tuple(battery),
        link_margin_db=margins,
        downlinked_bit=tuple(downlinked),
        contacts=contacts,
        contact_s=contact_s,
        downlink_bit=sent_bit,
        min_battery_ratio=min(battery),
    )


def _transmit_extra_power_w(bus: ReferenceBus) -> float:
    """The current a contact adds to standby, taken from the bus's own power modes."""
    standby = next(item for item in bus.modes if item.name == _STANDBY_MODE)
    contact = next(item for item in bus.modes if _COMMUNICATION_MODE in item.name)
    return (contact.current_ma - standby.current_ma) / 1000 * bus.battery_voltage_v


def timeline_inputs(ledger: Ledger, bus: ReferenceBus) -> TimelineInputs | None:
    names = {
        "orbit_radius_m": "orbit_radius_m",
        "inclination_deg": "inclination_deg",
        "period_s": "orbit_period_s",
        "eclipse_s": "max_eclipse_s",
        "min_elevation_deg": "min_elevation_deg",
        "worst_range_m": "slant_range_m",
        "worst_margin_db": "link_margin_db",
        "rate_bps": "downlink_rate_bps",
        "sunlit_power_w": "usable_sunlit_power_w",
        "average_power_w": "average_consumed_power_w",
        "heater_power_w": "heater_power_w",
        "battery_capacity_j": "battery_capacity_j",
    }
    entries = {field: ledger.get(name) for field, name in names.items()}
    if any(entry is None for entry in entries.values()):
        return None
    constants = {item.key: item.value for item in load_constants()}
    return TimelineInputs(
        earth_radius_m=constants["earth_radius_m"],
        sidereal_day_s=constants["earth_sidereal_day_s"],
        transmit_extra_power_w=_transmit_extra_power_w(bus),
        **{field: entry.value for field, entry in entries.items()},
    )


def project_timeline(project: Project, ledger: Ledger) -> Timeline | None:
    bus = reference_bus(project.design.form_factor) if project.design else None
    inputs = timeline_inputs(ledger, bus) if bus else None
    return build_timeline(inputs, load_ground_station()) if inputs else None
