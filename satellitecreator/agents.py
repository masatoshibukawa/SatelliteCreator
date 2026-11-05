"""A Claude-backed design agent, kept cheap on purpose.

Claude only chooses among allowed moves; the design core still produces every number. It is
called only when the thermal check fails, at most a few times per loop, and identical situations
are answered from a cache. Anything unusable falls back to the rule-based agent.

Off by default. Set SATELLITECREATOR_USE_CLAUDE=1 and ANTHROPIC_API_KEY to enable it.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from functools import cache
from typing import Any, Literal

import anthropic
from pydantic import BaseModel

from satellitecreator.catalog import load_surface_finishes
from satellitecreator.core.ledger import Ledger
from satellitecreator.intake import build_intake
from satellitecreator.iteration import (
    DEFAULT_AGENTS,
    MAX_HEATER_W,
    AgentMessage,
    DesignAgent,
    DesignChange,
    IterationRecord,
    ThermalAgent,
    run_design_loop,
    with_design,
)
from satellitecreator.project import Project

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 512
MAX_CALLS_PER_LOOP = 3
MAX_CALLS_PER_PROCESS = 30
_REQUEST_TIMEOUT_S = 20.0
_MAX_REASON_LENGTH = 80
_AGENT_NAME = "熱（Claude）"
_SYSTEM = (
    "You are the thermal engineer of a CubeSat design team. Choose one design move that fixes "
    "the temperature problem. Prefer a surface change for a hot problem and more heater power "
    "for a cold one. Heater power adds electrical load, so use the least that works. "
    "Write `reason` in Japanese, in one short sentence."
)


class ThermalMove(BaseModel):
    action: Literal["surface", "heater", "stop"]
    surface: str | None
    heater_power_w: float | None
    reason: str


def _prompt(project: Project, ledger: Ledger) -> str:
    design = project.design
    finishes = "、".join(
        f"{item.name}(α{item.absorptivity},ε{item.emissivity})" for item in load_surface_finishes()
    )
    hot_margin_k = ledger.value("allowable_max_temperature_k") - ledger.value(
        "orbit_max_temperature_k"
    )
    cold_margin_k = ledger.value("orbit_min_temperature_k") - ledger.value(
        "allowable_min_temperature_k"
    )
    return (
        f"高温余裕 {hot_margin_k:.1f} K、低温余裕 {cold_margin_k:.1f} K。"
        f"現在の表面 {design.surface or '太陽電池セル'}、ヒータ {design.heater_power_w:g} W"
        f"（上限 {MAX_HEATER_W:g} W）。選べる表面: {finishes}"
    )


class ClaudeThermalAgent:
    name = _AGENT_NAME

    def __init__(self, client: Any, model: str = MODEL) -> None:
        self._client = client
        self._model = model
        self._fallback = ThermalAgent()
        self._answers: dict[str, ThermalMove | None] = {}
        self.spent_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def review(
        self, project: Project, ledger: Ledger, history: tuple[IterationRecord, ...]
    ) -> DesignChange | None:
        rule_change = self._fallback.review(project, ledger, history)
        if rule_change is None:
            return None
        move = self._move(_prompt(project, ledger), history)
        return self._apply(move, project) or rule_change

    def _move(self, prompt: str, history: tuple[IterationRecord, ...]) -> ThermalMove | None:
        if prompt in self._answers:
            return self._answers[prompt]
        used_in_loop = sum(
            item.agent == _AGENT_NAME for record in history for item in record.messages
        )
        if used_in_loop >= MAX_CALLS_PER_LOOP or self.spent_calls >= MAX_CALLS_PER_PROCESS:
            return None
        self.spent_calls += 1
        move = self._ask(prompt)
        self._answers[prompt] = move
        return move

    def _ask(self, prompt: str) -> ThermalMove | None:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                output_config={"effort": "low"},
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=ThermalMove,
            )
        except anthropic.APIError as error:
            sys.stderr.write(f"Claude agent fell back to the rules: {type(error).__name__}\n")
            return None
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        return response.parsed_output

    def _apply(self, move: ThermalMove | None, project: Project) -> DesignChange | None:
        if move is None:
            return None
        message = AgentMessage(agent=_AGENT_NAME, text=move.reason[:_MAX_REASON_LENGTH])
        if move.action == "surface":
            names = {item.name for item in load_surface_finishes()}
            if move.surface not in names:
                return None
            return DesignChange(message=message, project=with_design(project, surface=move.surface))
        if move.action == "heater":
            power_w = move.heater_power_w
            if power_w is None or not project.design.heater_power_w < power_w <= MAX_HEATER_W:
                return None
            return DesignChange(
                message=message, project=with_design(project, heater_power_w=power_w)
            )
        return None


@cache
def _claude_agents() -> tuple[DesignAgent, ...]:
    client = anthropic.Anthropic(max_retries=1, timeout=_REQUEST_TIMEOUT_S)
    return (ClaudeThermalAgent(client),)


def design_agents() -> tuple[DesignAgent, ...]:
    enabled = os.environ.get("SATELLITECREATOR_USE_CLAUDE") == "1"
    if enabled and os.environ.get("ANTHROPIC_API_KEY"):
        return _claude_agents()
    return DEFAULT_AGENTS


def main(argv: Sequence[str] | None = None) -> int:  # pragma: no cover
    parser = argparse.ArgumentParser(description="Run the design loop with the Claude agent.")
    parser.add_argument("--prompt", required=True)
    args = parser.parse_args(argv)
    agent = ClaudeThermalAgent(anthropic.Anthropic(max_retries=1, timeout=_REQUEST_TIMEOUT_S))
    result = run_design_loop(build_intake(args.prompt, {}).project, agents=(agent,))
    for record in result.iterations:
        sys.stdout.write(f"{record.number}: 余裕 {record.temperature_margin_k:.1f} K\n")
        for message in record.messages:
            sys.stdout.write(f"   {message.agent}: {message.text}\n")
    sys.stdout.write(
        f"結果: {result.status}、API {agent.spent_calls} 回、"
        f"入力 {agent.input_tokens} / 出力 {agent.output_tokens} トークン\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
