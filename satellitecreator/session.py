"""One design session: from a request and answers to everything the UI shows.

The session is recomputed from its inputs on every call, so the same inputs give the same result.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from satellitecreator.agents import design_agents
from satellitecreator.core.checks import CheckResult, evaluate_checks
from satellitecreator.design import check_scope, envelope, form_factor
from satellitecreator.document import Document, build_document
from satellitecreator.flowdown import with_subsystem_requirements
from satellitecreator.gates import evaluate_gate, pass_review
from satellitecreator.intake import QuestionState, build_intake
from satellitecreator.iteration import DesignLoopResult, run_design_loop
from satellitecreator.launch_request import LaunchRequest, build_launch_request
from satellitecreator.process import Phase, Review, load_review_specs
from satellitecreator.project import Project
from satellitecreator.quantify import draft_answers, requirement_reader
from satellitecreator.requirements import Requirement
from satellitecreator.schema import Finding, Frozen
from satellitecreator.simulation import BlockStatus, block_statuses, project_ledger

_REFUSED_TERMS = (
    "兵器",
    "ミサイル",
    "軍事",
    "攻撃",
    "妨害",
    "ジャミング",
    "weapon",
    "missile",
    "jamming",
)
_QUANTIFIABLE_QUESTIONS = frozenset({"form_factor", "altitude", "inclination", "mission_duration"})
_REFUSAL = "兵器、軍事用途、他の衛星への妨害に関わる設計は扱えません。"


class ReviewState(StrEnum):
    PASSED = "passed"
    BLOCKED = "blocked"
    WAITING = "waiting"


class ReviewView(Frozen):
    review: Review
    phase: Phase
    state: ReviewState
    outputs: tuple[str, ...] = ()
    findings: tuple[Finding, ...] = ()


class SatelliteView(Frozen):
    form_factor: str
    width_m: float
    depth_m: float
    length_m: float
    max_mass_kg: float


class SessionResult(Frozen):
    refusal: str = ""
    questions: tuple[QuestionState, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    reviews: tuple[ReviewView, ...] = ()
    simulations: tuple[BlockStatus, ...] = ()
    checks: tuple[CheckResult, ...] = ()
    satellite: SatelliteView | None = None
    scope_findings: tuple[Finding, ...] = ()
    document: Document | None = None
    launch_request: LaunchRequest | None = None
    iteration: DesignLoopResult | None = None


def check_request(text: str) -> str | None:
    lowered = text.lower()
    return _REFUSAL if any(term in lowered for term in _REFUSED_TERMS) else None


def _review_views(project: Project) -> tuple[ReviewView, ...]:
    views: tuple[ReviewView, ...] = ()
    current = project
    blocked = False
    for spec in load_review_specs():
        common = {"review": spec.review, "phase": spec.phase, "outputs": spec.outputs}
        if blocked:
            views += (ReviewView(state=ReviewState.WAITING, **common),)
            continue
        result = evaluate_gate(current, spec.review)
        if result.passed:
            current = pass_review(current, spec.review)
            views += (ReviewView(state=ReviewState.PASSED, **common),)
            continue
        blocked = True
        views += (ReviewView(state=ReviewState.BLOCKED, findings=result.findings, **common),)
    return views


def _satellite_view(form_factor_id: str | None) -> SatelliteView | None:
    if form_factor_id is None:
        return None
    size = envelope(form_factor_id)
    return SatelliteView(
        form_factor=form_factor_id,
        width_m=size.width_m,
        depth_m=size.depth_m,
        length_m=size.length_m,
        max_mass_kg=form_factor(form_factor_id).max_mass_kg,
    )


def _with_claude_assumptions(
    prompt: str, answers: Mapping[str, str]
) -> tuple[Mapping[str, str], dict[str, str]]:
    """Fills only what neither the request nor the user settled. Calls Claude only if needed."""
    reader = requirement_reader()
    if reader is None:
        return answers, {}
    questions = build_intake(prompt, answers).questions
    unsettled = {item.id for item in questions if not item.answered} & _QUANTIFIABLE_QUESTIONS
    draft = reader.read(prompt) if unsettled else None
    if draft is None:
        return answers, {}
    suggested, reasons = draft_answers(draft)
    picked = {key: value for key, value in suggested.items() if key in unsettled}
    return {**answers, **picked}, {key: reasons[key] for key in picked}


def run_session(prompt: str, answers: Mapping[str, str]) -> SessionResult:
    refusal = check_request(" ".join((prompt, *answers.values())))
    if refusal:
        return SessionResult(refusal=refusal)
    filled_answers, assumed = _with_claude_assumptions(prompt, answers)
    intake = build_intake(prompt, filled_answers, assumed)
    loop = run_design_loop(intake.project, agents=design_agents())
    project = with_subsystem_requirements(loop.project)
    ledger = project_ledger(project)
    return SessionResult(
        questions=intake.questions,
        requirements=project.requirements,
        reviews=_review_views(project),
        simulations=block_statuses(
            ledger, project.design.attitude if project.design else "free_rotation"
        ),
        checks=evaluate_checks(ledger),
        satellite=_satellite_view(intake.form_factor),
        scope_findings=check_scope(project.design) if project.design else (),
        document=build_document(project),
        launch_request=build_launch_request(project),
        iteration=loop,
    )
