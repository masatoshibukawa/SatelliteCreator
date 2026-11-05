"""Values stated in published contest reports, each with its report and page.

Only the numbers and citations live here. The reports themselves stay out of the repository.
"""

from __future__ import annotations

from functools import cache

from pydantic import Field

from satellitecreator.loading import load_yaml
from satellitecreator.schema import Frozen, Sourced


class ReferenceValue(Sourced):
    key: str
    value: float
    page: int = Field(gt=0)


class ReferenceReport(Frozen):
    id: str
    title: str
    values: tuple[ReferenceValue, ...]

    def value(self, key: str) -> float:
        return next(item.value for item in self.values if item.key == key)


@cache
def load_reference_reports() -> tuple[ReferenceReport, ...]:
    return tuple(ReferenceReport(**item) for item in load_yaml("reference/reports.yaml")["reports"])
