"""Derives subsystem requirements from settled system requirements.

Each one states what should hold for that function, so nothing here invents a number.
An open system requirement has nothing to flow down yet.
"""

from __future__ import annotations

from satellitecreator.project import Project
from satellitecreator.requirements import (
    Function,
    Requirement,
    RequirementKind,
    RequirementLevel,
    RequirementStatus,
)

_CHECK_TEXTS = {
    Function.STRUCTURE: "質量と固有振動数がロケットの条件を満たすこと",
    Function.MISSION: "ミッション機器の質量と電力が機器構成に含まれていること",
    Function.COMMUNICATION: "回線マージンが 0 dB 以上であること",
    Function.POWER: "1 周回の電力収支と放電深度が成立すること",
    Function.ATTITUDE_CONTROL: "姿勢の方式が電力収支の前提と一致すること",
    Function.THERMAL_CONTROL: "周回の温度が許容範囲に収まること",
    Function.DATA_HANDLING: "データ処理機器の消費電力が電力収支に含まれていること",
}
# No check in the design core verifies these yet, so they stay assumptions.
_UNVERIFIED_FUNCTIONS = frozenset(
    {Function.MISSION, Function.ATTITUDE_CONTROL, Function.DATA_HANDLING}
)
_UNVERIFIED_REASON = "設計の核にこの項目を確かめる整合チェックがまだありません"


def with_subsystem_requirements(project: Project) -> Project:
    settled = tuple(
        item
        for item in project.at_level(RequirementLevel.SYSTEM)
        if item.status is not RequirementStatus.OPEN and item.function in _CHECK_TEXTS
    )
    if len(settled) != len(
        tuple(
            item
            for item in project.at_level(RequirementLevel.SYSTEM)
            if item.function in _CHECK_TEXTS
        )
    ):
        return project
    derived = tuple(
        Requirement(
            id=f"SS-{index:03d}",
            level=RequirementLevel.SUBSYSTEM,
            kind=RequirementKind.FUNCTIONAL,
            statement=_CHECK_TEXTS[item.function],
            status=(
                RequirementStatus.ASSUMED
                if item.function in _UNVERIFIED_FUNCTIONS
                else RequirementStatus.CONFIRMED
            ),
            rationale=_UNVERIFIED_REASON if item.function in _UNVERIFIED_FUNCTIONS else "",
            function=item.function,
            parents=(item.id,),
        )
        for index, item in enumerate(settled, start=1)
    )
    return project.model_copy(update={"requirements": (*project.requirements, *derived)})
