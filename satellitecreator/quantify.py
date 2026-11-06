"""Turns a qualitative request into quantitative assumptions with Claude.

Claude only fills what the text implies and says why. Each value becomes an assumed requirement,
never a confirmed one, and anything the user states wins. Empty fields stay as questions. One
small call per distinct request, off by default, and any failure just leaves the questions.
"""

from __future__ import annotations

import logging
import os
from functools import cache
from typing import Any, Literal

import anthropic
from pydantic import BaseModel

from satellitecreator.agents import MODEL
from satellitecreator.design import load_scope_limits

logger = logging.getLogger(__name__)

MAX_TOKENS = 512
MAX_READS_PER_PROCESS = 30
_REQUEST_TIMEOUT_S = 20.0
_SYSTEM = (
    "You turn a satellite request into numbers for a CubeSat concept design in low Earth orbit. "
    "Give your engineering estimate for each field that the mission purpose implies, even when "
    "the text states no number: observing at the same local time implies a sun-synchronous "
    "orbit, and a small satellite implies a small form factor. Leave a field null only when "
    "nothing in the text bears on it. "
    "form_factor is one of 1U, 2U, 3U, 6U. Altitude is 400 to 2000 km. "
    "Write `rationale` in Japanese, in one short sentence."
)


class RequirementDraft(BaseModel):
    form_factor: Literal["1U", "2U", "3U", "6U"] | None
    altitude_km: float | None
    inclination_deg: float | None
    mission_months: float | None
    rationale: str


def draft_answers(draft: RequirementDraft) -> tuple[dict[str, str], dict[str, str]]:
    """Returns the values as answers, and the reason for each, dropping out-of-scope ones."""
    limits = load_scope_limits()
    answers: dict[str, str] = {}
    if draft.form_factor is not None:
        answers["form_factor"] = draft.form_factor
    altitude_km = draft.altitude_km
    lowest_km = limits.leo_min_altitude.value_m / 1000
    highest_km = limits.leo_max_altitude.value_m / 1000
    if altitude_km is not None and lowest_km <= altitude_km <= highest_km:
        answers["altitude"] = f"{altitude_km:g} km"
    if draft.inclination_deg is not None and 0 <= draft.inclination_deg <= 180:
        answers["inclination"] = f"{draft.inclination_deg:g} 度"
    if draft.mission_months is not None and draft.mission_months > 0:
        answers["mission_duration"] = f"{draft.mission_months:g} か月"
    return answers, dict.fromkeys(answers, draft.rationale)


class ClaudeRequirementReader:
    def __init__(self, client: Any, model: str = MODEL) -> None:
        self._client = client
        self._model = model
        self._drafts: dict[str, RequirementDraft | None] = {}
        self.spent_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def read(self, prompt: str) -> RequirementDraft | None:
        if prompt in self._drafts:
            return self._drafts[prompt]
        if self.spent_calls >= MAX_READS_PER_PROCESS:
            return None
        self.spent_calls += 1
        draft = self._ask(prompt)
        self._drafts[prompt] = draft
        return draft

    def _ask(self, prompt: str) -> RequirementDraft | None:
        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=MAX_TOKENS,
                thinking={"type": "disabled"},
                output_config={"effort": "low"},
                system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
                output_format=RequirementDraft,
            )
        except (anthropic.AnthropicError, ValueError) as error:
            logger.warning("Requirement reading failed: %s", type(error).__name__)
            return None
        self.input_tokens += response.usage.input_tokens
        self.output_tokens += response.usage.output_tokens
        return response.parsed_output


@cache
def _claude_reader() -> ClaudeRequirementReader:
    return ClaudeRequirementReader(anthropic.Anthropic(max_retries=1, timeout=_REQUEST_TIMEOUT_S))


def requirement_reader() -> ClaudeRequirementReader | None:
    enabled = os.environ.get("SATELLITECREATOR_USE_CLAUDE") == "1"
    return _claude_reader() if enabled and os.environ.get("ANTHROPIC_API_KEY") else None
