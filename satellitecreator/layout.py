"""Places the chosen equipment inside the satellite. All sizes are provisional drawing values."""

from __future__ import annotations

from functools import cache
from typing import Literal

from pydantic import Field

from satellitecreator.catalog import ReferenceBus
from satellitecreator.design import SatelliteDesign, envelope
from satellitecreator.equipment import EquipmentOption, selected_options
from satellitecreator.loading import load_yaml
from satellitecreator.schema import Frozen

Face = Literal["side", "opposite", "top", "bottom"]
Size = tuple[float, float, float]
_FACE_GAP_MM = 1.0


class PartLayout(Frozen):
    role: str
    size_mm: Size
    label: str = ""
    category: str | None = None
    face: Face | None = None
    offset_mm: Size = (0.0, 0.0, 0.0)


class LayoutCatalog(Frozen):
    internal_length_mm: dict[str, float]
    stacks: dict[str, tuple[str, ...]]
    external: dict[str, tuple[str, ...]]
    parts: dict[str, PartLayout]
    options: dict[str, PartLayout]


class LayoutItem(Frozen):
    id: str
    label: str
    group: str
    role: str
    mass_g: float | None = None
    average_power_w: float | None = None
    size_mm: Size
    center_mm: Size
    external: bool = False


class SatelliteLayout(Frozen):
    items: tuple[LayoutItem, ...]
    stack_height_mm: float = Field(ge=0)
    internal_length_mm: float = Field(gt=0)

    @property
    def fits(self) -> bool:
        return self.stack_height_mm <= self.internal_length_mm


@cache
def load_layout() -> LayoutCatalog:
    return LayoutCatalog(**load_yaml("catalog/layout.yaml"))


def _changed_options(design: SatelliteDesign) -> dict[str, EquipmentOption]:
    defaults = {item.id for item in selected_options(design.form_factor, ())}
    chosen = selected_options(design.form_factor, design.equipment)
    return {item.category: item for item in chosen if item.id not in defaults}


def _resolved_ids(ids: tuple[str, ...], changed: dict[str, EquipmentOption]) -> tuple[str, ...]:
    """Parts of a changed category give way to its option, at the first part's place."""
    catalog = load_layout()
    resolved: list[str] = []
    for part_id in ids:
        option = changed.get(catalog.parts[part_id].category or "")
        replacement = option.id if option else part_id
        if replacement not in resolved:
            resolved.append(replacement)
    return tuple(resolved)


def _stack_ids(design: SatelliteDesign, changed: dict[str, EquipmentOption]) -> tuple[str, ...]:
    catalog = load_layout()
    resolved = _resolved_ids(catalog.stacks[design.form_factor], changed)
    return tuple(item for item in resolved if not _layout_of(item).face)


def _external_ids(design: SatelliteDesign, changed: dict[str, EquipmentOption]) -> tuple[str, ...]:
    catalog = load_layout()
    resolved = _resolved_ids(catalog.external[design.form_factor], changed)
    return tuple(item for item in resolved if _layout_of(item).face)


def _layout_of(item_id: str) -> PartLayout:
    catalog = load_layout()
    return catalog.parts.get(item_id) or catalog.options[item_id]


def _item(
    item_id: str,
    bus: ReferenceBus,
    changed: dict[str, EquipmentOption],
    center_mm: Size,
    external: bool,
) -> LayoutItem:
    layout = _layout_of(item_id)
    option = next((item for item in changed.values() if item.id == item_id), None)
    part = next((item for item in bus.parts if item.id == item_id), None)
    return LayoutItem(
        id=item_id,
        label=option.label if option else layout.label,
        group=part.group if part else "選択した機器",
        role=layout.role,
        mass_g=option.mass_g if option else part.mass_g if part else None,
        average_power_w=option.average_power_mw / 1000 if option else None,
        size_mm=layout.size_mm,
        center_mm=center_mm,
        external=external,
    )


def _face_center(layout: PartLayout, body_mm: Size) -> Size:
    width, _, length = body_mm
    size = layout.size_mm
    if layout.face in ("side", "opposite"):
        sign = 1 if layout.face == "side" else -1
        base = (sign * (width / 2 + size[0] / 2 + _FACE_GAP_MM), 0.0, 0.0)
    else:
        sign = 1 if layout.face == "top" else -1
        base = (0.0, 0.0, sign * (length / 2 + size[2] / 2 + _FACE_GAP_MM))
    return tuple(a + b for a, b in zip(base, layout.offset_mm, strict=True))


def stack_height_mm(design: SatelliteDesign) -> float:
    ids = _stack_ids(design, _changed_options(design))
    return sum(_layout_of(item).size_mm[2] for item in ids)


def internal_length_mm(form_factor_id: str) -> float:
    return load_layout().internal_length_mm[form_factor_id]


def build_layout(design: SatelliteDesign, bus: ReferenceBus) -> SatelliteLayout:
    """The stack runs from +Z to -Z, centred in the body, in the order of the catalog."""
    changed = _changed_options(design)
    size = envelope(design.form_factor)
    body_mm = (size.width_m * 1000, size.depth_m * 1000, internal_length_mm(design.form_factor))
    height = stack_height_mm(design)
    cursor = height / 2
    stacked: list[LayoutItem] = []
    for item_id in _stack_ids(design, changed):
        item_height = _layout_of(item_id).size_mm[2]
        center = (0.0, 0.0, cursor - item_height / 2)
        stacked.append(_item(item_id, bus, changed, center, external=False))
        cursor -= item_height
    outside = tuple(
        _item(
            item_id,
            bus,
            changed,
            _face_center(_layout_of(item_id), body_mm),
            external=True,
        )
        for item_id in _external_ids(design, changed)
    )
    return SatelliteLayout(
        items=(*stacked, *outside),
        stack_height_mm=height,
        internal_length_mm=internal_length_mm(design.form_factor),
    )
