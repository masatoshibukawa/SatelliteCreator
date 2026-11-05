from types import SimpleNamespace

import anthropic
import pytest

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

    def __init__(self, *moves, error=None):
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
        return SimpleNamespace(parsed_output=move, usage=usage)


def _surface(name: str) -> ThermalMove:
    return ThermalMove(action="surface", surface=name, heater_power_w=None, reason="理由")


def _heater(power_w: float) -> ThermalMove:
    return ThermalMove(action="heater", surface=None, heater_power_w=power_w, reason="理由")


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
    assert call["max_tokens"] <= 512
    assert call["output_config"] == {"effort": "low"}
    assert len(call["messages"][0]["content"]) < 500


@pytest.mark.parametrize(
    "move",
    [
        _surface("金メッキ"),
        _surface(None),
        _heater(99.0),
        _heater(None),
        ThermalMove(action="stop", surface=None, heater_power_w=None, reason="理由"),
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
    client = FakeClient(_surface("黒塗り"), _heater(6.0))

    result = run_design_loop(build_intake(HOT, {}).project, agents=(ClaudeThermalAgent(client),))

    assert result.status is LoopStatus.CONVERGED
    assert len(client.calls) == 2


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
