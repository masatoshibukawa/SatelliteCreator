"""Connects a project to the design core and reports how far each block has been calculated."""

from __future__ import annotations

from enum import StrEnum

from satellitecreator.core.ledger import Ledger, LedgerEntry, solve
from satellitecreator.core.registry import Block, Equation, load_equations
from satellitecreator.design import form_factor
from satellitecreator.project import Project
from satellitecreator.schema import Frozen

_BLOCK_LABELS = {
    Block.ORBIT: "軌道",
    Block.MASS: "質量",
    Block.POWER: "電源",
    Block.THERMAL: "熱",
    Block.COMMUNICATION: "通信",
    Block.STRUCTURE: "構造",
}
_BLOCK_NOTES = {Block.ORBIT: "円軌道を仮定。日陰は太陽が軌道面にある最悪の場合"}


class BlockState(StrEnum):
    DONE = "done"
    WAITING = "waiting"
    NOT_BUILT = "not_built"


class DisplayValue(Frozen):
    label: str
    text: str


class BlockStatus(Frozen):
    block: Block
    label: str
    state: BlockState
    values: tuple[DisplayValue, ...] = ()
    note: str = ""


def project_ledger(project: Project) -> Ledger:
    design = project.design
    if design is None:
        return solve({})
    return solve(
        {
            "altitude_m": design.orbit.altitude_m,
            "inclination_deg": design.orbit.inclination_deg,
            "max_mass_kg": form_factor(design.form_factor).max_mass_kg,
        }
    )


def format_entry(equation: Equation, entry: LedgerEntry) -> str:
    text = f"{entry.value / equation.display_divisor:.1f} {equation.display_unit}".strip()
    return f"{text}（暫定）" if entry.provisional else text


def _block_status(block: Block, ledger: Ledger) -> BlockStatus:
    common = {"block": block, "label": _BLOCK_LABELS[block]}
    equations = tuple(item for item in load_equations() if item.block is block)
    if not equations:
        return BlockStatus(state=BlockState.NOT_BUILT, **common)
    if any(ledger.value(item.output) is None for item in equations):
        return BlockStatus(state=BlockState.WAITING, **common)
    values = tuple(
        DisplayValue(label=item.label, text=format_entry(item, ledger.get(item.output)))
        for item in equations
        if item.summary
    )
    note = _BLOCK_NOTES.get(block, "")
    return BlockStatus(state=BlockState.DONE, values=values, note=note, **common)


def block_statuses(ledger: Ledger) -> tuple[BlockStatus, ...]:
    return tuple(_block_status(block, ledger) for block in Block)
