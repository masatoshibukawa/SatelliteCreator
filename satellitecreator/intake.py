"""Turns a request and the answers so far into a project record.

Interim step: facts are read with plain text patterns, so nothing here invents a value. A fact
that cannot be read stays open with a question. Claude takes over the reading in step 5; the
question list and the records built here stay the same.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import TypeVar

from pydantic import computed_field

from satellitecreator.design import Orbit, SatelliteDesign, form_factor, load_scope_limits
from satellitecreator.project import MissionDefinition, Project, SuccessCriterion, SuccessLevel
from satellitecreator.requirements import (
    Comparator,
    Function,
    Requirement,
    RequirementKind,
    RequirementLevel,
    RequirementStatus,
    Target,
)
from satellitecreator.schema import Frozen

T = TypeVar("T")

_NUMBER = r"(\d+(?:\.\d+)?)"
_KILOMETRES = _NUMBER + r"\s*(?:km|キロ(?!グラム))"
_FORM_FACTOR = re.compile(r"(?<![\d.])(\d+)\s*U(?![A-Za-z])", re.IGNORECASE)
_ALTITUDE_AFTER_LABEL = re.compile(r"(?:高度|軌道)\D{0,8}?" + _KILOMETRES, re.IGNORECASE)
_ALTITUDE_BEFORE_LABEL = re.compile(_KILOMETRES + r"\s*の?\s*(?:高度|軌道)", re.IGNORECASE)
_ALTITUDE_ANY = re.compile(_KILOMETRES, re.IGNORECASE)
_INCLINATION_LABELLED = re.compile(
    r"傾斜角?\D{0,8}?" + _NUMBER + r"\s*(?:度|deg|°)?", re.IGNORECASE
)
_PEAK_POWER = re.compile(r"消費電力\D{0,8}?" + _NUMBER + r"\s*W", re.IGNORECASE)
_DURATION = _NUMBER + r"\s*(年|か月|ヶ月|ケ月|カ月)"
_DURATION_LABELLED = re.compile(r"(?:ミッション|運用)期間\D{0,8}?" + _DURATION)
_DURATION_ANY = re.compile(_DURATION)
_SECONDS_PER_YEAR = 365.25 * 86400
_SECONDS_PER_MONTH = _SECONDS_PER_YEAR / 12
_BARE_VALUE = re.compile(r"^\s*" + _NUMBER + r"\s*(?:km|キロ|度|deg|°)?\s*$", re.IGNORECASE)
_HEDGE_BEFORE = re.compile(r"約|およそ")
_HEDGE_AFTER = re.compile(r"\s*(?:以上|以下|未満|以内|超|程度|くらい|ぐらい|前後|付近|あたり)")
_HEDGE_WINDOW = 6
_LIST_SEPARATOR = re.compile(r"[、,，]")
_NAME_LENGTH = 40

_QUESTIONS = {
    "form_factor": "衛星の大きさはどれにしますか？（1U、2U、3U、6U）",
    "altitude": "軌道の高度は何 km にしますか？",
    "inclination": "軌道傾斜角は何度にしますか？",
    "stakeholders": "この衛星の成果を受け取る人や組織は誰ですか？",
    "minimum_success": "最低限これが達成できれば成功と言える基準は何ですか？",
    "mission_payload": "ミッション機器に求める機能は何ですか？",
    "communication": "地上との通信で何を実現しますか？",
    "power": "電源に求めることは何ですか？",
    "attitude_control": "衛星の向きに求めることは何ですか？（地球指向、太陽指向、制御なしなど）",
    "thermal_control": "温度管理が特に必要な機器はありますか？",
    "data_handling": "搭載データをどのように処理、保存しますか？",
    "operations_concept": "どのように運用しますか？（地上局、通信の頻度など）",
    "mission_duration": "ミッション期間はどのくらいですか？（例：6 か月、2 年）",
}
QUESTION_IDS = tuple(_QUESTIONS)
_ASSUMABLE_REQUIREMENTS = {"altitude": "SR-001", "inclination": "SR-002", "form_factor": "SR-003"}

_FUNCTION_QUESTIONS = (
    ("mission_payload", Function.MISSION, "ミッション機器への要求"),
    ("communication", Function.COMMUNICATION, "通信系への要求"),
    ("power", Function.POWER, "電源系への要求"),
    ("attitude_control", Function.ATTITUDE_CONTROL, "姿勢制御系への要求"),
    ("thermal_control", Function.THERMAL_CONTROL, "熱制御系への要求"),
    ("data_handling", Function.DATA_HANDLING, "データ処理系への要求"),
)


class UnknownQuestionError(ValueError):
    """An answer names a question that does not exist, which is the caller's mistake."""


class QuestionState(Frozen):
    id: str
    text: str
    answer: str = ""
    from_prompt: bool = False
    assumed: bool = False
    unreadable: bool = False

    @computed_field
    @property
    def answered(self) -> bool:
        return bool(self.answer) and not self.unreadable


class Intake(Frozen):
    project: Project
    questions: tuple[QuestionState, ...]
    form_factor: str | None = None


def _normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def parse_form_factor(text: str) -> str | None:
    """Several different sizes in one text are a comparison, not a choice, so none is taken."""
    found = {f"{int(value)}U" for value in _FORM_FACTOR.findall(_normalized(text))}
    return next(iter(found)) if len(found) == 1 else None


def _bare_number(text: str) -> float | None:
    match = _BARE_VALUE.match(text)
    return float(match.group(1)) if match else None


def _exact_number(match: re.Match[str]) -> float | None:
    """A hedged value such as 約 400 or 500 以上 is a range, so it stays open for the dialogue."""
    lead = match.string[max(0, match.start(1) - _HEDGE_WINDOW) : match.start(1)]
    if _HEDGE_BEFORE.search(lead) or _HEDGE_AFTER.match(match.string, match.end()):
        return None
    return float(match.group(1))


def parse_altitude_m(text: str, *, bare: bool = False) -> float | None:
    """A request must label the altitude. Only an answer to the altitude question may omit it."""
    normalized = _normalized(text)
    patterns = (_ALTITUDE_AFTER_LABEL, _ALTITUDE_BEFORE_LABEL, *((_ALTITUDE_ANY,) if bare else ()))
    match = next(filter(None, (pattern.search(normalized) for pattern in patterns)), None)
    if match is not None:
        kilometres = _exact_number(match)
    else:
        kilometres = _bare_number(normalized) if bare else None
    return kilometres * 1000 if kilometres else None


def parse_inclination_deg(text: str, *, bare: bool = False) -> float | None:
    normalized = _normalized(text)
    match = _INCLINATION_LABELLED.search(normalized)
    if match is not None:
        degrees = _exact_number(match)
    else:
        degrees = _bare_number(normalized) if bare else None
    return degrees if degrees is not None and degrees <= 180 else None


def parse_peak_power_w(text: str) -> float | None:
    match = _PEAK_POWER.search(_normalized(text))
    return None if match is None else _exact_number(match)


def parse_mission_duration_s(text: str, *, bare: bool = False) -> float | None:
    normalized = _normalized(text)
    match = (_DURATION_ANY if bare else _DURATION_LABELLED).search(normalized)
    if match is None:
        return None
    amount = _exact_number(match)
    if amount is None:
        return None
    return amount * (_SECONDS_PER_YEAR if match.group(2) == "年" else _SECONDS_PER_MONTH)


def _resolve(
    question_id: str,
    prompt: str,
    answers: Mapping[str, str],
    parse: Callable[[str, bool], T | None],
    display: Callable[[T], str],
) -> tuple[QuestionState, T | None]:
    """An answer wins over the request, because it is the user's latest word."""
    text = _QUESTIONS[question_id]
    raw = answers.get(question_id, "").strip()
    if raw:
        value = parse(raw, True)
        return QuestionState(id=question_id, text=text, answer=raw, unreadable=value is None), value
    value = parse(prompt, False)
    if value is None:
        return QuestionState(id=question_id, text=text), None
    question = QuestionState(id=question_id, text=text, answer=display(value), from_prompt=True)
    return question, value


def _resolve_form_factor(
    prompt: str, answers: Mapping[str, str]
) -> tuple[QuestionState, str | None]:
    question, value = _resolve(
        "form_factor", prompt, answers, lambda text, _bare: parse_form_factor(text), str
    )
    supported = {item.id for item in load_scope_limits().form_factors}
    if value is None or value in supported:
        return question, value
    return question.model_copy(update={"unreadable": True, "from_prompt": False}), None


def _free_text(question_id: str, answers: Mapping[str, str]) -> QuestionState:
    answer = answers.get(question_id, "").strip()
    return QuestionState(id=question_id, text=_QUESTIONS[question_id], answer=answer)


def _system_requirement(
    index: int,
    function: Function,
    kind: RequirementKind,
    statement: str,
    question: QuestionState | None = None,
    target: Target | None = None,
) -> Requirement:
    settled = question is None
    return Requirement(
        id=f"SR-{index:03d}",
        level=RequirementLevel.SYSTEM,
        kind=kind,
        statement=statement,
        status=RequirementStatus.CONFIRMED if settled else RequirementStatus.OPEN,
        question="" if settled else question.text,
        function=function,
        parents=("MR-001",),
        target=target,
    )


def _orbit_requirements(
    altitude: tuple[QuestionState, float | None],
    inclination: tuple[QuestionState, float | None],
) -> tuple[Requirement, ...]:
    altitude_question, altitude_m = altitude
    inclination_question, inclination_deg = inclination
    performance = RequirementKind.PERFORMANCE
    return (
        _system_requirement(1, Function.ORBIT, performance, "軌道高度", altitude_question)
        if altitude_m is None
        else _system_requirement(
            1,
            Function.ORBIT,
            performance,
            f"軌道高度を {altitude_m / 1000:g} km とする",
            target=Target(key="altitude_m", comparator=Comparator.EQUAL, value=altitude_m),
        ),
        _system_requirement(2, Function.ORBIT, performance, "軌道傾斜角", inclination_question)
        if inclination_deg is None
        else _system_requirement(
            2,
            Function.ORBIT,
            performance,
            f"軌道傾斜角を {inclination_deg:g} 度とする",
            target=Target(
                key="inclination_deg", comparator=Comparator.EQUAL, value=inclination_deg
            ),
        ),
    )


def _mass_requirement(question: QuestionState, form_factor_id: str | None) -> Requirement:
    constraint = RequirementKind.CONSTRAINT
    if form_factor_id is None:
        return _system_requirement(3, Function.STRUCTURE, constraint, "衛星の大きさ", question)
    max_mass_kg = form_factor(form_factor_id).max_mass_kg
    return _system_requirement(
        3,
        Function.STRUCTURE,
        constraint,
        f"総質量を {max_mass_kg:g} kg 以下とする（{form_factor_id}）",
        target=Target(key="total_mass_kg", comparator=Comparator.AT_MOST, value=max_mass_kg),
    )


def _function_requirements(
    questions: Mapping[str, QuestionState],
) -> tuple[Requirement, ...]:
    return tuple(
        _system_requirement(
            index,
            function,
            RequirementKind.FUNCTIONAL,
            questions[question_id].answer or label,
            None if questions[question_id].answered else questions[question_id],
        )
        for index, (question_id, function, label) in enumerate(_FUNCTION_QUESTIONS, start=4)
    )


def _mission(
    prompt: str, stakeholders: QuestionState, minimum_success: QuestionState
) -> MissionDefinition | None:
    names = tuple(
        name.strip() for name in _LIST_SEPARATOR.split(stakeholders.answer) if name.strip()
    )
    if not names:
        return None
    criteria = (
        (SuccessCriterion(level=SuccessLevel.MINIMUM, statement=minimum_success.answer),)
        if minimum_success.answered
        else ()
    )
    return MissionDefinition(objective=prompt, stakeholders=names, success_criteria=criteria)


def _design(
    form_factor_id: str | None,
    altitude_m: float | None,
    inclination_deg: float | None,
    peak_power_w: float | None,
    mission_duration_s: float | None,
) -> SatelliteDesign | None:
    if form_factor_id is None or altitude_m is None or inclination_deg is None:
        return None
    orbit = Orbit(altitude_m=altitude_m, inclination_deg=inclination_deg)
    return SatelliteDesign(
        form_factor=form_factor_id,
        orbit=orbit,
        peak_power_w=peak_power_w,
        mission_duration_s=mission_duration_s,
    )


def _apply_assumptions(
    project: Project,
    questions: tuple[QuestionState, ...],
    assumed: Mapping[str, str],
) -> tuple[Project, tuple[QuestionState, ...]]:
    """Marks values that came from an assumption instead of the user."""
    reasons = {
        _ASSUMABLE_REQUIREMENTS[key]: reason
        for key, reason in assumed.items()
        if key in _ASSUMABLE_REQUIREMENTS
    }
    requirements = tuple(
        item.model_copy(update={"status": RequirementStatus.ASSUMED, "rationale": reasons[item.id]})
        if item.id in reasons and item.status is RequirementStatus.CONFIRMED
        else item
        for item in project.requirements
    )
    marked = tuple(
        item.model_copy(update={"assumed": True}) if item.id in assumed else item
        for item in questions
    )
    return project.model_copy(update={"requirements": requirements}), marked


def build_intake(
    prompt: str, answers: Mapping[str, str], assumed: Mapping[str, str] | None = None
) -> Intake:
    """`assumed` names answers that are assumptions, with the reason for each."""
    unknown = sorted(set(answers) - set(QUESTION_IDS))
    if unknown:
        raise UnknownQuestionError(f"unknown question ids: {unknown}")

    form_question, form_factor_id = _resolve_form_factor(prompt, answers)
    altitude = _resolve(
        "altitude", prompt, answers, lambda t, b: parse_altitude_m(t, bare=b), _kilometres_text
    )
    inclination = _resolve(
        "inclination",
        prompt,
        answers,
        lambda t, b: parse_inclination_deg(t, bare=b),
        lambda value: f"{value:g} 度",
    )
    duration = _resolve(
        "mission_duration",
        prompt,
        answers,
        lambda t, b: parse_mission_duration_s(t, bare=b),
        lambda value: f"{value / _SECONDS_PER_MONTH:.1f} か月",
    )
    free_text = {
        question_id: _free_text(question_id, answers)
        for question_id in QUESTION_IDS[3:]
        if question_id != "mission_duration"
    }

    mission_requirement = Requirement(
        id="MR-001",
        level=RequirementLevel.MISSION,
        kind=RequirementKind.FUNCTIONAL,
        statement=prompt,
        status=RequirementStatus.CONFIRMED,
    )
    project = Project(
        name=prompt[:_NAME_LENGTH],
        mission=_mission(prompt, free_text["stakeholders"], free_text["minimum_success"]),
        requirements=(
            mission_requirement,
            *_orbit_requirements(altitude, inclination),
            _mass_requirement(form_question, form_factor_id),
            *_function_requirements(free_text),
        ),
        operations_concept=free_text["operations_concept"].answer,
        design=_design(
            form_factor_id,
            altitude[1],
            inclination[1],
            parse_peak_power_w(f"{prompt} {answers.get('power', '')}"),
            duration[1],
        ),
    )
    questions = (form_question, altitude[0], inclination[0], *free_text.values(), duration[0])
    project, questions = _apply_assumptions(project, questions, assumed or {})
    return Intake(project=project, questions=questions, form_factor=form_factor_id)


def _kilometres_text(altitude_m: float) -> str:
    return f"{altitude_m / 1000:g} km"
