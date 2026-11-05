import pytest

from satellitecreator.process import Review
from satellitecreator.session import ReviewState, check_request, run_session

PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"


def _states(result):
    return {item.review: item.state for item in result.reviews}


@pytest.mark.parametrize(
    "text",
    ["ミサイルを追尾する衛星", "敵の通信を妨害したい", "他国の衛星を攻撃する", "weapon payload"],
)
def test_requests_outside_the_safety_line_are_refused(text):
    assert check_request(text) is not None


def test_ordinary_request_is_not_refused():
    assert check_request(PROMPT) is None


def test_refused_request_returns_no_design():
    result = run_session("ミサイルを追尾する衛星", {})

    assert result.refusal
    assert result.document is None
    assert result.reviews == ()
    assert result.satellite is None


def test_first_blocked_review_stops_the_rest():
    result = run_session(PROMPT, {})

    assert _states(result) == {
        Review.MDR: ReviewState.BLOCKED,
        Review.SRR: ReviewState.WAITING,
        Review.SDR: ReviewState.WAITING,
        Review.PDR: ReviewState.WAITING,
        Review.CDR: ReviewState.WAITING,
    }


def test_blocked_review_explains_why():
    result = run_session(PROMPT, {})

    mdr = next(item for item in result.reviews if item.review is Review.MDR)

    assert {item.code for item in mdr.findings} == {"missing_mission"}


def test_answers_advance_the_reviews():
    answers = {
        "stakeholders": "大学の研究室",
        "minimum_success": "地上で光信号を検出する",
    }

    result = run_session(PROMPT, answers)

    assert _states(result)[Review.MDR] is ReviewState.PASSED
    assert _states(result)[Review.SRR] is ReviewState.BLOCKED


def test_satellite_view_uses_the_envelope_and_mass_limit_data():
    satellite = run_session(PROMPT, {}).satellite

    assert satellite.form_factor == "3U"
    assert (satellite.width_m, satellite.depth_m, satellite.length_m) == (0.1, 0.1, 0.3405)
    assert satellite.max_mass_kg == 4.5


def test_form_factor_alone_is_enough_to_show_the_satellite():
    assert run_session("3U で光通信を実証したい", {}).satellite.form_factor == "3U"


def test_no_satellite_until_the_form_factor_is_known():
    assert run_session("光通信を実証したい", {}).satellite is None


def test_orbit_outside_the_scope_is_reported_immediately():
    result = run_session("高度 36000 km、傾斜角 0 度の 3U 衛星", {})

    assert [item.code for item in result.scope_findings] == ["altitude_out_of_scope"]


def test_session_reports_the_simulation_of_each_block():
    result = run_session(PROMPT, {})

    states = {item.block: item.state for item in result.simulations}

    assert states["orbit"] == "done"
    assert states["thermal"] == "not_built"


def test_session_reports_the_consistency_checks():
    result = run_session(PROMPT, {})

    assert {item.state for item in result.checks} == {"not_run"}


def test_refused_request_runs_no_simulation():
    result = run_session("ミサイルを追尾する衛星", {})

    assert result.simulations == ()
    assert result.checks == ()


def test_session_exposes_the_requirements_with_their_status():
    result = run_session(PROMPT, {})

    assert {item.status for item in result.requirements} == {"confirmed", "open"}
