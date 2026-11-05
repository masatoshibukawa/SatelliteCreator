"""Loads the constants, inputs, equations and checks, and verifies they fit together."""

from __future__ import annotations

import inspect
from collections import Counter
from collections.abc import Callable, Mapping
from enum import StrEnum
from functools import cache

from pydantic import Field, model_validator

from satellitecreator.core.formulas import FORMULAS
from satellitecreator.loading import load_yaml
from satellitecreator.requirements import Comparator
from satellitecreator.schema import Frozen, Sourced


class Block(StrEnum):
    ORBIT = "orbit"
    MASS = "mass"
    POWER = "power"
    THERMAL = "thermal"
    COMMUNICATION = "communication"
    STRUCTURE = "structure"


class Constant(Sourced):
    key: str
    label: str
    value: float = Field(allow_inf_nan=False)


class InputSpec(Frozen):
    key: str
    label: str


class Equation(Sourced):
    """Produces one quantity. Exactly one equation may produce a given quantity."""

    output: str
    label: str
    formula: str
    inputs: tuple[str, ...]
    block: Block
    display_divisor: float = Field(default=1.0, gt=0)
    display_unit: str = ""
    summary: bool = False


class CheckSpec(Sourced):
    """Compares a quantity with another quantity or with a fixed threshold."""

    id: str
    label: str
    block: Block
    left: str
    comparator: Comparator
    right: str | None = None
    right_value: float | None = None

    @model_validator(mode="after")
    def _one_right_side(self) -> CheckSpec:
        if (self.right is None) == (self.right_value is None):
            raise ValueError(f"{self.id}: set exactly one of `right` and `right_value`")
        return self


def _require_single_definitions(
    equations: tuple[Equation, ...],
    constants: tuple[Constant, ...],
    inputs: tuple[InputSpec, ...],
    planned: tuple[str, ...],
) -> None:
    counts = Counter(
        (
            *(item.output for item in equations),
            *(item.key for item in constants),
            *(item.key for item in inputs),
            *planned,
        )
    )
    repeated = sorted(key for key, count in counts.items() if count > 1)
    if repeated:
        raise ValueError(f"each quantity is produced in one place only: {repeated}")


def _require_formulas(
    equations: tuple[Equation, ...], formulas: Mapping[str, Callable[..., float]]
) -> None:
    for equation in equations:
        formula = formulas.get(equation.output)
        if formula is None:
            raise ValueError(f"no formula function for {equation.output}")
        parameters = tuple(inspect.signature(formula).parameters)
        if parameters != equation.inputs:
            raise ValueError(f"{equation.output}: inputs {equation.inputs} != {parameters}")


def _require_resolvable(equations: tuple[Equation, ...], known: frozenset[str]) -> None:
    produced = {item.output for item in equations}
    read = {key for item in equations for key in item.inputs}
    unknown = sorted(read - known - produced)
    if unknown:
        raise ValueError(f"unknown quantity read by an equation: {unknown}")
    available = known
    pending = equations
    while pending:
        ready = tuple(item for item in pending if set(item.inputs) <= available)
        if not ready:
            raise ValueError(f"equations form a cycle: {[item.output for item in pending]}")
        available = available | {item.output for item in ready}
        pending = tuple(item for item in pending if item not in ready)


def validate_equations(
    equations: tuple[Equation, ...],
    formulas: Mapping[str, Callable[..., float]],
    constants: tuple[Constant, ...],
    inputs: tuple[InputSpec, ...],
    planned: tuple[str, ...] = (),
) -> None:
    _require_single_definitions(equations, constants, inputs, planned)
    _require_formulas(equations, formulas)
    known = frozenset({item.key for item in constants} | {item.key for item in inputs})
    _require_resolvable(equations, known)


def validate_checks(checks: tuple[CheckSpec, ...], known: frozenset[str]) -> None:
    for check in checks:
        keys = {check.left} if check.right is None else {check.left, check.right}
        unknown = sorted(keys - known)
        if unknown:
            raise ValueError(f"{check.id}: unknown quantity {unknown}")


@cache
def load_constants() -> tuple[Constant, ...]:
    return tuple(Constant(**item) for item in load_yaml("core/constants.yaml")["constants"])


@cache
def load_inputs() -> tuple[InputSpec, ...]:
    return tuple(InputSpec(**item) for item in load_yaml("core/equations.yaml")["inputs"])


@cache
def load_planned_quantities() -> tuple[str, ...]:
    """Quantities that checks already name but no equation produces yet."""
    return tuple(load_yaml("core/equations.yaml")["planned_quantities"])


@cache
def load_equations() -> tuple[Equation, ...]:
    equations = tuple(Equation(**item) for item in load_yaml("core/equations.yaml")["equations"])
    validate_equations(
        equations, FORMULAS, load_constants(), load_inputs(), load_planned_quantities()
    )
    return equations


@cache
def load_checks() -> tuple[CheckSpec, ...]:
    checks = tuple(CheckSpec(**item) for item in load_yaml("core/checks.yaml")["checks"])
    known = frozenset(
        (
            *(item.key for item in load_constants()),
            *(item.key for item in load_inputs()),
            *(item.output for item in load_equations()),
            *load_planned_quantities(),
        )
    )
    validate_checks(checks, known)
    return checks
