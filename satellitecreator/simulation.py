"""Connects a project to the design core and reports how far each block has been calculated."""

from __future__ import annotations

from enum import StrEnum

from satellitecreator.catalog import ReferenceBus, reference_bus, surface_finish
from satellitecreator.core.ledger import Ledger, LedgerEntry, solve
from satellitecreator.core.registry import Block, Equation, load_equations
from satellitecreator.design import (
    SatelliteDesign,
    envelope,
    form_factor,
    load_launch_vehicle,
)
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
_BLOCK_NOTES = {
    Block.ORBIT: "円軌道を仮定。日陰は太陽が軌道面にある最悪の場合",
    Block.MASS: "OPT-CUBE の機器構成を目安に使用",
    Block.POWER: "OPT-CUBE の機器構成を目安に使用。最短の日照で 1 周回の収支を計算",
    Block.COMMUNICATION: "OPT-CUBE の S 帯 50 kbps を目安に使用。仰角が最低のときの最悪値",
    Block.STRUCTURE: "4 本のレールを片持ち梁とした概算。解析書の FEM の代わりにはなりません",
    Block.THERMAL: (
        "衛星全体を 1 節点で計算。機器ごとの温度ではありません。"
        "高温は日陰最小と発熱最大、低温は日陰最大と発熱最小の場合"
    ),
}
# Stand-in limit: no source for this battery yet, and the inputs are marked provisional.
_ALLOWABLE_DEPTH_OF_DISCHARGE_RATIO = 0.30
_SUN_POINTING_THERMAL_NOTE = "太陽指向は熱の計算に未反映で、自由回転のままです"
_STANDARD_GRAVITY_MPS2 = 9.80665
_NEEDS_BUS_NOTE = "機器構成が必要です。今は 3U だけ登録しています"
_WAITING_NOTES = {
    Block.MASS: _NEEDS_BUS_NOTE,
    Block.POWER: _NEEDS_BUS_NOTE,
    Block.COMMUNICATION: _NEEDS_BUS_NOTE,
    Block.STRUCTURE: _NEEDS_BUS_NOTE,
    Block.THERMAL: _NEEDS_BUS_NOTE,
}


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


def _blend(base: float, covering: float, covered_ratio: float) -> float:
    return base * (1 - covered_ratio) + covering * covered_ratio


def _bus_inputs(bus: ReferenceBus, design: SatelliteDesign) -> dict[str, float]:
    covered_ratio = 0.0 if design.surface is None else design.radiator_ratio
    finish = None if design.surface is None else surface_finish(design.surface)
    absorptivity = finish.absorptivity if finish else bus.surface_absorptivity
    emissivity = finish.emissivity if finish else bus.surface_emissivity
    link = bus.link
    return {
        "design_acceleration_mps2": bus.design_load_g * _STANDARD_GRAVITY_MPS2,
        "allowable_stress_pa": bus.allowable_stress_mpa * 1e6,
        "safety_factor_ratio": bus.safety_factor,
        "downlink_frequency_hz": link.frequency_hz,
        "downlink_rate_bps": link.rate_bps,
        "transmit_power_db": link.transmit_power_db,
        "transmit_feed_loss_db": link.transmit_feed_loss_db,
        "transmit_antenna_gain_db": link.transmit_antenna_gain_db,
        "pointing_loss_db": link.pointing_loss_db,
        "receive_antenna_gain_db": link.receive_antenna_gain_db,
        "receive_feed_loss_db": link.receive_feed_loss_db,
        "noise_density_db": link.noise_density_db,
        "other_loss_db": link.other_loss_db,
        "required_ebno_db": link.required_ebno_db,
        "min_elevation_deg": link.min_elevation_deg,
        "parts_mass_kg": bus.parts_mass_kg,
        "mass_margin_kg": bus.mass_margin_kg,
        "max_consumed_power_w": design.peak_power_w or bus.max_consumed_power_w,
        "min_consumed_power_w": bus.min_consumed_power_w,
        "heater_power_w": design.heater_power_w,
        "sunlit_generated_power_w": bus.sunlit_generated_power_w(design.attitude, covered_ratio),
        "charge_efficiency_ratio": bus.charge_efficiency,
        "average_consumed_power_w": bus.average_consumed_power_w(
            design.attitude, design.peak_power_w
        ),
        "battery_capacity_j": bus.battery_capacity_j,
        "allowable_depth_of_discharge_ratio": _ALLOWABLE_DEPTH_OF_DISCHARGE_RATIO,
        "surface_absorptivity_ratio": _blend(bus.surface_absorptivity, absorptivity, covered_ratio),
        "surface_emissivity_ratio": _blend(bus.surface_emissivity, emissivity, covered_ratio),
        "allowable_max_temperature_k": bus.allowable_max_temperature_k,
        "allowable_min_temperature_k": bus.allowable_min_temperature_k,
    }


def project_ledger(project: Project) -> Ledger:
    design = project.design
    if design is None:
        return solve({})
    size = envelope(design.form_factor)
    inputs = {
        "altitude_m": design.orbit.altitude_m,
        "inclination_deg": design.orbit.inclination_deg,
        "max_mass_kg": form_factor(design.form_factor).max_mass_kg,
        "envelope_width_m": size.width_m,
        "envelope_depth_m": size.depth_m,
        "envelope_length_m": size.length_m,
        "required_natural_frequency_hz": load_launch_vehicle().longitudinal_frequency_hz,
    }
    if design.mission_duration_s is not None:
        inputs = {**inputs, "mission_duration_s": design.mission_duration_s}
    bus = reference_bus(design.form_factor)
    if bus is None:
        return solve(inputs)
    bus_inputs = _bus_inputs(bus, design)
    return solve({**inputs, **bus_inputs}, provisional=frozenset(bus_inputs))


def format_entry(equation: Equation, entry: LedgerEntry) -> str:
    value = entry.value / equation.display_divisor + equation.display_offset
    text = f"{value:.{equation.display_digits}f} {equation.display_unit}".strip()
    return f"{text}（暫定）" if entry.provisional else text


def _block_status(block: Block, ledger: Ledger) -> BlockStatus:
    common = {"block": block, "label": _BLOCK_LABELS[block]}
    equations = tuple(item for item in load_equations() if item.block is block)
    if not equations:
        return BlockStatus(state=BlockState.NOT_BUILT, **common)
    if any(ledger.value(item.output) is None for item in equations):
        return BlockStatus(state=BlockState.WAITING, note=_WAITING_NOTES.get(block, ""), **common)
    values = tuple(
        DisplayValue(label=item.label, text=format_entry(item, ledger.get(item.output)))
        for item in equations
        if item.summary
    )
    note = _BLOCK_NOTES.get(block, "")
    return BlockStatus(state=BlockState.DONE, values=values, note=note, **common)


def block_statuses(ledger: Ledger, attitude: str = "free_rotation") -> tuple[BlockStatus, ...]:
    statuses = tuple(_block_status(block, ledger) for block in Block)
    if attitude != "sun_pointing":
        return statuses
    return tuple(
        item.model_copy(update={"note": f"{item.note} {_SUN_POINTING_THERMAL_NOTE}"})
        if item.block is Block.THERMAL and item.state is BlockState.DONE
        else item
        for item in statuses
    )
