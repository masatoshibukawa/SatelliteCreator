"""Equation implementations.

Each function is named after the quantity it produces and its parameters are named after the
quantities it reads. `data/core/equations.yaml` holds the formula text and source of each one.
"""

from __future__ import annotations

import math
from collections.abc import Callable

_THERMAL_TIME_STEP_S = 10.0
_THERMAL_MAX_ORBITS = 300
_THERMAL_PERIODIC_TOLERANCE_K = 0.001
# Mean of cos(solar zenith angle) over the sunlit half of an orbit with the Sun in its plane.
_ALBEDO_ORBIT_AVERAGE_RATIO = 2 / math.pi


def orbit_radius_m(altitude_m: float, earth_radius_m: float) -> float:
    return altitude_m + earth_radius_m


def orbit_period_s(orbit_radius_m: float, earth_mu_m3s2: float) -> float:
    return 2 * math.pi * math.sqrt(orbit_radius_m**3 / earth_mu_m3s2)


def max_eclipse_fraction_ratio(earth_radius_m: float, orbit_radius_m: float) -> float:
    return math.asin(earth_radius_m / orbit_radius_m) / math.pi


def max_eclipse_s(orbit_period_s: float, max_eclipse_fraction_ratio: float) -> float:
    return orbit_period_s * max_eclipse_fraction_ratio


def min_sunlight_s(orbit_period_s: float, max_eclipse_s: float) -> float:
    return orbit_period_s - max_eclipse_s


def max_beta_deg(inclination_deg: float, earth_obliquity_deg: float) -> float:
    prograde_inclination_deg = min(inclination_deg, 180 - inclination_deg)
    return min(90.0, prograde_inclination_deg + earth_obliquity_deg)


def min_eclipse_fraction_ratio(
    earth_radius_m: float, orbit_radius_m: float, max_beta_deg: float
) -> float:
    radius_ratio = earth_radius_m / orbit_radius_m
    beta_rad = math.radians(max_beta_deg)
    if math.sin(beta_rad) >= radius_ratio:
        return 0.0
    sine_squared = (radius_ratio**2 - math.sin(beta_rad) ** 2) / math.cos(beta_rad) ** 2
    return math.asin(math.sqrt(sine_squared)) / math.pi


def min_eclipse_s(orbit_period_s: float, min_eclipse_fraction_ratio: float) -> float:
    return orbit_period_s * min_eclipse_fraction_ratio


def total_mass_kg(parts_mass_kg: float, mass_margin_kg: float) -> float:
    return parts_mass_kg + mass_margin_kg


def surface_area_m2(
    envelope_width_m: float, envelope_depth_m: float, envelope_length_m: float
) -> float:
    return 2 * (
        envelope_width_m * envelope_depth_m
        + envelope_width_m * envelope_length_m
        + envelope_depth_m * envelope_length_m
    )


def earth_view_factor_ratio(earth_radius_m: float, orbit_radius_m: float) -> float:
    return (1 - math.sqrt(1 - (earth_radius_m / orbit_radius_m) ** 2)) / 2


def sun_absorbed_w(
    surface_absorptivity_ratio: float, solar_flux_wm2: float, surface_area_m2: float
) -> float:
    return surface_absorptivity_ratio * solar_flux_wm2 * surface_area_m2 / 4


def _albedo_absorbed_w(
    absorptivity_ratio: float,
    albedo_ratio: float,
    solar_flux_wm2: float,
    area_m2: float,
    view_factor_ratio: float,
) -> float:
    return absorptivity_ratio * albedo_ratio * solar_flux_wm2 * area_m2 * view_factor_ratio


def albedo_high_absorbed_w(
    surface_absorptivity_ratio: float,
    albedo_high_ratio: float,
    solar_flux_wm2: float,
    surface_area_m2: float,
    earth_view_factor_ratio: float,
) -> float:
    return _albedo_absorbed_w(
        surface_absorptivity_ratio,
        albedo_high_ratio,
        solar_flux_wm2,
        surface_area_m2,
        earth_view_factor_ratio,
    )


def albedo_low_absorbed_w(
    surface_absorptivity_ratio: float,
    albedo_low_ratio: float,
    solar_flux_wm2: float,
    surface_area_m2: float,
    earth_view_factor_ratio: float,
) -> float:
    return _albedo_absorbed_w(
        surface_absorptivity_ratio,
        albedo_low_ratio,
        solar_flux_wm2,
        surface_area_m2,
        earth_view_factor_ratio,
    )


def earth_ir_high_absorbed_w(
    surface_emissivity_ratio: float,
    earth_ir_high_wm2: float,
    surface_area_m2: float,
    earth_view_factor_ratio: float,
) -> float:
    return surface_emissivity_ratio * earth_ir_high_wm2 * surface_area_m2 * earth_view_factor_ratio


def earth_ir_low_absorbed_w(
    surface_emissivity_ratio: float,
    earth_ir_low_wm2: float,
    surface_area_m2: float,
    earth_view_factor_ratio: float,
) -> float:
    return surface_emissivity_ratio * earth_ir_low_wm2 * surface_area_m2 * earth_view_factor_ratio


def thermal_capacity_jpk(total_mass_kg: float, specific_heat_jpkgk: float) -> float:
    return total_mass_kg * specific_heat_jpkgk


def _orbit_temperature_range(
    sunlit_heat_w: float,
    eclipse_heat_w: float,
    radiation_coefficient_wk4: float,
    capacity_jpk: float,
    period_s: float,
    eclipse_s: float,
) -> tuple[float, float]:
    """Steps one node around the orbit until the temperature repeats each orbit."""
    steps = max(1, round(period_s / _THERMAL_TIME_STEP_S))
    step_s = period_s / steps
    sunlit_steps = round((period_s - eclipse_s) / step_s)
    mean_heat_w = (sunlit_heat_w * (period_s - eclipse_s) + eclipse_heat_w * eclipse_s) / period_s
    temperature_k = (mean_heat_w / radiation_coefficient_wk4) ** 0.25
    coldest_k = warmest_k = temperature_k
    for _ in range(_THERMAL_MAX_ORBITS):
        orbit_start_k = temperature_k
        coldest_k = warmest_k = temperature_k
        for step in range(steps):
            heat_w = sunlit_heat_w if step < sunlit_steps else eclipse_heat_w
            net_w = heat_w - radiation_coefficient_wk4 * temperature_k**4
            temperature_k += net_w * step_s / capacity_jpk
            coldest_k = min(coldest_k, temperature_k)
            warmest_k = max(warmest_k, temperature_k)
        if abs(temperature_k - orbit_start_k) < _THERMAL_PERIODIC_TOLERANCE_K:
            break
    return coldest_k, warmest_k


def _paired_environment(
    albedo_high_w: float,
    albedo_low_w: float,
    earth_ir_high_w: float,
    earth_ir_low_w: float,
    albedo_factor_ratio: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """JERG-2-310A pairs the tolerances: high albedo goes with low infrared, and the reverse."""
    return (
        (albedo_high_w * albedo_factor_ratio, earth_ir_low_w),
        (albedo_low_w * albedo_factor_ratio, earth_ir_high_w),
    )


def orbit_max_temperature_k(
    sun_absorbed_w: float,
    albedo_high_absorbed_w: float,
    albedo_low_absorbed_w: float,
    earth_ir_high_absorbed_w: float,
    earth_ir_low_absorbed_w: float,
    max_beta_deg: float,
    max_consumed_power_w: float,
    surface_emissivity_ratio: float,
    surface_area_m2: float,
    stefan_boltzmann_wm2k4: float,
    thermal_capacity_jpk: float,
    orbit_period_s: float,
    min_eclipse_s: float,
) -> float:
    """Hot case: the orbit with the least eclipse, the warmer environment, the most power."""
    albedo_factor_ratio = _ALBEDO_ORBIT_AVERAGE_RATIO * math.cos(math.radians(max_beta_deg))
    pairs = _paired_environment(
        albedo_high_absorbed_w,
        albedo_low_absorbed_w,
        earth_ir_high_absorbed_w,
        earth_ir_low_absorbed_w,
        albedo_factor_ratio,
    )
    return max(
        _orbit_temperature_range(
            sun_absorbed_w + albedo_w + earth_ir_w + max_consumed_power_w,
            earth_ir_w + max_consumed_power_w,
            surface_emissivity_ratio * stefan_boltzmann_wm2k4 * surface_area_m2,
            thermal_capacity_jpk,
            orbit_period_s,
            min_eclipse_s,
        )[1]
        for albedo_w, earth_ir_w in pairs
    )


def orbit_min_temperature_k(
    sun_absorbed_w: float,
    albedo_high_absorbed_w: float,
    albedo_low_absorbed_w: float,
    earth_ir_high_absorbed_w: float,
    earth_ir_low_absorbed_w: float,
    min_consumed_power_w: float,
    heater_power_w: float,
    surface_emissivity_ratio: float,
    surface_area_m2: float,
    stefan_boltzmann_wm2k4: float,
    thermal_capacity_jpk: float,
    orbit_period_s: float,
    max_eclipse_s: float,
) -> float:
    """Cold case: the most eclipse, the cooler environment, the least power, heater in eclipse."""
    pairs = _paired_environment(
        albedo_high_absorbed_w,
        albedo_low_absorbed_w,
        earth_ir_high_absorbed_w,
        earth_ir_low_absorbed_w,
        _ALBEDO_ORBIT_AVERAGE_RATIO,
    )
    return min(
        _orbit_temperature_range(
            sun_absorbed_w + albedo_w + earth_ir_w + min_consumed_power_w,
            earth_ir_w + min_consumed_power_w + heater_power_w,
            surface_emissivity_ratio * stefan_boltzmann_wm2k4 * surface_area_m2,
            thermal_capacity_jpk,
            orbit_period_s,
            max_eclipse_s,
        )[0]
        for albedo_w, earth_ir_w in pairs
    )


def temperature_margin_k(
    orbit_max_temperature_k: float,
    orbit_min_temperature_k: float,
    allowable_max_temperature_k: float,
    allowable_min_temperature_k: float,
) -> float:
    return min(
        allowable_max_temperature_k - orbit_max_temperature_k,
        orbit_min_temperature_k - allowable_min_temperature_k,
    )


def max_radiated_power_w(
    surface_emissivity_ratio: float,
    surface_area_m2: float,
    stefan_boltzmann_wm2k4: float,
    allowable_max_temperature_k: float,
) -> float:
    return (
        surface_emissivity_ratio
        * stefan_boltzmann_wm2k4
        * surface_area_m2
        * allowable_max_temperature_k**4
    )


def usable_sunlit_power_w(sunlit_generated_power_w: float, charge_efficiency_ratio: float) -> float:
    return sunlit_generated_power_w * charge_efficiency_ratio


def orbit_generated_energy_j(usable_sunlit_power_w: float, min_sunlight_s: float) -> float:
    return usable_sunlit_power_w * min_sunlight_s


def orbit_consumed_energy_j(
    average_consumed_power_w: float,
    heater_power_w: float,
    orbit_period_s: float,
    max_eclipse_s: float,
) -> float:
    return average_consumed_power_w * orbit_period_s + heater_power_w * max_eclipse_s


def battery_depth_of_discharge_ratio(
    average_consumed_power_w: float,
    heater_power_w: float,
    max_eclipse_s: float,
    battery_capacity_j: float,
) -> float:
    return (average_consumed_power_w + heater_power_w) * max_eclipse_s / battery_capacity_j


def slant_range_m(earth_radius_m: float, orbit_radius_m: float, min_elevation_deg: float) -> float:
    elevation_rad = math.radians(min_elevation_deg)
    return math.sqrt(
        orbit_radius_m**2 - (earth_radius_m * math.cos(elevation_rad)) ** 2
    ) - earth_radius_m * math.sin(elevation_rad)


def free_space_loss_db(
    slant_range_m: float, downlink_frequency_hz: float, speed_of_light_mps: float
) -> float:
    return 20 * math.log10(4 * math.pi * slant_range_m * downlink_frequency_hz / speed_of_light_mps)


def carrier_to_noise_density_db(
    transmit_power_db: float,
    transmit_feed_loss_db: float,
    transmit_antenna_gain_db: float,
    free_space_loss_db: float,
    pointing_loss_db: float,
    receive_antenna_gain_db: float,
    receive_feed_loss_db: float,
    noise_density_db: float,
) -> float:
    received_db = (
        transmit_power_db
        - transmit_feed_loss_db
        + transmit_antenna_gain_db
        - free_space_loss_db
        - pointing_loss_db
        + receive_antenna_gain_db
        - receive_feed_loss_db
    )
    return received_db - noise_density_db


def link_margin_db(
    carrier_to_noise_density_db: float,
    other_loss_db: float,
    required_ebno_db: float,
    downlink_rate_bps: float,
) -> float:
    return (
        carrier_to_noise_density_db
        - other_loss_db
        - required_ebno_db
        - 10 * math.log10(downlink_rate_bps)
    )


def rail_bending_inertia_m4(envelope_depth_m: float, rail_width_m: float) -> float:
    offset_m = (envelope_depth_m - rail_width_m) / 2
    return 4 * (rail_width_m**4 / 12 + rail_width_m**2 * offset_m**2)


def natural_frequency_hz(
    aluminium_modulus_pa: float,
    rail_bending_inertia_m4: float,
    total_mass_kg: float,
    envelope_length_m: float,
) -> float:
    stiffness = 3 * aluminium_modulus_pa * rail_bending_inertia_m4 / envelope_length_m**3
    return math.sqrt(stiffness / total_mass_kg) / (2 * math.pi)


def margin_of_safety_ratio(
    total_mass_kg: float,
    design_acceleration_mps2: float,
    envelope_length_m: float,
    envelope_depth_m: float,
    rail_bending_inertia_m4: float,
    allowable_stress_pa: float,
    safety_factor_ratio: float,
) -> float:
    moment_nm = total_mass_kg * design_acceleration_mps2 * envelope_length_m / 2
    stress_pa = moment_nm * (envelope_depth_m / 2) / rail_bending_inertia_m4
    return allowable_stress_pa / (safety_factor_ratio * stress_pa) - 1


def orbit_lifetime_s(
    altitude_m: float,
    orbit_radius_m: float,
    earth_mu_m3s2: float,
    surface_area_m2: float,
    total_mass_kg: float,
    drag_coefficient_ratio: float,
    reference_density_kgpm3: float,
    reference_altitude_m: float,
    density_scale_height_m: float,
) -> float:
    """Time for the altitude to fall by one scale height in an exponential atmosphere."""
    density = reference_density_kgpm3 * math.exp(
        -(altitude_m - reference_altitude_m) / density_scale_height_m
    )
    ballistic_ratio = drag_coefficient_ratio * (surface_area_m2 / 4) / total_mass_kg
    decay_mps = density * ballistic_ratio * math.sqrt(earth_mu_m3s2 * orbit_radius_m)
    return density_scale_height_m / decay_mps


FORMULAS: dict[str, Callable[..., float]] = {
    function.__name__: function
    for function in (
        orbit_radius_m,
        orbit_period_s,
        max_eclipse_fraction_ratio,
        max_eclipse_s,
        min_sunlight_s,
        max_beta_deg,
        min_eclipse_fraction_ratio,
        min_eclipse_s,
        total_mass_kg,
        surface_area_m2,
        earth_view_factor_ratio,
        sun_absorbed_w,
        albedo_high_absorbed_w,
        albedo_low_absorbed_w,
        earth_ir_high_absorbed_w,
        earth_ir_low_absorbed_w,
        thermal_capacity_jpk,
        orbit_max_temperature_k,
        orbit_min_temperature_k,
        temperature_margin_k,
        max_radiated_power_w,
        usable_sunlit_power_w,
        orbit_generated_energy_j,
        orbit_consumed_energy_j,
        battery_depth_of_discharge_ratio,
        slant_range_m,
        free_space_loss_db,
        carrier_to_noise_density_db,
        link_margin_db,
        rail_bending_inertia_m4,
        natural_frequency_hz,
        margin_of_safety_ratio,
        orbit_lifetime_s,
    )
}
