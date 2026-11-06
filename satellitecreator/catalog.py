"""Stand-in equipment for a form factor, used until parts are chosen for each mission."""

from __future__ import annotations

from functools import cache

from pydantic import Field

from satellitecreator.loading import load_yaml
from satellitecreator.schema import Frozen, Sourced

_ZERO_CELSIUS_K = 273.15
_SECONDS_PER_HOUR = 3600
_HOURS_PER_DAY = 24


class Part(Frozen):
    id: str
    group: str
    mass_g: float = Field(gt=0)


class PowerMode(Frozen):
    name: str
    current_ma: float = Field(ge=0)
    hours: dict[str, float]


class LinkBudget(Frozen):
    frequency_hz: float = Field(gt=0)
    rate_bps: float = Field(gt=0)
    transmit_power_db: float
    transmit_feed_loss_db: float
    transmit_antenna_gain_db: float
    pointing_loss_db: float
    receive_antenna_gain_db: float
    receive_feed_loss_db: float
    noise_density_db: float
    other_loss_db: float
    required_ebno_db: float
    min_elevation_deg: float


class SurfaceFinish(Sourced):
    name: str
    absorptivity: float = Field(gt=0, le=1)
    emissivity: float = Field(gt=0, le=1)


class ReferenceBus(Sourced):
    form_factor: str
    name: str
    parts: tuple[Part, ...]
    mass_margin_g: float = Field(ge=0)
    min_consumed_power_mw: float = Field(gt=0)
    max_consumed_power_mw: float = Field(gt=0)
    surface_absorptivity: float = Field(gt=0, le=1)
    surface_emissivity: float = Field(gt=0, le=1)
    allowable_min_c: float
    allowable_max_c: float
    link: LinkBudget
    battery_voltage_v: float = Field(gt=0)
    battery_capacity_mah: float = Field(gt=0)
    charge_efficiency: float = Field(gt=0, le=1)
    sunlit_power_mw: dict[str, float]
    paddle_cell_share: dict[str, float]
    optical_power_mw: float = Field(gt=0)
    optical_hours_per_day: float = Field(ge=0)
    modes: tuple[PowerMode, ...]

    @property
    def parts_mass_kg(self) -> float:
        return sum(item.mass_g for item in self.parts) / 1000

    @property
    def mass_margin_kg(self) -> float:
        return self.mass_margin_g / 1000

    @property
    def min_consumed_power_w(self) -> float:
        return self.min_consumed_power_mw / 1000

    @property
    def max_consumed_power_w(self) -> float:
        return self.max_consumed_power_mw / 1000

    @property
    def battery_capacity_j(self) -> float:
        return self.battery_voltage_v * self.battery_capacity_mah / 1000 * _SECONDS_PER_HOUR

    def daily_charge_mah(self, attitude: str) -> float:
        return sum(item.current_ma * item.hours[attitude] for item in self.modes)

    def average_consumed_power_w(self, attitude: str, peak_power_w: float | None) -> float:
        base_w = self.daily_charge_mah(attitude) * self.battery_voltage_v / 1000 / _HOURS_PER_DAY
        if peak_power_w is None:
            return base_w
        extra_w = peak_power_w - self.max_consumed_power_w
        return base_w + extra_w * self.optical_hours_per_day / _HOURS_PER_DAY

    def sunlit_generated_power_w(self, attitude: str, covered_body_ratio: float) -> float:
        """Covering part of the body removes that part of the body cells, not the paddle cells."""
        body_share = 1 - self.paddle_cell_share[attitude]
        return self.sunlit_power_mw[attitude] / 1000 * (1 - covered_body_ratio * body_share)

    @property
    def allowable_min_temperature_k(self) -> float:
        return self.allowable_min_c + _ZERO_CELSIUS_K

    @property
    def allowable_max_temperature_k(self) -> float:
        return self.allowable_max_c + _ZERO_CELSIUS_K


@cache
def load_reference_buses() -> tuple[ReferenceBus, ...]:
    data = load_yaml("catalog/reference_buses.yaml")["reference_buses"]
    return tuple(ReferenceBus(**item) for item in data)


@cache
def load_surface_finishes() -> tuple[SurfaceFinish, ...]:
    data = load_yaml("catalog/reference_buses.yaml")["surface_finishes"]
    return tuple(SurfaceFinish(**item) for item in data)


def surface_finish(name: str) -> SurfaceFinish:
    return next(item for item in load_surface_finishes() if item.name == name)


def reference_bus(form_factor_id: str) -> ReferenceBus | None:
    return next(
        (item for item in load_reference_buses() if item.form_factor == form_factor_id), None
    )
