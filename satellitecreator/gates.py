"""Deterministic review gates.

A gate re-runs the rules of every earlier review, so a change made after a review cannot slip
through a later one. PDR and CDR read the design core, so they cannot pass on paperwork alone.
"""

from __future__ import annotations

from collections.abc import Callable

from satellitecreator.core.checks import CheckState, evaluate_checks
from satellitecreator.design import check_scope
from satellitecreator.process import Review, review_order
from satellitecreator.project import Project, SuccessLevel
from satellitecreator.requirements import (
    REQUIRED_FUNCTIONS,
    Function,
    RequirementLevel,
    RequirementStatus,
)
from satellitecreator.schema import Finding, Frozen
from satellitecreator.simulation import BlockState, block_statuses, project_ledger

Rule = Callable[[Project], tuple[Finding, ...]]

# The orbit is chosen at system level: the contest rules list no orbit subsystem (Annex 1, 5.3).
_SYSTEM_ONLY_FUNCTIONS = frozenset({Function.ORBIT})

_LEVEL_LABELS = {
    RequirementLevel.MISSION: "ミッション",
    RequirementLevel.SYSTEM: "システム",
    RequirementLevel.SUBSYSTEM: "サブシステム",
}


class GateResult(Frozen):
    review: Review
    findings: tuple[Finding, ...] = ()

    @property
    def passed(self) -> bool:
        return not self.findings


class GateBlockedError(Exception):
    def __init__(self, result: GateResult) -> None:
        codes = ", ".join(item.code for item in result.findings)
        super().__init__(f"{result.review} blocked: {codes}")
        self.result = result


def _mission_defined(project: Project) -> tuple[Finding, ...]:
    if project.mission is None:
        return (Finding(code="missing_mission", message="ミッション定義がありません"),)
    levels = {item.level for item in project.mission.success_criteria}
    if SuccessLevel.MINIMUM not in levels:
        return (
            Finding(
                code="missing_minimum_success",
                message="ミニマムサクセスの基準がありません",
            ),
        )
    return ()


def _has_requirements(level: RequirementLevel, code: str) -> Rule:
    def rule(project: Project) -> tuple[Finding, ...]:
        if project.at_level(level):
            return ()
        return (Finding(code=code, message=f"{_LEVEL_LABELS[level]}要求がありません"),)

    return rule


def _settled(*levels: RequirementLevel) -> Rule:
    def rule(project: Project) -> tuple[Finding, ...]:
        return tuple(
            Finding(
                code="open_requirement",
                message=f"未定の要求があります: {item.question}",
                subject=item.id,
            )
            for level in levels
            for item in project.at_level(level)
            if item.status is RequirementStatus.OPEN
        )

    return rule


def _traced(level: RequirementLevel, parent_level: RequirementLevel) -> Rule:
    def rule(project: Project) -> tuple[Finding, ...]:
        valid_parents = {item.id for item in project.at_level(parent_level)}
        return tuple(
            Finding(
                code="broken_trace",
                message=f"親となる{_LEVEL_LABELS[parent_level]}要求が見つかりません: {parent}",
                subject=item.id,
            )
            for item in project.at_level(level)
            for parent in item.parents
            if parent not in valid_parents
        )

    return rule


def _flowed_down(
    level: RequirementLevel,
    child_level: RequirementLevel,
    code: str,
    exempt_functions: frozenset[Function] = frozenset(),
) -> Rule:
    def rule(project: Project) -> tuple[Finding, ...]:
        covered = {parent for item in project.at_level(child_level) for parent in item.parents}
        return tuple(
            Finding(
                code=code,
                message=f"{_LEVEL_LABELS[child_level]}要求に展開されていません",
                subject=item.id,
            )
            for item in project.at_level(level)
            if item.id not in covered and item.function not in exempt_functions
        )

    return rule


def _functions_covered(project: Project) -> tuple[Finding, ...]:
    covered = {item.function for item in project.at_level(RequirementLevel.SYSTEM)}
    return tuple(
        Finding(
            code="uncovered_function",
            message="この機能に対するシステム要求がありません",
            subject=function,
        )
        for function in sorted(REQUIRED_FUNCTIONS - covered)
    )


def _operations_concept_present(project: Project) -> tuple[Finding, ...]:
    if project.operations_concept:
        return ()
    return (Finding(code="missing_operations_concept", message="運用コンセプトがありません"),)


def _design_in_scope(project: Project) -> tuple[Finding, ...]:
    if project.design is None:
        return (Finding(code="missing_design", message="システム仕様となる設計がありません"),)
    return check_scope(project.design)


def _analysis_passed(project: Project) -> tuple[Finding, ...]:
    """PDR: every block is calculated and no check that ran has failed."""
    ledger = project_ledger(project)
    missing = tuple(
        Finding(code="analysis_missing", message="解析の結果がありません", subject=item.block)
        for item in block_statuses(ledger)
        if item.state is not BlockState.DONE
    )
    failed = tuple(
        Finding(code="check_failed", message=f"不合格です: {item.label}", subject=item.id)
        for item in evaluate_checks(ledger)
        if item.state is CheckState.FAILED
    )
    return missing + failed


def _all_checks_ran(project: Project) -> tuple[Finding, ...]:
    """CDR: nothing may be left unchecked."""
    return tuple(
        Finding(code="check_not_run", message=f"未実行です: {item.label}", subject=item.id)
        for item in evaluate_checks(project_ledger(project))
        if item.state is CheckState.NOT_RUN
    )


_RULES: dict[Review, tuple[Rule, ...]] = {
    Review.MDR: (
        _mission_defined,
        _has_requirements(RequirementLevel.MISSION, "no_mission_requirement"),
    ),
    Review.SRR: (
        _settled(RequirementLevel.MISSION, RequirementLevel.SYSTEM),
        _has_requirements(RequirementLevel.SYSTEM, "no_system_requirement"),
        _traced(RequirementLevel.SYSTEM, RequirementLevel.MISSION),
        _flowed_down(
            RequirementLevel.MISSION,
            RequirementLevel.SYSTEM,
            "uncovered_mission_requirement",
        ),
        _functions_covered,
        _operations_concept_present,
    ),
    Review.SDR: (
        _settled(RequirementLevel.SUBSYSTEM),
        _has_requirements(RequirementLevel.SUBSYSTEM, "no_subsystem_requirement"),
        _traced(RequirementLevel.SUBSYSTEM, RequirementLevel.SYSTEM),
        _flowed_down(
            RequirementLevel.SYSTEM,
            RequirementLevel.SUBSYSTEM,
            "uncovered_system_requirement",
            exempt_functions=_SYSTEM_ONLY_FUNCTIONS,
        ),
        _design_in_scope,
    ),
    Review.PDR: (_analysis_passed,),
    Review.CDR: (_all_checks_ran,),
}


def _order_findings(project: Project, review: Review) -> tuple[Finding, ...]:
    if review in project.passed_reviews:
        return (Finding(code="already_passed", message="この審査は通過済みです", subject=review),)
    order = review_order()
    if project.passed_reviews != order[: order.index(review)]:
        return (
            Finding(
                code="previous_review_not_passed",
                message="前の審査を通過していません",
                subject=review,
            ),
        )
    return ()


def evaluate_gate(project: Project, review: Review) -> GateResult:
    order = review_order()
    reviews_to_check = order[: order.index(review) + 1]
    rule_findings = tuple(
        finding
        for checked_review in reviews_to_check
        for rule in _RULES[checked_review]
        for finding in rule(project)
    )
    return GateResult(review=review, findings=_order_findings(project, review) + rule_findings)


def pass_review(project: Project, review: Review) -> Project:
    result = evaluate_gate(project, review)
    if not result.passed:
        raise GateBlockedError(result)
    return project.model_copy(update={"passed_reviews": (*project.passed_reviews, review)})
