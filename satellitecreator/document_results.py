"""Design results for the document. Values come from the ledger or the reference bus only."""

from __future__ import annotations

from satellitecreator.catalog import ReferenceBus
from satellitecreator.core.ledger import Ledger
from satellitecreator.core.registry import Block, Equation, load_equations
from satellitecreator.equipment import equipment_effect, load_equipment, selected_options
from satellitecreator.requirements import Function
from satellitecreator.simulation import format_entry
from satellitecreator.timeline import Timeline

_RESULT_BLOCKS = {
    Block.ORBIT: Function.ORBIT,
    Block.STRUCTURE: Function.STRUCTURE,
    Block.COMMUNICATION: Function.COMMUNICATION,
    Block.POWER: Function.POWER,
    Block.THERMAL: Function.THERMAL_CONTROL,
}
_GROUND_LINK_OUTPUTS = ("slant_range_m", "link_margin_db")


def _value_line(equation: Equation, ledger: Ledger) -> str:
    return f"{equation.label}: {format_entry(equation, ledger.get(equation.output))}"


def equipment_lines(bus: ReferenceBus, chosen: tuple[str, ...]) -> tuple[str, ...]:
    groups = dict.fromkeys(item.group for item in bus.parts)
    lines = []
    for group in groups:
        parts = tuple(item for item in bus.parts if item.group == group)
        names = "、".join(item.id for item in parts)
        lines.append(f"{group}: {sum(item.mass_g for item in parts):.1f} g（{names}）")
    labels = {item.id: item.label for item in load_equipment().categories}
    selected = tuple(
        f"{labels[item.category]}の選択: {item.label}（{item.mass_g:g} g、暫定）"
        for item in selected_options(bus.form_factor, chosen)
    )
    mass_delta_kg = equipment_effect(bus, chosen).mass_delta_kg
    change = (f"選択による質量の変化: {mass_delta_kg * 1000:+.1f} g",) if mass_delta_kg else ()
    return (*lines, f"質量余裕: {bus.mass_margin_g:.1f} g", *selected, *change)


def subsystem_result_lines(ledger: Ledger, labels: dict[Function, str]) -> tuple[str, ...]:
    return tuple(
        f"{labels[function]}の結果: {_value_line(item, ledger)}"
        for block, function in _RESULT_BLOCKS.items()
        for item in load_equations()
        if item.block is block and item.summary and ledger.get(item.output) is not None
    )


def contact_lines(timeline: Timeline | None) -> tuple[str, ...]:
    if timeline is None:
        return ()
    return (
        f"{timeline.station}との通信: 1 日 {len(timeline.contacts)} 回、"
        f"合計 {timeline.contact_s / 60:.0f} 分（暫定）",
        f"1 日のダウンリンク量: {timeline.downlink_bit / 8e6:.1f} MB（暫定）",
    )


def ground_link_lines(bus: ReferenceBus, ledger: Ledger) -> tuple[str, ...]:
    link = bus.link
    conditions = (
        f"ダウンリンク: 周波数 {link.frequency_hz / 1e9:g} GHz、"
        f"伝送速度 {link.rate_bps / 1000:g} kbps、最低仰角 {link.min_elevation_deg:g} 度"
    )
    equations = {item.output: item for item in load_equations()}
    return (conditions, *(_value_line(equations[name], ledger) for name in _GROUND_LINK_OUTPUTS))
