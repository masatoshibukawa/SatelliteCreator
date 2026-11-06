from types import SimpleNamespace

import anthropic
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.main import app
from satellitecreator import session as session_module
from satellitecreator.agents import (
    MAX_CALLS_PER_LOOP,
    MAX_CALLS_PER_PROCESS,
    ClaudeThermalAgent,
    ThermalMove,
    design_agents,
)
from satellitecreator.intake import build_intake
from satellitecreator.iteration import (
    DEFAULT_AGENTS,
    AgentMessage,
    IterationRecord,
    LoopStatus,
    run_design_loop,
)
from satellitecreator.simulation import project_ledger

BASE = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
HOT = f"{BASE}。消費電力 20 W"


class FakeClient:
    """Stands in for the API, so no test spends money."""

    def __init__(self, *moves, error=None, stop_reason="end_turn"):
        self.stop_reason = stop_reason
        self.moves = list(moves)
        self.error = error
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        move = self.moves.pop(0) if len(self.moves) > 1 else self.moves[0]
        usage = SimpleNamespace(input_tokens=100, output_tokens=20)
        return SimpleNamespace(parsed_output=move, usage=usage, stop_reason=self.stop_reason)


def _surface(name: str, ratio: float | None = 0.4) -> ThermalMove:
    return ThermalMove(
        action="surface", surface=name, radiator_ratio=ratio, heater_power_w=None, reason="理由"
    )


def _heater(power_w: float) -> ThermalMove:
    return ThermalMove(
        action="heater", surface=None, radiator_ratio=None, heater_power_w=power_w, reason="理由"
    )


def _hot_state():
    project = build_intake(HOT, {}).project
    return project, project_ledger(project)


def test_passing_design_makes_no_api_call():
    client = FakeClient(_surface("黒塗り"))

    result = run_design_loop(build_intake(BASE, {}).project, agents=(ClaudeThermalAgent(client),))

    assert result.status is LoopStatus.CONVERGED
    assert client.calls == []


def test_claude_move_is_applied_and_labelled():
    project, ledger = _hot_state()

    change = ClaudeThermalAgent(FakeClient(_surface("カプトン"))).review(project, ledger, ())

    assert change.project.design.surface == "カプトン"
    assert change.message.agent == "熱（Claude）"
    assert change.message.text == "理由"


def test_request_stays_small_and_cheap():
    project, ledger = _hot_state()
    client = FakeClient(_surface("カプトン"))

    ClaudeThermalAgent(client).review(project, ledger, ())

    call = client.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] <= 1024
    assert call["output_config"] == {"effort": "low"}
    assert call["thinking"] == {"type": "disabled"}
    assert len(call["messages"][0]["content"]) < 500


def _cold_project():
    project = build_intake(BASE, {}).project
    return project.model_copy(
        update={
            "design": project.design.model_copy(
                update={"surface": "カプトン", "radiator_ratio": 1.0}
            )
        }
    )


def test_heater_move_above_the_limit_is_refused():
    cold = _cold_project()

    change = ClaudeThermalAgent(FakeClient(_heater(99.0))).review(cold, project_ledger(cold), ())

    assert change.message.agent == "熱"


def test_surface_move_is_refused_for_a_cold_problem():
    cold = _cold_project()

    change = ClaudeThermalAgent(FakeClient(_surface("黒塗り"))).review(
        cold, project_ledger(cold), ()
    )

    assert change.message.agent == "熱"


def test_radiator_cannot_shrink_on_a_hot_problem():
    project = build_intake(HOT, {}).project
    partly = project.model_copy(
        update={
            "design": project.design.model_copy(
                update={"surface": "カプトン", "radiator_ratio": 0.1}
            )
        }
    )

    change = ClaudeThermalAgent(FakeClient(_surface("カプトン", 0.05))).review(
        partly, project_ledger(partly), ()
    )

    assert change.message.agent == "熱"


def test_heater_move_is_applied():
    project = build_intake(BASE, {}).project
    cold = project.model_copy(
        update={
            "design": project.design.model_copy(
                update={"surface": "カプトン", "radiator_ratio": 1.0}
            )
        }
    )

    change = ClaudeThermalAgent(FakeClient(_heater(3.0))).review(cold, project_ledger(cold), ())

    assert change.project.design.heater_power_w == 3.0


@pytest.mark.parametrize(
    "move",
    [
        _surface("金メッキ"),
        _surface("アルミ"),
        _heater(3.0),
        _surface(None),
        _heater(99.0),
        _heater(None),
        _surface("カプトン", None),
        _surface("カプトン", 1.5),
        ThermalMove(
            action="stop", surface=None, radiator_ratio=None, heater_power_w=None, reason="理由"
        ),
        None,
    ],
)
def test_unusable_answer_falls_back_to_the_rule_agent(move):
    project, ledger = _hot_state()

    change = ClaudeThermalAgent(FakeClient(move)).review(project, ledger, ())

    assert change.message.agent == "熱"


def test_api_failure_falls_back_to_the_rule_agent():
    project, ledger = _hot_state()
    client = FakeClient(error=anthropic.APIConnectionError(request=None))

    change = ClaudeThermalAgent(client).review(project, ledger, ())

    assert change.message.agent == "熱"


def _truncated_json_error():
    try:
        ThermalMove.model_validate_json('{"action": "surf')
    except ValidationError as error:
        return error
    raise AssertionError("expected a validation error")


def test_truncated_answer_falls_back_to_the_rule_agent():
    project, ledger = _hot_state()
    agent = ClaudeThermalAgent(FakeClient(error=_truncated_json_error()))

    change = agent.review(project, ledger, ())

    assert change.message.agent == "熱"
    assert "ValidationError" in change.message.text


def test_truncated_answer_does_not_stop_the_session(monkeypatch):
    agent = ClaudeThermalAgent(FakeClient(error=_truncated_json_error()))
    monkeypatch.setattr(session_module, "design_agents", lambda: (agent,))

    response = TestClient(app).post("/session", json={"prompt": HOT})

    assert response.status_code == 200
    assert response.json()["iteration"]["status"] == "converged"


def test_stop_reason_is_recorded():
    project, ledger = _hot_state()
    agent = ClaudeThermalAgent(FakeClient(_surface("カプトン"), stop_reason="max_tokens"))

    agent.review(project, ledger, ())

    assert agent.stop_reasons == ("max_tokens",)


def test_surface_copied_with_its_numbers_is_still_understood():
    project, ledger = _hot_state()

    change = ClaudeThermalAgent(FakeClient(_surface("黒塗り(α0.67,ε0.89)"))).review(
        project, ledger, ()
    )

    assert change.message.agent == "熱（Claude）"
    assert change.project.design.surface == "黒塗り"


def test_rejected_answer_gives_its_reason_in_the_log():
    project, ledger = _hot_state()
    agent = ClaudeThermalAgent(FakeClient(_surface("金メッキ")))

    change = agent.review(project, ledger, ())

    assert "Claude の案を不採用" in change.message.text
    assert "金メッキ" in change.message.text


def test_loop_stops_calling_after_its_budget():
    project, ledger = _hot_state()
    client = FakeClient(_surface("カプトン"))
    message = AgentMessage(agent="熱（Claude）", text="x")
    history = tuple(
        IterationRecord(number=n, messages=(message,)) for n in range(MAX_CALLS_PER_LOOP)
    )

    change = ClaudeThermalAgent(client).review(project, ledger, history)

    assert client.calls == []
    assert change.message.agent == "熱"


def test_process_budget_is_a_hard_limit():
    project, ledger = _hot_state()
    client = FakeClient(_surface("カプトン"))
    agent = ClaudeThermalAgent(client)
    agent.spent_calls = MAX_CALLS_PER_PROCESS

    change = agent.review(project, ledger, ())

    assert client.calls == []
    assert change.message.agent == "熱"


def test_same_situation_is_answered_from_the_cache():
    project, ledger = _hot_state()
    client = FakeClient(_surface("カプトン"))
    agent = ClaudeThermalAgent(client)

    first = agent.review(project, ledger, ())
    second = agent.review(project, ledger, ())

    assert len(client.calls) == 1
    assert first == second


def test_token_use_is_counted():
    project, ledger = _hot_state()
    agent = ClaudeThermalAgent(FakeClient(_surface("カプトン")))

    agent.review(project, ledger, ())

    assert (agent.input_tokens, agent.output_tokens) == (100, 20)


def test_loop_converges_with_claude_moves():
    client = FakeClient(_surface("カプトン", 0.4))

    result = run_design_loop(build_intake(HOT, {}).project, agents=(ClaudeThermalAgent(client),))

    assert result.status is LoopStatus.CONVERGED
    assert len(client.calls) == 1


def test_claude_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv("SATELLITECREATOR_USE_CLAUDE", raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    assert design_agents() == DEFAULT_AGENTS


def test_claude_needs_a_key_even_when_asked_for(monkeypatch):
    monkeypatch.setenv("SATELLITECREATOR_USE_CLAUDE", "1")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    assert design_agents() == DEFAULT_AGENTS


def test_claude_agent_is_used_when_asked_for_and_kept_between_calls(monkeypatch):
    monkeypatch.setenv("SATELLITECREATOR_USE_CLAUDE", "1")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")

    agents = design_agents()

    assert isinstance(agents[0], ClaudeThermalAgent)
    assert design_agents()[0] is agents[0]


def test_agent_makes_no_call_when_the_temperatures_are_fine():
    project = build_intake(BASE, {}).project
    client = FakeClient(_surface("カプトン"))

    change = ClaudeThermalAgent(client).review(project, project_ledger(project), ())

    assert change is None
    assert client.calls == []
