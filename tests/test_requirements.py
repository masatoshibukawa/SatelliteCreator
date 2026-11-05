import math

import pytest
from pydantic import ValidationError

from satellitecreator.requirements import (
    Comparator,
    Function,
    Requirement,
    RequirementKind,
    RequirementLevel,
    RequirementStatus,
    Target,
)

MASS_LIMIT = Target(key="total_mass_kg", comparator=Comparator.AT_MOST, value=4.5)


def _system_requirement(**overrides) -> Requirement:
    fields = {
        "id": "SR-001",
        "level": RequirementLevel.SYSTEM,
        "kind": RequirementKind.PERFORMANCE,
        "statement": "Total mass stays within the 3U limit",
        "status": RequirementStatus.CONFIRMED,
        "function": Function.STRUCTURE,
        "parents": ("MR-001",),
        "target": MASS_LIMIT,
    }
    return Requirement(**{**fields, **overrides})


def test_target_rejects_key_without_unit_suffix():
    with pytest.raises(ValidationError, match="unit suffix"):
        Target(key="total_mass", comparator=Comparator.AT_MOST, value=4.5)


@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_target_rejects_non_finite_value(value):
    with pytest.raises(ValidationError):
        Target(key="total_mass_kg", comparator=Comparator.AT_MOST, value=value)


def test_confirmed_performance_requirement_is_valid():
    assert _system_requirement().target == MASS_LIMIT


@pytest.mark.parametrize(
    ("level", "requirement_id"),
    [
        (RequirementLevel.MISSION, "SR-001"),
        (RequirementLevel.SYSTEM, "MR-001"),
        (RequirementLevel.SUBSYSTEM, "SR-001"),
    ],
)
def test_id_prefix_must_match_level(level, requirement_id):
    with pytest.raises(ValidationError, match="prefix"):
        _system_requirement(id=requirement_id, level=level)


def test_id_must_follow_the_numbering_format():
    with pytest.raises(ValidationError):
        _system_requirement(id="SR-1")


def test_assumed_requirement_needs_a_rationale():
    with pytest.raises(ValidationError, match="rationale"):
        _system_requirement(status=RequirementStatus.ASSUMED)


def test_assumed_requirement_with_rationale_is_valid():
    requirement = _system_requirement(
        status=RequirementStatus.ASSUMED, rationale="Typical of 3U missions"
    )

    assert requirement.status is RequirementStatus.ASSUMED


def test_open_requirement_needs_a_question():
    with pytest.raises(ValidationError, match="question"):
        _system_requirement(status=RequirementStatus.OPEN, target=None)


def test_open_requirement_may_be_unquantified():
    requirement = _system_requirement(
        status=RequirementStatus.OPEN, target=None, question="How heavy may it be?"
    )

    assert requirement.target is None


@pytest.mark.parametrize("kind", [RequirementKind.PERFORMANCE, RequirementKind.CONSTRAINT])
def test_settled_quantitative_requirement_needs_a_target(kind):
    with pytest.raises(ValidationError, match="target"):
        _system_requirement(kind=kind, target=None)


def test_functional_requirement_needs_no_target():
    requirement = _system_requirement(kind=RequirementKind.FUNCTIONAL, target=None)

    assert requirement.target is None


@pytest.mark.parametrize(
    ("requirement_id", "level"),
    [("SR-001", RequirementLevel.SYSTEM), ("SS-001", RequirementLevel.SUBSYSTEM)],
)
def test_lower_level_requirement_needs_a_function(requirement_id, level):
    with pytest.raises(ValidationError, match="function"):
        _system_requirement(id=requirement_id, level=level, function=None)


@pytest.mark.parametrize(
    ("requirement_id", "level"),
    [("SR-001", RequirementLevel.SYSTEM), ("SS-001", RequirementLevel.SUBSYSTEM)],
)
def test_lower_level_requirement_needs_a_parent(requirement_id, level):
    with pytest.raises(ValidationError, match="parent"):
        _system_requirement(id=requirement_id, level=level, parents=())


def test_mission_requirement_needs_no_function_or_parent():
    requirement = Requirement(
        id="MR-001",
        level=RequirementLevel.MISSION,
        kind=RequirementKind.FUNCTIONAL,
        statement="Demonstrate optical downlink from orbit",
        status=RequirementStatus.CONFIRMED,
    )

    assert requirement.parents == ()


def test_target_rejects_key_that_is_only_a_suffix():
    with pytest.raises(ValidationError, match="unit suffix"):
        Target(key="_kg", comparator=Comparator.AT_MOST, value=4.5)


def test_blank_statement_is_rejected():
    with pytest.raises(ValidationError):
        _system_requirement(statement="   ")


def test_blank_rationale_does_not_justify_an_assumption():
    with pytest.raises(ValidationError, match="rationale"):
        _system_requirement(status=RequirementStatus.ASSUMED, rationale="   ")


def test_blank_question_does_not_count():
    with pytest.raises(ValidationError, match="question"):
        _system_requirement(status=RequirementStatus.OPEN, target=None, question="   ")


def test_settled_requirement_keeps_no_question():
    with pytest.raises(ValidationError, match="question"):
        _system_requirement(question="How heavy may it be?")


def test_parents_must_be_unique():
    with pytest.raises(ValidationError, match="duplicate"):
        _system_requirement(parents=("MR-001", "MR-001"))


def test_mission_requirement_rejects_a_function():
    with pytest.raises(ValidationError, match="function"):
        Requirement(
            id="MR-003",
            level=RequirementLevel.MISSION,
            kind=RequirementKind.FUNCTIONAL,
            statement="Demonstrate optical downlink from orbit",
            status=RequirementStatus.CONFIRMED,
            function=Function.COMMUNICATION,
        )


def test_mission_requirement_rejects_parents():
    with pytest.raises(ValidationError, match="parent"):
        Requirement(
            id="MR-002",
            level=RequirementLevel.MISSION,
            kind=RequirementKind.FUNCTIONAL,
            statement="Demonstrate optical downlink from orbit",
            status=RequirementStatus.CONFIRMED,
            parents=("MR-001",),
        )
