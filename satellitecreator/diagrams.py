"""Values the main screen draws. They are read from the ledger, so nothing is computed here."""

from __future__ import annotations

from satellitecreator.core.ledger import Ledger
from satellitecreator.schema import Frozen


class DiagramData(Frozen):
    altitude_m: float | None = None
    inclination_deg: float | None = None
    orbit_period_s: float | None = None
    max_eclipse_s: float | None = None
    min_sunlight_s: float | None = None
    usable_sunlit_power_w: float | None = None
    average_consumed_power_w: float | None = None
    orbit_generated_energy_j: float | None = None
    orbit_consumed_energy_j: float | None = None
    battery_depth_of_discharge_ratio: float | None = None
    link_margin_db: float | None = None
    slant_range_m: float | None = None
    min_elevation_deg: float | None = None
    downlink_frequency_hz: float | None = None
    downlink_rate_bps: float | None = None
    provisional: bool = False


def diagram_data(ledger: Ledger) -> DiagramData:
    entries = {name: ledger.get(name) for name in DiagramData.model_fields if name != "provisional"}
    present = {name: entry for name, entry in entries.items() if entry is not None}
    return DiagramData(
        **{name: entry.value for name, entry in present.items()},
        provisional=any(entry.provisional for entry in present.values()),
    )
