import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from satellitecreator.intake import build_intake
from satellitecreator.launch_request import build_launch_request, main, to_json
from satellitecreator.session import run_session
from satellitecreator.simulation import project_ledger

EXAMPLE_DIR = Path(__file__).parent.parent / "examples" / "opt_cube"
PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
FIELDS = {
    "schema_version",
    "satellite_name",
    "payload_mass_kg",
    "target_perigee_m",
    "target_apogee_m",
    "inclination_deg",
    "envelope_mm",
    "sources",
    "provisional",
}


def _request(prompt: str = PROMPT, name: str | None = "OPT-CUBE"):
    return build_launch_request(build_intake(prompt, {}).project, name)


def test_request_has_exactly_the_agreed_fields():
    assert set(json.loads(to_json(_request()))) == FIELDS


def test_schema_version_is_one():
    assert _request().schema_version == 1


def test_payload_mass_is_the_calculated_total_mass():
    project = build_intake(PROMPT, {}).project

    request = build_launch_request(project)

    assert request.payload_mass_kg == pytest.approx(
        project_ledger(project).value("total_mass_kg"), abs=1e-4
    )


def test_circular_orbit_has_equal_perigee_and_apogee_in_metres():
    request = _request()

    assert request.target_perigee_m == 400_000
    assert request.target_apogee_m == 400_000


def test_inclination_comes_from_the_design():
    assert _request().inclination_deg == 51.6


def test_envelope_is_the_launch_envelope_in_millimetres():
    envelope = _request().envelope_mm

    assert (envelope.width, envelope.depth, envelope.height) == (100.0, 100.0, 340.5)


def test_every_value_names_its_source():
    sources = _request().sources

    assert set(sources) == {
        "payload_mass_kg",
        "target_perigee_m",
        "target_apogee_m",
        "inclination_deg",
        "envelope_mm",
    }
    assert "m = Σm_i + Δm" in sources["payload_mass_kg"]
    assert "22_asj.pdf" in sources["payload_mass_kg"]
    assert "SR-001" in sources["target_perigee_m"]
    assert "SR-002" in sources["inclination_deg"]
    assert "cubesatdesignspecification" in sources["envelope_mm"]


def test_request_built_on_the_reference_bus_is_provisional():
    assert _request().provisional is True


def test_name_defaults_to_the_project_name():
    assert _request(name=None).satellite_name == PROMPT[:40]


def test_no_request_without_a_design():
    assert _request("光通信を実証したい") is None


def test_no_request_without_a_calculated_mass():
    assert _request("高度 500 km、傾斜角 97 度の 6U 衛星") is None


def test_json_is_deterministic_and_keeps_japanese_readable():
    assert to_json(_request()) == to_json(_request())
    assert "\\u" not in to_json(_request())


def test_session_exposes_the_request():
    assert run_session(PROMPT, {}).launch_request.payload_mass_kg > 0


def test_api_returns_the_request():
    body = TestClient(app).post("/session", json={"prompt": PROMPT}).json()

    assert body["launch_request"]["schema_version"] == 1


def test_command_writes_the_file(tmp_path):
    output = tmp_path / "launch_request.json"

    status = main(["--prompt", PROMPT, "--name", "OPT-CUBE", "--output", str(output)])

    assert status == 0
    assert json.loads(output.read_text(encoding="utf-8"))["satellite_name"] == "OPT-CUBE"


def test_command_fails_when_no_request_can_be_built(tmp_path, capsys):
    output = tmp_path / "launch_request.json"

    status = main(["--prompt", "光通信を実証したい", "--output", str(output)])

    assert status == 1
    assert not output.exists()
    assert capsys.readouterr().err


def test_example_file_matches_what_the_code_produces():
    prompt = (EXAMPLE_DIR / "request.txt").read_text(encoding="utf-8").strip()

    expected = to_json(_request(prompt)) + "\n"

    assert (EXAMPLE_DIR / "launch_request.json").read_text(encoding="utf-8") == expected
