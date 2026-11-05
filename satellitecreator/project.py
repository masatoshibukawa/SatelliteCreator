"""The project record that moves through the review gates."""

from __future__ import annotations

from collections import Counter
from enum import StrEnum

from pydantic import Field, model_validator

from satellitecreator.design import SatelliteDesign
from satellitecreator.process import Review
from satellitecreator.requirements import Requirement, RequirementLevel
from satellitecreator.schema import Frozen, NonBlankText, Text


class SuccessLevel(StrEnum):
    MINIMUM = "minimum"
    FULL = "full"
    EXTRA = "extra"


class SuccessCriterion(Frozen):
    level: SuccessLevel
    statement: NonBlankText


class MissionDefinition(Frozen):
    """Purpose, stakeholders and success criteria, as JERG-2-100 6.1 asks for."""

    objective: NonBlankText
    stakeholders: tuple[NonBlankText, ...] = Field(min_length=1)
    success_criteria: tuple[SuccessCriterion, ...] = ()


class Project(Frozen):
    name: NonBlankText
    mission: MissionDefinition | None = None
    requirements: tuple[Requirement, ...] = ()
    operations_concept: Text = ""
    design: SatelliteDesign | None = None
    passed_reviews: tuple[Review, ...] = ()

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Project:
        counts = Counter(item.id for item in self.requirements)
        duplicates = sorted(key for key, count in counts.items() if count > 1)
        if duplicates:
            raise ValueError(f"duplicate requirement ids: {duplicates}")
        return self

    def at_level(self, level: RequirementLevel) -> tuple[Requirement, ...]:
        return tuple(item for item in self.requirements if item.level is level)
