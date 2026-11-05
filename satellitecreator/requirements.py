"""Requirement models.

A requirement is confirmed, assumed or open. Assumed ones keep the reason for the assumption
and open ones keep the question to ask the user, so the dialogue can be driven from this data.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, field_validator, model_validator

from satellitecreator.schema import UNIT_SUFFIXES, Frozen, NonBlankText, Text


class RequirementLevel(StrEnum):
    MISSION = "mission"
    SYSTEM = "system"
    SUBSYSTEM = "subsystem"


class RequirementKind(StrEnum):
    FUNCTIONAL = "functional"
    PERFORMANCE = "performance"
    CONSTRAINT = "constraint"


class RequirementStatus(StrEnum):
    CONFIRMED = "confirmed"
    ASSUMED = "assumed"
    OPEN = "open"


class Function(StrEnum):
    """Functions from JERG-2-100 6.2, plus data handling from the contest rules (Annex 1, 5.3)."""

    MISSION = "mission"
    ORBIT = "orbit"
    COMMUNICATION = "communication"
    POWER = "power"
    ATTITUDE_CONTROL = "attitude_control"
    ORBIT_CONTROL = "orbit_control"
    THERMAL_CONTROL = "thermal_control"
    STRUCTURE = "structure"
    DATA_HANDLING = "data_handling"


# Orbit control is left out: the contest rules ask for it only when the mission needs it.
REQUIRED_FUNCTIONS = frozenset(Function) - {Function.ORBIT_CONTROL}

_ID_PREFIXES = {
    RequirementLevel.MISSION: "MR-",
    RequirementLevel.SYSTEM: "SR-",
    RequirementLevel.SUBSYSTEM: "SS-",
}
_QUANTIFIED_KINDS = frozenset({RequirementKind.PERFORMANCE, RequirementKind.CONSTRAINT})


class Comparator(StrEnum):
    AT_MOST = "<="
    AT_LEAST = ">="
    EQUAL = "=="


class Target(Frozen):
    """The number a requirement is checked against. `key` is unit-suffixed."""

    key: str
    comparator: Comparator
    value: float = Field(allow_inf_nan=False)

    @field_validator("key")
    @classmethod
    def _key_has_unit_suffix(cls, key: str) -> str:
        if key in UNIT_SUFFIXES or not key.endswith(UNIT_SUFFIXES):
            raise ValueError(f"key {key!r} must be a name ending with a unit suffix")
        return key


class Requirement(Frozen):
    id: str = Field(pattern=r"^(MR|SR|SS)-\d{3}$")
    level: RequirementLevel
    kind: RequirementKind
    statement: NonBlankText
    status: RequirementStatus
    rationale: Text = ""
    question: Text = ""
    function: Function | None = None
    parents: tuple[str, ...] = ()
    target: Target | None = None

    @model_validator(mode="after")
    def _check_id_prefix(self) -> Requirement:
        prefix = _ID_PREFIXES[self.level]
        if not self.id.startswith(prefix):
            raise ValueError(f"{self.id}: {self.level} requirements use the prefix {prefix}")
        return self

    @model_validator(mode="after")
    def _check_status(self) -> Requirement:
        if self.status is RequirementStatus.ASSUMED and not self.rationale:
            raise ValueError(f"{self.id}: an assumed requirement needs a `rationale`")
        if self.status is RequirementStatus.OPEN:
            if not self.question:
                raise ValueError(f"{self.id}: an open requirement needs a `question`")
            return self
        if self.question:
            raise ValueError(f"{self.id}: a settled requirement keeps no `question`")
        if self.kind in _QUANTIFIED_KINDS and self.target is None:
            raise ValueError(f"{self.id}: a settled {self.kind} requirement needs a `target`")
        return self

    @model_validator(mode="after")
    def _check_lineage(self) -> Requirement:
        if len(set(self.parents)) != len(self.parents):
            raise ValueError(f"{self.id}: duplicate parents {self.parents}")
        if self.level is RequirementLevel.MISSION:
            if self.parents:
                raise ValueError(f"{self.id}: a mission requirement has no parent")
            if self.function is not None:
                raise ValueError(f"{self.id}: a mission requirement has no `function`")
            return self
        if self.function is None:
            raise ValueError(f"{self.id}: a {self.level} requirement needs a `function`")
        if not self.parents:
            raise ValueError(f"{self.id}: a {self.level} requirement needs a parent")
        return self
