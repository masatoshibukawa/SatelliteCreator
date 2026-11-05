"""Equation implementations.

Each function is named after the quantity it produces and its parameters are named after the
quantities it reads. `data/core/equations.yaml` holds the formula text and source of each one.
"""

from __future__ import annotations

import math
from collections.abc import Callable


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


FORMULAS: dict[str, Callable[..., float]] = {
    function.__name__: function
    for function in (
        orbit_radius_m,
        orbit_period_s,
        max_eclipse_fraction_ratio,
        max_eclipse_s,
        min_sunlight_s,
    )
}
