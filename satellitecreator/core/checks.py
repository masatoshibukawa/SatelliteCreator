"""Consistency checks between physical quantities.

A check whose quantities are not in the ledger has not run. It never counts as passed.
"""

from __future__ import annotations

import math
from enum import StrEnum

from satellitecreator.core.ledger import Ledger
from satellitecreator.core.registry import Block, CheckSpec, load_checks
from satellitecreator.requirements import Comparator
from satellitecreator.schema import Frozen

_EQUALITY_TOLERANCE_RATIO = 1e-9


class CheckState(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"


class CheckResult(Frozen):
    id: str
    label: str
    block: Block
    state: CheckState
    missing: tuple[str, ...] = ()
    provisional: bool = False


def _holds(left: float, comparator: Comparator, right: float) -> bool:
    if comparator is Comparator.AT_MOST:
        return left <= right
    if comparator is Comparator.AT_LEAST:
        return left >= right
    return math.isclose(left, right, rel_tol=_EQUALITY_TOLERANCE_RATIO)


def _evaluate(spec: CheckSpec, ledger: Ledger) -> CheckResult:
    common = {
        "id": spec.id,
        "label": spec.label,
        "block": spec.block,
        "provisional": spec.provisional,
    }
    keys = (spec.left,) if spec.right is None else (spec.left, spec.right)
    missing = tuple(key for key in keys if ledger.value(key) is None)
    if missing:
        return CheckResult(state=CheckState.NOT_RUN, missing=missing, **common)
    right = spec.right_value if spec.right is None else ledger.value(spec.right)
    passed = _holds(ledger.value(spec.left), spec.comparator, right)
    return CheckResult(state=CheckState.PASSED if passed else CheckState.FAILED, **common)


def evaluate_checks(ledger: Ledger) -> tuple[CheckResult, ...]:
    return tuple(_evaluate(spec, ledger) for spec in load_checks())
