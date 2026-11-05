"""The ledger: every quantity appears once, with how it was made.

`solve` computes everything the inputs allow, so a quantity shared by two subsystems is the same
value by construction. Anything that cannot be computed yet is listed as missing, never guessed.
"""

from __future__ import annotations

import math
from collections.abc import Collection, Mapping
from enum import StrEnum

from satellitecreator.core.formulas import FORMULAS
from satellitecreator.core.registry import (
    Equation,
    load_constants,
    load_equations,
    load_inputs,
)
from satellitecreator.schema import Frozen


class Origin(StrEnum):
    INPUT = "input"
    CONSTANT = "constant"
    EQUATION = "equation"


class LedgerEntry(Frozen):
    key: str
    label: str
    value: float
    origin: Origin
    formula: str = ""
    inputs: tuple[str, ...] = ()
    source: str | None = None
    section: str = ""
    provisional: bool = False


class Ledger(Frozen):
    entries: tuple[LedgerEntry, ...]
    missing: tuple[str, ...] = ()

    def get(self, key: str) -> LedgerEntry | None:
        return next((item for item in self.entries if item.key == key), None)

    def value(self, key: str) -> float | None:
        entry = self.get(key)
        return None if entry is None else entry.value


def _input_entries(
    inputs: Mapping[str, float], provisional: Collection[str]
) -> dict[str, LedgerEntry]:
    labels = {item.key: item.label for item in load_inputs()}
    unknown = sorted(set(inputs) - set(labels))
    if unknown:
        raise ValueError(f"unknown input quantities: {unknown}")
    not_finite = sorted(key for key, value in inputs.items() if not math.isfinite(value))
    if not_finite:
        raise ValueError(f"input must be finite: {not_finite}")
    return {
        key: LedgerEntry(
            key=key,
            label=labels[key],
            value=value,
            origin=Origin.INPUT,
            provisional=key in provisional,
        )
        for key, value in inputs.items()
    }


def _constant_entries() -> dict[str, LedgerEntry]:
    return {
        item.key: LedgerEntry(
            key=item.key,
            label=item.label,
            value=item.value,
            origin=Origin.CONSTANT,
            source=item.source,
            section=item.section,
            provisional=item.provisional,
        )
        for item in load_constants()
    }


def _evaluate(equation: Equation, known: Mapping[str, LedgerEntry]) -> LedgerEntry:
    arguments = {key: known[key].value for key in equation.inputs}
    value = FORMULAS[equation.output](**arguments)
    if not math.isfinite(value):
        raise ValueError(f"{equation.output} is not finite for {arguments}")
    return LedgerEntry(
        key=equation.output,
        label=equation.label,
        value=value,
        origin=Origin.EQUATION,
        formula=equation.formula,
        inputs=equation.inputs,
        source=equation.source,
        section=equation.section,
        provisional=equation.provisional or any(known[key].provisional for key in equation.inputs),
    )


def solve(inputs: Mapping[str, float], provisional: Collection[str] = ()) -> Ledger:
    """`provisional` names stand-in inputs. Everything derived from them inherits the mark."""
    known = {**_constant_entries(), **_input_entries(inputs, provisional)}
    pending = load_equations()
    while True:
        ready = tuple(item for item in pending if all(key in known for key in item.inputs))
        if not ready:
            break
        known = {**known, **{item.output: _evaluate(item, known) for item in ready}}
        pending = tuple(item for item in pending if item not in ready)
    return Ledger(entries=tuple(known.values()), missing=tuple(item.output for item in pending))
