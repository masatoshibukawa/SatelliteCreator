"""Equipment the user chooses, and how a choice changes a reference bus."""

from __future__ import annotations

from functools import cache

from pydantic import Field

from satellitecreator.catalog import LinkBudget, ReferenceBus, reference_bus
from satellitecreator.loading import load_yaml
from satellitecreator.schema import Frozen, Sourced


class EquipmentCategory(Frozen):
    id: str
    label: str


class EquipmentOption(Sourced):
    id: str
    category: str
    label: str
    mass_g: float = Field(gt=0)
    average_power_mw: float = Field(ge=0)
    cell_ratio: float = Field(default=1.0, gt=0)
    link_bus: str | None = None


class EquipmentCatalog(Frozen):
    categories: tuple[EquipmentCategory, ...]
    options: tuple[EquipmentOption, ...]
    defaults: dict[str, tuple[str, ...]]


class EquipmentEffect(Frozen):
    """What the chosen equipment changes compared with the bus as published."""

    mass_delta_kg: float = 0.0
    power_delta_w: float = 0.0
    generation_ratio: float = 1.0
    link: LinkBudget


class UnknownEquipmentError(ValueError):
    """A selection names equipment that does not exist, which is the caller's mistake."""


@cache
def load_equipment() -> EquipmentCatalog:
    return EquipmentCatalog(**load_yaml("catalog/equipment.yaml"))


def _option(option_id: str) -> EquipmentOption:
    return next(item for item in load_equipment().options if item.id == option_id)


def check_selection(chosen: tuple[str, ...]) -> None:
    known = {item.id for item in load_equipment().options}
    unknown = sorted(set(chosen) - known)
    if unknown:
        raise UnknownEquipmentError(f"unknown equipment ids: {unknown}")


def selected_options(form_factor_id: str, chosen: tuple[str, ...]) -> tuple[EquipmentOption, ...]:
    """The bus defaults with each choice replacing the option of its category."""
    defaults = load_equipment().defaults.get(form_factor_id, ())
    selection = {_option(item).category: _option(item) for item in (*defaults, *chosen)}
    return tuple(selection[item.id] for item in load_equipment().categories if item.id in selection)


def equipment_effect(bus: ReferenceBus, chosen: tuple[str, ...]) -> EquipmentEffect:
    defaults = selected_options(bus.form_factor, ())
    selected = selected_options(bus.form_factor, chosen)
    mass_delta_g = sum(item.mass_g for item in selected) - sum(item.mass_g for item in defaults)
    power_delta_mw = sum(item.average_power_mw for item in selected) - sum(
        item.average_power_mw for item in defaults
    )
    generation_ratio = 1.0
    for before, after in zip(defaults, selected, strict=True):
        generation_ratio *= after.cell_ratio / before.cell_ratio
    link_buses = (item.link_bus for item in selected if item.link_bus)
    link_bus = next(link_buses, bus.form_factor)
    return EquipmentEffect(
        mass_delta_kg=mass_delta_g / 1000,
        power_delta_w=power_delta_mw / 1000,
        generation_ratio=generation_ratio,
        link=reference_bus(link_bus).link,
    )
