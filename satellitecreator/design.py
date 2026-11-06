"""Satellite design models and the check that a design is within the project scope."""

from __future__ import annotations

from functools import cache
from typing import Literal

from pydantic import Field

from satellitecreator.loading import load_yaml
from satellitecreator.schema import Finding, Frozen, Sourced


class FormFactor(Sourced):
    id: str = Field(pattern=r"^\d+U$")
    max_mass_kg: float = Field(gt=0)


class Envelope(Sourced):
    """Launch envelope along the CubeSat X, Y and Z axes. Z is the rail direction."""

    id: str = Field(pattern=r"^\d+U$")
    width_m: float = Field(gt=0)
    depth_m: float = Field(gt=0)
    length_m: float = Field(gt=0)


class AltitudeLimit(Sourced):
    value_m: float = Field(gt=0)


class ScopeLimits(Frozen):
    form_factors: tuple[FormFactor, ...]
    envelopes: tuple[Envelope, ...]
    leo_min_altitude: AltitudeLimit
    leo_max_altitude: AltitudeLimit


class LaunchVehicle(Sourced):
    """The baseline launcher until RocketCreater can supply these conditions itself."""

    name: str
    longitudinal_frequency_hz: float = Field(gt=0)
    lateral_frequency_hz: float = Field(gt=0)


class Orbit(Frozen):
    altitude_m: float = Field(gt=0, allow_inf_nan=False)
    inclination_deg: float = Field(ge=0, le=180)


class SatelliteDesign(Frozen):
    form_factor: str
    orbit: Orbit
    surface: str | None = None
    radiator_ratio: float = Field(default=1.0, gt=0, le=1)
    heater_power_w: float = Field(default=0.0, ge=0)
    peak_power_w: float | None = Field(default=None, gt=0)
    mission_duration_s: float | None = Field(default=None, gt=0)
    attitude: Literal["free_rotation", "sun_pointing"] = "free_rotation"


@cache
def load_scope_limits() -> ScopeLimits:
    return ScopeLimits(**load_yaml("constraints/scope.yaml"))


@cache
def load_launch_vehicle() -> LaunchVehicle:
    return LaunchVehicle(**load_yaml("constraints/launch_vehicle.yaml"))


def form_factor(form_factor_id: str) -> FormFactor:
    for item in load_scope_limits().form_factors:
        if item.id == form_factor_id:
            return item
    raise KeyError(form_factor_id)


def envelope(form_factor_id: str) -> Envelope:
    for item in load_scope_limits().envelopes:
        if item.id == form_factor_id:
            return item
    raise KeyError(form_factor_id)


def check_scope(design: SatelliteDesign) -> tuple[Finding, ...]:
    limits = load_scope_limits()
    findings: tuple[Finding, ...] = ()
    if design.form_factor not in {item.id for item in limits.form_factors}:
        findings += (
            Finding(
                code="form_factor_out_of_scope",
                message=f"対応していない形状です: {design.form_factor}",
                subject=design.form_factor,
            ),
        )
    if design.orbit.altitude_m < limits.leo_min_altitude.value_m:
        findings += (
            Finding(
                code="altitude_below_scope",
                message=f"高度が下限より低いです: 高度 {design.orbit.altitude_m / 1000:g} km",
            ),
        )
    if design.orbit.altitude_m > limits.leo_max_altitude.value_m:
        findings += (
            Finding(
                code="altitude_out_of_scope",
                message=f"地球低軌道の範囲外です: 高度 {design.orbit.altitude_m / 1000:g} km",
            ),
        )
    return findings
