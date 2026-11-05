import pytest

from satellitecreator.gates import evaluate_gate
from satellitecreator.intake import (
    QUESTION_IDS,
    build_intake,
    parse_altitude_m,
    parse_form_factor,
    parse_inclination_deg,
)
from satellitecreator.process import Review
from satellitecreator.requirements import REQUIRED_FUNCTIONS, RequirementLevel, RequirementStatus

PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"
FREE_TEXT_ANSWERS = {
    "stakeholders": "大学の研究室、地上局の運用者",
    "minimum_success": "地上で光信号を検出する",
    "mission_payload": "レーザ通信端末を搭載する",
    "communication": "UHF でテレメトリを降ろす",
    "power": "太陽電池で全運用モードを賄う",
    "attitude_control": "地上局を指向する",
    "thermal_control": "レーザ端末を動作温度に保つ",
    "data_handling": "テレメトリを記録して地上へ送る",
    "operations_concept": "地上局の上空通過時に通信する",
}


def _question(intake, question_id):
    return next(item for item in intake.questions if item.id == question_id)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3U の衛星", "3U"),
        ("6 U", "6U"),
        ("３Ｕ", "3U"),
        ("12U", "12U"),
        ("小型衛星", None),
        ("3U と 6U で比較したい", None),
        ("3U の衛星で、3U の分離機構を使う", "3U"),
    ],
)
def test_parse_form_factor(text, expected):
    assert parse_form_factor(text) == expected


@pytest.mark.parametrize(
    ("text", "bare", "expected"),
    [
        ("高度 400 km", False, 400_000.0),
        ("５００ｋｍの軌道", False, 500_000.0),
        ("高度500キロ", False, 500_000.0),
        ("地上局から 2000km、高度 400km", False, 400_000.0),
        ("軌道は 550 km", False, 550_000.0),
        ("400", False, None),
        ("400", True, 400_000.0),
        ("400 km", True, 400_000.0),
        ("0 km", False, None),
        ("まだ決めていない", True, None),
        ("10キロ四方を観測する", False, None),
        ("300km先の雲を撮る", False, None),
        ("高度は 500 km 以上", False, None),
        ("高度 500km 以下", False, None),
        ("高度 400 km 程度", False, None),
        ("高度 約 400 km", False, None),
        ("500km以上", True, None),
        ("約 400", True, None),
    ],
)
def test_parse_altitude(text, bare, expected):
    assert parse_altitude_m(text, bare=bare) == expected


@pytest.mark.parametrize(
    ("text", "bare", "expected"),
    [
        ("軌道傾斜角 51.6 度", False, 51.6),
        ("傾斜角97.4°", False, 97.4),
        ("51.6", False, None),
        ("51.6", True, 51.6),
        ("傾斜角 181 度", False, None),
        ("傾斜角は 90 度未満", False, None),
        ("傾斜角 約 97 度", False, None),
    ],
)
def test_parse_inclination(text, bare, expected):
    assert parse_inclination_deg(text, bare=bare) == expected


def test_facts_in_the_prompt_become_confirmed_requirements():
    intake = build_intake(PROMPT, {})

    assert _question(intake, "form_factor").from_prompt
    assert intake.project.design.form_factor == "3U"
    assert intake.project.design.orbit.altitude_m == 400_000.0
    orbit_targets = [
        item.target.key
        for item in intake.project.at_level(RequirementLevel.SYSTEM)
        if item.target is not None
    ]
    assert orbit_targets == ["altitude_m", "inclination_deg", "total_mass_kg"]


def test_mass_limit_comes_from_the_form_factor_data():
    intake = build_intake(PROMPT, {})

    mass = next(
        item
        for item in intake.project.at_level(RequirementLevel.SYSTEM)
        if item.target is not None and item.target.key == "total_mass_kg"
    )

    assert mass.target.value == 4.5


def test_missing_facts_stay_open_with_a_question():
    intake = build_intake("光通信を実証したい", {})

    assert intake.project.design is None
    open_requirements = [
        item for item in intake.project.requirements if item.status is RequirementStatus.OPEN
    ]
    assert open_requirements
    assert all(item.question for item in open_requirements)


def test_every_required_function_has_a_system_requirement():
    intake = build_intake("光通信を実証したい", {})

    covered = {item.function for item in intake.project.at_level(RequirementLevel.SYSTEM)}

    assert REQUIRED_FUNCTIONS <= covered


def test_answer_fills_the_gap_left_by_the_prompt():
    intake = build_intake("光通信を実証したい", {"altitude": "500"})

    question = _question(intake, "altitude")

    assert question.answered
    assert not question.from_prompt


def test_answer_overrides_the_prompt():
    intake = build_intake(PROMPT, {"altitude": "550 km"})

    assert intake.project.design.orbit.altitude_m == 550_000.0


def test_unreadable_answer_is_flagged_and_stays_unanswered():
    intake = build_intake("光通信を実証したい", {"altitude": "まだ決めていない"})

    question = _question(intake, "altitude")

    assert question.unreadable
    assert not question.answered


def test_unsupported_form_factor_is_asked_again():
    intake = build_intake("12U の衛星で光通信を実証したい", {})

    question = _question(intake, "form_factor")

    assert question.unreadable
    assert not question.answered
    assert intake.project.design is None


def test_unknown_answer_id_is_rejected():
    with pytest.raises(ValueError, match="unknown question"):
        build_intake(PROMPT, {"no_such_question": "x"})


def test_all_questions_have_unique_ids():
    assert len(QUESTION_IDS) == len(set(QUESTION_IDS))


def test_free_text_answers_are_kept_verbatim_and_confirmed():
    intake = build_intake(PROMPT, FREE_TEXT_ANSWERS)

    statements = {item.statement for item in intake.project.requirements}

    assert "UHF でテレメトリを降ろす" in statements


def test_stakeholders_are_split_on_japanese_commas():
    intake = build_intake(PROMPT, FREE_TEXT_ANSWERS)

    assert intake.project.mission.stakeholders == ("大学の研究室", "地上局の運用者")


def test_fully_answered_project_passes_mdr_and_srr():
    project = build_intake(PROMPT, FREE_TEXT_ANSWERS).project

    assert evaluate_gate(project, Review.MDR).findings == ()
    advanced = project.model_copy(update={"passed_reviews": (Review.MDR,)})
    assert evaluate_gate(advanced, Review.SRR).findings == ()


def test_intake_is_deterministic():
    assert build_intake(PROMPT, FREE_TEXT_ANSWERS) == build_intake(PROMPT, FREE_TEXT_ANSWERS)
