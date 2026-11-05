"""Hands a design to the launcher side as launch_request.json.

Run `python -m satellitecreator.launch_request --prompt "..." --output launch_request.json`.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from satellitecreator.design import envelope
from satellitecreator.intake import build_intake
from satellitecreator.project import Project
from satellitecreator.schema import Frozen, NonBlankText
from satellitecreator.simulation import project_ledger

SCHEMA_VERSION = 1
_MASS_DIGITS = 4
_MILLIMETRE_DIGITS = 1


class EnvelopeMm(Frozen):
    width: float
    depth: float
    height: float


class LaunchRequest(Frozen):
    schema_version: int = SCHEMA_VERSION
    satellite_name: NonBlankText
    payload_mass_kg: float
    target_perigee_m: float
    target_apogee_m: float
    inclination_deg: float
    envelope_mm: EnvelopeMm
    sources: dict[str, str]
    provisional: bool


def _requirement_source(project: Project, key: str) -> str:
    return next(
        (
            f"要求 {item.id}: {item.statement}"
            for item in project.requirements
            if item.target is not None and item.target.key == key
        ),
        "設計の軌道",
    )


def _millimetres(value_m: float) -> float:
    return round(value_m * 1000, _MILLIMETRE_DIGITS)


def build_launch_request(
    project: Project, satellite_name: str | None = None
) -> LaunchRequest | None:
    """Returns None until the design has an orbit and a calculated mass."""
    design = project.design
    mass = project_ledger(project).get("total_mass_kg")
    if design is None or mass is None:
        return None
    size = envelope(design.form_factor)
    altitude_source = f"{_requirement_source(project, 'altitude_m')}（円軌道を仮定）"
    mass_source = f"計算 total_mass_kg: {mass.formula}（{mass.source} {mass.section}）"
    return LaunchRequest(
        satellite_name=satellite_name or project.name,
        payload_mass_kg=round(mass.value, _MASS_DIGITS),
        target_perigee_m=design.orbit.altitude_m,
        target_apogee_m=design.orbit.altitude_m,
        inclination_deg=design.orbit.inclination_deg,
        envelope_mm=EnvelopeMm(
            width=_millimetres(size.width_m),
            depth=_millimetres(size.depth_m),
            height=_millimetres(size.length_m),
        ),
        sources={
            "payload_mass_kg": mass_source,
            "target_perigee_m": altitude_source,
            "target_apogee_m": altitude_source,
            "inclination_deg": _requirement_source(project, "inclination_deg"),
            "envelope_mm": f"{size.source} {size.section}",
        },
        provisional=mass.provisional,
    )


def to_json(request: LaunchRequest) -> str:
    return json.dumps(request.model_dump(mode="json"), ensure_ascii=False, indent=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write launch_request.json for a request.")
    parser.add_argument("--prompt", required=True, help="the satellite request text")
    parser.add_argument("--name", help="satellite name; defaults to the start of the request")
    parser.add_argument("--output", required=True, type=Path, help="path of the file to write")
    args = parser.parse_args(argv)

    request = build_launch_request(build_intake(args.prompt, {}).project, args.name)
    if request is None:
        sys.stderr.write("launch_request を作れません。軌道と計算済みの質量が必要です。\n")
        return 1
    args.output.write_text(to_json(request) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
