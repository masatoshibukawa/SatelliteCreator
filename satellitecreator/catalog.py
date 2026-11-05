"""Stand-in equipment for a form factor, used until parts are chosen for each mission."""

from __future__ import annotations

from functools import cache

from pydantic import Field

from satellitecreator.loading import load_yaml
from satellitecreator.schema import Frozen, Sourced

_ZERO_CELSIUS_K = 273.15


class Part(Frozen):
    id: str
    group: str
    mass_g: float = Field(gt=0)


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
