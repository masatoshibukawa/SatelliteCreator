"""The design loop: analyse, let agents respond, change the design, and analyse again.

Agents only propose changes. Every number still comes from the design core, and the loop decides
when to stop. An agent is anything with `name` and `review`, so a Claude-backed agent can replace
or join the rule-based one here. Requirements the loop cannot supply are returned as questions.

Run `python -m satellitecreator.iteration --prompt "..."` to see the log.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from enum import StrEnum
from typing import Protocol

from satellitecreator.catalog import load_surface_finishes, reference_bus
from satellitecreator.core.checks import CheckState, evaluate_checks
from satellitecreator.core.ledger import Ledger
from satellitecreator.intake import build_intake
from satellitecreator.project import Project
from satellitecreator.requirements import RequirementStatus
from satellitecreator.schema import Frozen
from satellitecreator.simulation import project_ledger

MAX_ITERATIONS = 20
_HEATER_STEP_W = 1.0
_MAX_HEATER_W = 10.0
_NEEDS_BUS_QUESTION = (
    "搭載機器の質量と消費電力を教えてください。今は 3U の機器構成だけ登録しています"
)


class LoopStatus(StrEnum):
    CONVERGED = "converged"
    NO_SOLUTION = "no_solution"
    LIMIT_REACHED = "limit_reached"
    NEEDS_INPUT = "needs_input"


class AgentMessage(Frozen):
    agent: str
    text: str


class DesignChange(Frozen):
    message: AgentMessage
    project: Project


class IterationRecord(Frozen):
    number: int
    temperature_margin_k: float | None = None
    failed_checks: tuple[str, ...] = ()
    messages: tuple[AgentMessage, ...] = ()


class DesignLoopResult(Frozen):
    status: LoopStatus
    project: Project
    iterations: tuple[IterationRecord, ...] = ()
    questions: tuple[str, ...] = ()


class DesignAgent(Protocol):
    name: str

    def review(
        self, project: Project, ledger: Ledger, history: tuple[IterationRecord, ...]
    ) -> DesignChange | None:
        """Returns a proposed change, or None when this agent has nothing to change."""


def _with_design(project: Project, **changes: object) -> Project:
    return project.model_copy(update={"design": project.design.model_copy(update=changes)})


class ThermalAgent:
    """Too hot: move to a finish with a lower absorptivity to emissivity ratio. Too cold: heat."""

    name = "熱"

    def review(
        self, project: Project, ledger: Ledger, history: tuple[IterationRecord, ...]
    ) -> DesignChange | None:
        hot_margin_k = ledger.value("allowable_max_temperature_k") - ledger.value(
            "orbit_max_temperature_k"
        )
        if hot_margin_k < 0:
            return self._cooler_surface(project, ledger, hot_margin_k)
        cold_margin_k = ledger.value("orbit_min_temperature_k") - ledger.value(
            "allowable_min_temperature_k"
        )
        if cold_margin_k < 0:
            return self._more_heat(project, cold_margin_k)
        return None

    def _cooler_surface(
        self, project: Project, ledger: Ledger, hot_margin_k: float
    ) -> DesignChange | None:
        current_ratio = ledger.value("surface_absorptivity_ratio") / ledger.value(
            "surface_emissivity_ratio"
        )
        cooler = [
            item
            for item in load_surface_finishes()
            if item.absorptivity / item.emissivity < current_ratio
        ]
        if not cooler:
            return None
        choice = max(cooler, key=lambda item: item.absorptivity / item.emissivity)
        text = f"高温側が {-hot_margin_k:.1f} K 超過。表面を{choice.name}に変更"
        return DesignChange(
            message=AgentMessage(agent=self.name, text=text),
            project=_with_design(project, surface=choice.name),
        )

    def _more_heat(self, project: Project, cold_margin_k: float) -> DesignChange | None:
        heater_w = project.design.heater_power_w + _HEATER_STEP_W
        if heater_w > _MAX_HEATER_W:
            return None
        text = f"低温側が {-cold_margin_k:.1f} K 不足。ヒータを {heater_w:g} W に増加"
        return DesignChange(
            message=AgentMessage(agent=self.name, text=text),
            project=_with_design(project, heater_power_w=heater_w),
        )


DEFAULT_AGENTS: tuple[DesignAgent, ...] = (ThermalAgent(),)


def _open_questions(project: Project) -> tuple[str, ...]:
    return tuple(
        item.question for item in project.requirements if item.status is RequirementStatus.OPEN
    )


def _failed_checks(ledger: Ledger) -> tuple[str, ...]:
    return tuple(item.id for item in evaluate_checks(ledger) if item.state is CheckState.FAILED)


def _first_change(
    agents: Sequence[DesignAgent],
    project: Project,
    ledger: Ledger,
    history: tuple[IterationRecord, ...],
) -> DesignChange | None:
    replies = (agent.review(project, ledger, history) for agent in agents)
    return next((item for item in replies if item is not None), None)


def run_design_loop(
    project: Project,
    agents: Sequence[DesignAgent] = DEFAULT_AGENTS,
    max_iterations: int = MAX_ITERATIONS,
) -> DesignLoopResult:
    questions = _open_questions(project)
    if project.design is None:
        return DesignLoopResult(status=LoopStatus.NEEDS_INPUT, project=project, questions=questions)
    if reference_bus(project.design.form_factor) is None:
        return DesignLoopResult(
            status=LoopStatus.NEEDS_INPUT,
            project=project,
            questions=(_NEEDS_BUS_QUESTION, *questions),
        )

    current = project
    history: tuple[IterationRecord, ...] = ()
    for number in range(1, max_iterations + 1):
        ledger = project_ledger(current)
        record = IterationRecord(
            number=number,
            temperature_margin_k=ledger.value("temperature_margin_k"),
            failed_checks=_failed_checks(ledger),
        )
        if not record.failed_checks:
            return _finish(LoopStatus.CONVERGED, current, (*history, record), questions)
        if number == max_iterations:
            return _finish(LoopStatus.LIMIT_REACHED, current, (*history, record), questions)
        change = _first_change(agents, current, ledger, history)
        if change is None:
            return _finish(LoopStatus.NO_SOLUTION, current, (*history, record), questions)
        current = change.project
        history = (*history, record.model_copy(update={"messages": (change.message,)}))
    raise ValueError("max_iterations must be at least 1")


def _finish(
    status: LoopStatus,
    project: Project,
    iterations: tuple[IterationRecord, ...],
    questions: tuple[str, ...],
) -> DesignLoopResult:
    return DesignLoopResult(
        status=status, project=project, iterations=iterations, questions=questions
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the design loop for a request.")
    parser.add_argument("--prompt", required=True, help="the satellite request text")
    args = parser.parse_args(argv)

    result = run_design_loop(build_intake(args.prompt, {}).project)
    for record in result.iterations:
        sys.stdout.write(f"{record.number}: 余裕 {record.temperature_margin_k:.1f} K\n")
        for message in record.messages:
            sys.stdout.write(f"   {message.agent}: {message.text}\n")
    sys.stdout.write(f"結果: {result.status}\n")
    for question in result.questions:
        sys.stdout.write(f"質問: {question}\n")
    return 0 if result.status is LoopStatus.CONVERGED else 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
