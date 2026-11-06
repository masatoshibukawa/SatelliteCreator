from types import SimpleNamespace

import anthropic
import pytest

from satellitecreator.intake import build_intake
from satellitecreator.quantify import (
    MAX_READS_PER_PROCESS,
    ClaudeRequirementReader,
    RequirementDraft,
    draft_answers,
    requirement_reader,
)
from satellitecreator.requirements import RequirementStatus
from satellitecreator.session import run_session

VAGUE = "毎日同じ時刻に日本の森林を撮影したい小さな衛星"


def _draft(**overrides) -> RequirementDraft:
    fields = {
        "form_factor": "3U",
        "altitude_km": 550.0,
        "inclination_deg": 97.6,
        "mission_months": 12.0,
        "rationale": "同じ時刻の撮影には太陽同期軌道が向く",
    }
    return RequirementDraft(**{**fields, **overrides})


class FakeClient:
    """Stands in for the API, so no test spends money."""

    def __init__(self, draft=None, error=None):
        self.draft = draft
        self.error = error
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        usage = SimpleNamespace(input_tokens=100, output_tokens=20)
        return SimpleNamespace(parsed_output=self.draft, usage=usage, stop_reason="end_turn")


def test_draft_becomes_answers_and_a_rationale():
    answers, assumed = draft_answers(_draft())

    assert answers == {
        "form_factor": "3U",
        "altitude": "550 km",
        "inclination": "97.6 度",
        "mission_duration": "12 か月",
    }
    assert set(assumed) == {"form_factor", "altitude", "inclination", "mission_duration"}


def test_empty_fields_stay_for_the_user_to_answer():
    answers, _ = draft_answers(_draft(altitude_km=None, form_factor=None))

    assert set(answers) == {"inclination", "mission_duration"}


@pytest.mark.parametrize(
    ("overrides", "dropped"),
    [
        ({"altitude_km": 100.0}, "altitude"),
        ({"altitude_km": 5000.0}, "altitude"),
        ({"inclination_deg": 200.0}, "inclination"),
        ({"mission_months": 0.0}, "mission_duration"),
    ],
)
def test_values_outside_the_scope_are_dropped(overrides, dropped):
    answers, _ = draft_answers(_draft(**overrides))

    assert dropped not in answers


def test_claude_values_are_recorded_as_assumptions_with_a_reason():
    answers, assumed = draft_answers(_draft())

    project = build_intake(VAGUE, answers, assumed).project

    altitude = next(item for item in project.requirements if item.id == "SR-001")
    assert altitude.status is RequirementStatus.ASSUMED
    assert "太陽同期" in altitude.rationale


def test_assumed_question_is_shown_as_assumed():
    answers, assumed = draft_answers(_draft())

    question = next(
        item for item in build_intake(VAGUE, answers, assumed).questions if item.id == "altitude"
    )

    assert question.assumed
    assert question.answered


def test_reader_makes_one_small_request_per_text():
    client = FakeClient(_draft())
    reader = ClaudeRequirementReader(client)

    first = reader.read(VAGUE)
    second = reader.read(VAGUE)

    assert first == second
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] <= 512
    assert call["thinking"] == {"type": "disabled"}


def test_reader_stops_at_its_budget():
    client = FakeClient(_draft())
    reader = ClaudeRequirementReader(client)
    reader.spent_calls = MAX_READS_PER_PROCESS

    assert reader.read(VAGUE) is None
    assert client.calls == []


@pytest.mark.parametrize(
    "client",
    [FakeClient(error=anthropic.APIConnectionError(request=None)), FakeClient(draft=None)],
)
def test_reader_failure_leaves_the_questions_to_the_user(client):
    assert ClaudeRequirementReader(client).read(VAGUE) is None


def test_reader_survives_a_truncated_answer():
    try:
        RequirementDraft.model_validate_json('{"form_fac')
    except ValueError as error:
        client = FakeClient(error=error)

    assert ClaudeRequirementReader(client).read(VAGUE) is None


def test_reader_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("SATELLITECREATOR_USE_CLAUDE", raising=False)

    assert requirement_reader() is None


def test_reader_is_on_when_asked_for(monkeypatch):
    monkeypatch.setenv("SATELLITECREATOR_USE_CLAUDE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    assert isinstance(requirement_reader(), ClaudeRequirementReader)


def _session_with(monkeypatch, client):
    reader = ClaudeRequirementReader(client)
    monkeypatch.setattr("satellitecreator.session.requirement_reader", lambda: reader)


def test_session_turns_a_vague_request_into_a_design(monkeypatch):
    _session_with(monkeypatch, FakeClient(_draft()))

    result = run_session(VAGUE, {})

    assert result.satellite.form_factor == "3U"
    assert any(item.status == "assumed" for item in result.requirements)


def test_user_answer_wins_over_claude(monkeypatch):
    _session_with(monkeypatch, FakeClient(_draft()))

    result = run_session(VAGUE, {"altitude": "600 km"})

    altitude = next(item for item in result.requirements if item.id == "SR-001")
    assert altitude.status is RequirementStatus.CONFIRMED
    assert "600" in altitude.statement


def test_stated_value_in_the_request_wins_over_claude(monkeypatch):
    _session_with(monkeypatch, FakeClient(_draft()))

    result = run_session(f"高度 450 km の{VAGUE}", {})

    altitude = next(item for item in result.requirements if item.id == "SR-001")
    assert altitude.status is RequirementStatus.CONFIRMED
    assert "450" in altitude.statement


def test_settled_request_makes_no_call(monkeypatch):
    client = FakeClient(_draft())
    _session_with(monkeypatch, client)
    prompt = "高度 500 km、傾斜角 97 度の 3U 衛星。ミッション期間 6 か月"

    run_session(prompt, {})

    assert client.calls == []


def test_failed_read_leaves_the_session_working(monkeypatch):
    _session_with(monkeypatch, FakeClient(draft=None))

    assert run_session(VAGUE, {}).satellite is None


def test_refused_request_never_reaches_claude(monkeypatch):
    client = FakeClient(_draft())
    _session_with(monkeypatch, client)

    run_session("ミサイルを追尾する衛星", {})

    assert client.calls == []
