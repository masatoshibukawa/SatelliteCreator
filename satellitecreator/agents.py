"""A Claude-backed design agent, kept cheap on purpose.

Claude only chooses among allowed moves; the design core still produces every number. It is
called only when the thermal check fails, at most a few times per loop, and identical situations
are answered from a cache. Anything unusable falls back to the rule-based agent.

Off by default. Set SATELLITECREATOR_USE_CLAUDE=1 and ANTHROPIC_API_KEY to enable it.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from functools import cache
from typing import Any, Literal

import anthropic
from pydantic import BaseModel

from satellitecreator.catalog import load_surface_finishes
from satellitecreator.core.ledger import Ledger
from satellitecreator.design import SatelliteDesign
from satellitecreator.intake import build_intake
from satellitecreator.iteration import (
    DEFAULT_AGENTS,
    MAX_HEATER_W,
    AgentMessage,
    DesignAgent,
    DesignChange,
    IterationRecord,
    PowerAgent,
    ThermalAgent,
    run_design_loop,
    with_design,
)
from satellitecreator.project import Project

logger = logging.getLogger(__name__)

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 1024
MAX_CALLS_PER_LOOP = 3
MAX_CALLS_PER_PROCESS = 30
_REQUEST_TIMEOUT_S = 20.0
_MAX_REASON_LENGTH = 80
_AGENT_NAME = "熱（Claude）"
_SYSTEM = (
    "You are the thermal engineer of a CubeSat design team. Choose one design move that fixes "
    "the temperature problem. For a hot problem set a radiator patch: `surface` is its "
    "material name only and `radiator_ratio` the share of the body it covers, "
    "from 0 to 1. For a cold problem raise "
    "`heater_power_w`. A radiator removes body solar cells and makes the cold case colder, and "
    "heater power uses energy, so use the least that works. "
    "Write `reason` in Japanese, in one short sentence."
)


class ThermalMove(BaseModel):
    action: Literal["surface", "heater", "stop"]
    surface: str | None
    radiator_ratio: float | None
    heater_power_w: float | None
    reason: str


def _radiator_text(design: SatelliteDesign) -> str:
    return f"{design.surface} {design.radiator_ratio:.0%}" if design.surface else "なし"


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
        f"現在の放熱面 {_radiator_text(design)}、ヒータ {design.heater_power_w:g} W"
        f"（上限 {MAX_HEATER_W:g} W）。本体は太陽電池セル(α0.92,ε0.8)。放熱面の材料: {finishes}"
    )


class ClaudeThermalAgent:
    name = _AGENT_NAME

    def __init__(self, client: Any, model: str = MODEL) -> None:
        self._client = client
        self._model = model
        self._fallback = ThermalAgent()
        self._answers: dict[str, ThermalMove | None] = {}
        self._failures: dict[str, str] = {}
        self.spent_calls = 0
        self.stop_reasons: tuple[str, ...] = ()
        self.input_tokens = 0
        self.output_tokens = 0

    def review(
        self, project: Project, ledger: Ledger, history: tuple[IterationRecord, ...]
    ) -> DesignChange | None:
        rule_change = self._fallback.review(project, ledger, history)
        if rule_change is None:
            return None
        prompt = _prompt(project, ledger)
        move = self._move(prompt, history)
        if move is None:
            return _with_note(rule_change, self._failures.get(prompt, ""))
        verdict = self._judge(move, project, rule_change)
        if isinstance(verdict, DesignChange):
            return verdict
        logger.warning("Claude move rejected: %s", verdict)
        return _with_note(rule_change, verdict)

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
        """Any failure here falls back to the rules, so one answer cannot stop the session."""
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "disabled"},
                output_config={"effort": "low"},
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=ThermalMove,
            )
        except (anthropic.AnthropicError, ValueError) as error:
            self._failures[prompt] = f"{type(error).__name__} のため"
            logger.warning("Claude call failed: %s", type(error).__name__)
            return None
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        self.stop_reasons = (*self.stop_reasons, str(response.stop_reason))
        if response.parsed_output is None:
            self._failures[prompt] = f"応答なし（{response.stop_reason}）"
        return response.parsed_output

    def _judge(
        self, move: ThermalMove, project: Project, rule_change: DesignChange
    ) -> DesignChange | str:
        """Returns the change, or why the move does not answer the diagnosed problem."""
        design = project.design
        too_cold = rule_change.project.design.heater_power_w > design.heater_power_w
        message = AgentMessage(agent=_AGENT_NAME, text=move.reason[:_MAX_REASON_LENGTH])
        if move.action == "surface":
            return self._judge_surface(move, project, too_cold, message)
        if move.action == "heater":
            if not too_cold:
                return "高温の問題にヒータを提案"
            power_w = move.heater_power_w
            if power_w is None or not design.heater_power_w < power_w <= MAX_HEATER_W:
                return f"ヒータ {power_w} W は範囲外"
            return DesignChange(
                message=message, project=with_design(project, heater_power_w=power_w)
            )
        return "変更なしを提案"

    def _judge_surface(
        self, move: ThermalMove, project: Project, too_cold: bool, message: AgentMessage
    ) -> DesignChange | str:
        if too_cold:
            return "低温の問題に放熱面を提案"
        design = project.design
        usable = {
            item.name for item in load_surface_finishes() if item.absorptivity < item.emissivity
        }
        # The model sometimes copies the whole list entry, such as "黒塗り(α0.67,ε0.89)".
        surface = (move.surface or "").split("(")[0].strip()
        if surface not in usable:
            return f"{move.surface} は放熱面に使えない"
        current_ratio = design.radiator_ratio if design.surface else 0.0
        ratio = move.radiator_ratio
        if ratio is None or not current_ratio < ratio <= 1:
            return f"面積比 {ratio} は現在の {current_ratio:.2f} より大きくない"
        return DesignChange(
            message=message,
            project=with_design(project, surface=surface, radiator_ratio=ratio),
        )


def _with_note(change: DesignChange, reason: str) -> DesignChange:
    if not reason:
        return change
    text = f"{change.message.text}（Claude の案を不採用: {reason}）"
    return change.model_copy(update={"message": change.message.model_copy(update={"text": text})})


@cache
def _claude_agents() -> tuple[DesignAgent, ...]:
    client = anthropic.Anthropic(max_retries=1, timeout=_REQUEST_TIMEOUT_S)
    return (ClaudeThermalAgent(client), PowerAgent())


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
    result = run_design_loop(build_intake(args.prompt, {}).project, agents=(agent, PowerAgent()))
    for record in result.iterations:
        sys.stdout.write(f"{record.number}: 余裕 {record.temperature_margin_k:.1f} K\n")
        for message in record.messages:
            sys.stdout.write(f"   {message.agent}: {message.text}\n")
    sys.stdout.write(
        f"結果: {result.status}、API {agent.spent_calls} 回、"
        f"入力 {agent.input_tokens} / 出力 {agent.output_tokens} トークン、"
        f"stop_reason {agent.stop_reasons}\n"
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
