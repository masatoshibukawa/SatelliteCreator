from fastapi.testclient import TestClient

from api.main import MAX_ANSWER_LENGTH, MAX_PROMPT_LENGTH, app

client = TestClient(app)
PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"


def test_health_reports_ok():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_session_returns_the_design_state():
    response = client.post("/session", json={"prompt": PROMPT})

    assert response.status_code == 200
    body = response.json()
    assert body["satellite"]["form_factor"] == "3U"
    assert body["reviews"][0]["review"] == "MDR"
    assert body["document"]["sections"][0]["number"] == "1"


def test_session_accepts_answers():
    response = client.post(
        "/session", json={"prompt": "光通信を実証したい", "answers": {"form_factor": "2U"}}
    )

    assert response.json()["satellite"]["form_factor"] == "2U"


def test_blank_prompt_is_rejected():
    assert client.post("/session", json={"prompt": "   "}).status_code == 422


def test_overlong_prompt_is_rejected():
    response = client.post("/session", json={"prompt": "あ" * (MAX_PROMPT_LENGTH + 1)})

    assert response.status_code == 422


def test_overlong_answer_is_rejected():
    response = client.post(
        "/session",
        json={"prompt": PROMPT, "answers": {"power": "あ" * (MAX_ANSWER_LENGTH + 1)}},
    )

    assert response.status_code == 422


def test_unknown_answer_id_is_rejected():
    response = client.post("/session", json={"prompt": PROMPT, "answers": {"nope": "x"}})

    assert response.status_code == 422
    assert "unknown question" in response.json()["detail"]


def test_refusal_is_a_normal_response():
    body = client.post("/session", json={"prompt": "ミサイルを追尾する衛星"}).json()

    assert body["refusal"]
    assert body["document"] is None
