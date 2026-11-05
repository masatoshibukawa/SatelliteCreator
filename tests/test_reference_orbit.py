"""Reproduces the orbit values stated in published contest reports.

The reports are paper designs, so a difference is recorded rather than tuned away.
"""

import pytest

from satellitecreator.core.ledger import solve
from satellitecreator.core.reference import load_reference_reports
from satellitecreator.core.registry import load_constants

SATEBAL_PERIOD_TOLERANCE_RATIO = 0.005
OPT_CUBE_KNOWN_PERIOD_DIFFERENCE_RATIO = 0.017


def _report(report_id: str):
    return next(item for item in load_reference_reports() if item.id == report_id)


def _earth_radius_m() -> float:
    return next(item.value for item in load_constants() if item.key == "earth_radius_m")


def test_every_reference_value_cites_its_report_and_page():
    reports = load_reference_reports()

    assert reports
    assert all(item.source and item.page > 0 for report in reports for item in report.values)


def test_opt_cube_period_differs_from_the_report_by_the_recorded_amount():
    """The report rounds to 91 min and 400 km depends on the ISS altitude at release."""
    report = _report("opt_cube")

    ledger = solve({"altitude_m": report.value("altitude_m")})

    difference = ledger.value("orbit_period_s") / report.value("orbit_period_s") - 1
    assert difference == pytest.approx(OPT_CUBE_KNOWN_PERIOD_DIFFERENCE_RATIO, abs=0.001)


def test_opt_cube_eclipse_does_not_exceed_the_worst_case():
    """A bound only: this does not reproduce the report's eclipse value."""
    report = _report("opt_cube")

    ledger = solve({"altitude_m": report.value("altitude_m")})

    assert report.value("eclipse_s") <= ledger.value("max_eclipse_s")


def test_satebal_period_is_reproduced_from_its_semi_major_axis():
    report = _report("satebal")
    altitude_m = report.value("semi_major_axis_m") - _earth_radius_m()

    ledger = solve({"altitude_m": altitude_m})

    assert ledger.value("orbit_period_s") == pytest.approx(
        report.value("orbit_period_s"), rel=SATEBAL_PERIOD_TOLERANCE_RATIO
    )
