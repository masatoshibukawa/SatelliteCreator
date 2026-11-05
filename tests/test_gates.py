import pytest
from pydantic import ValidationError

from satellitecreator.design import Orbit, SatelliteDesign
from satellitecreator.gates import GateBlockedError, evaluate_gate, pass_review
from satellitecreator.process import Review
from satellitecreator.project import MissionDefinition, Project, SuccessCriterion, SuccessLevel
from satellitecreator.requirements import (
    REQUIRED_FUNCTIONS,
    Function,
    Requirement,
    RequirementKind,
    RequirementLevel,
    RequirementStatus,
)

MISSION = MissionDefinition(
    objective="Demonstrate optical downlink from a CubeSat",
    stakeholders=("University lab",),
    success_criteria=(
        SuccessCriterion(level=SuccessLevel.MINIMUM, statement="Detect the beam on the ground"),
    ),
)
DESIGN = SatelliteDesign(form_factor="3U", orbit=Orbit(altitude_m=400e3, inclination_deg=51.6))


def _mission_requirement(**overrides) -> Requirement:
    fields = {
        "id": "MR-001",
        "level": RequirementLevel.MISSION,
        "kind": RequirementKind.FUNCTIONAL,
        "statement": "Downlink data with a laser",
        "status": RequirementStatus.CONFIRMED,
    }
    return Requirement(**{**fields, **overrides})


def _functional(requirement_id: str, level: RequirementLevel, function: Function, parent: str):
    return Requirement(
        id=requirement_id,
        level=level,
        kind=RequirementKind.FUNCTIONAL,
        statement=f"Provide the {function.value} function",
        status=RequirementStatus.CONFIRMED,
        function=function,
        parents=(parent,),
    )


def _system_requirements() -> tuple[Requirement, ...]:
    return tuple(
        _functional(f"SR-{index:03d}", RequirementLevel.SYSTEM, function, "MR-001")
        for index, function in enumerate(sorted(REQUIRED_FUNCTIONS), start=1)
    )


def _subsystem_requirements() -> tuple[Requirement, ...]:
    return tuple(
        _functional(f"SS-{index:03d}", RequirementLevel.SUBSYSTEM, item.function, item.id)
        for index, item in enumerate(_system_requirements(), start=1)
        if item.function is not Function.ORBIT
    )


def _project_ready_for_mdr(**overrides) -> Project:
    fields = {"name": "Demo", "mission": MISSION, "requirements": (_mission_requirement(),)}
    return Project(**{**fields, **overrides})


def _project_ready_for_srr(**overrides) -> Project:
    fields = {
        "name": "Demo",
        "mission": MISSION,
        "requirements": (_mission_requirement(), *_system_requirements()),
        "operations_concept": "Pass over the ground station, then downlink",
        "passed_reviews": (Review.MDR,),
    }
    return Project(**{**fields, **overrides})


def _project_ready_for_sdr(**overrides) -> Project:
    fields = {
        "name": "Demo",
        "mission": MISSION,
        "requirements": (
            _mission_requirement(),
            *_system_requirements(),
            *_subsystem_requirements(),
        ),
        "operations_concept": "Pass over the ground station, then downlink",
        "design": DESIGN,
        "passed_reviews": (Review.MDR, Review.SRR),
    }
    return Project(**{**fields, **overrides})


def _codes(project: Project, review: Review) -> set[str]:
    return {finding.code for finding in evaluate_gate(project, review).findings}


def test_project_rejects_duplicate_requirement_ids():
    with pytest.raises(ValidationError, match="duplicate"):
        Project(name="Demo", requirements=(_mission_requirement(), _mission_requirement()))


def test_mission_definition_needs_a_stakeholder():
    with pytest.raises(ValidationError):
        MissionDefinition(objective="x", stakeholders=(), success_criteria=())


def test_complete_project_passes_mdr():
    assert evaluate_gate(_project_ready_for_mdr(), Review.MDR).passed


def test_mdr_allows_open_mission_requirements_because_the_document_is_a_draft():
    draft = _mission_requirement(
        status=RequirementStatus.OPEN, question="Which ground station will you use?"
    )

    assert evaluate_gate(_project_ready_for_mdr(requirements=(draft,)), Review.MDR).passed


def test_mdr_blocks_without_a_mission_definition():
    assert "missing_mission" in _codes(_project_ready_for_mdr(mission=None), Review.MDR)


def test_mdr_blocks_without_minimum_success_criterion():
    mission = MISSION.model_copy(
        update={
            "success_criteria": (SuccessCriterion(level=SuccessLevel.FULL, statement="Downlink"),)
        }
    )

    assert "missing_minimum_success" in _codes(_project_ready_for_mdr(mission=mission), Review.MDR)


def test_mdr_blocks_without_mission_requirements():
    project = _project_ready_for_mdr(requirements=())

    assert "no_mission_requirement" in _codes(project, Review.MDR)


def test_complete_project_passes_srr():
    assert evaluate_gate(_project_ready_for_srr(), Review.SRR).passed


def test_gate_cannot_be_skipped():
    project = _project_ready_for_srr(passed_reviews=())

    assert "previous_review_not_passed" in _codes(project, Review.SRR)


def test_gate_cannot_be_passed_twice():
    project = _project_ready_for_mdr(passed_reviews=(Review.MDR,))

    assert "already_passed" in _codes(project, Review.MDR)


def test_srr_blocks_on_open_mission_requirement():
    project = _project_ready_for_srr(
        requirements=(
            _mission_requirement(status=RequirementStatus.OPEN, question="Which band?"),
            *_system_requirements(),
        )
    )

    assert "open_requirement" in _codes(project, Review.SRR)


def test_srr_blocks_on_open_system_requirement():
    open_requirement = Requirement(
        id="SR-099",
        level=RequirementLevel.SYSTEM,
        kind=RequirementKind.PERFORMANCE,
        statement="Pointing accuracy",
        status=RequirementStatus.OPEN,
        question="How accurate must pointing be?",
        function=Function.ATTITUDE_CONTROL,
        parents=("MR-001",),
    )
    project = _project_ready_for_srr(
        requirements=(_mission_requirement(), *_system_requirements(), open_requirement)
    )

    assert "open_requirement" in _codes(project, Review.SRR)


def test_srr_allows_assumed_requirements():
    assumed = _mission_requirement(status=RequirementStatus.ASSUMED, rationale="Lab default")
    project = _project_ready_for_srr(requirements=(assumed, *_system_requirements()))

    assert evaluate_gate(project, Review.SRR).passed


def test_srr_blocks_on_unknown_parent():
    orphan = _functional("SR-099", RequirementLevel.SYSTEM, Function.POWER, "MR-404")
    project = _project_ready_for_srr(
        requirements=(_mission_requirement(), *_system_requirements(), orphan)
    )

    assert "broken_trace" in _codes(project, Review.SRR)


def test_srr_blocks_when_parent_is_at_the_wrong_level():
    misplaced = _functional("SR-099", RequirementLevel.SYSTEM, Function.POWER, "SR-001")
    project = _project_ready_for_srr(
        requirements=(_mission_requirement(), *_system_requirements(), misplaced)
    )

    assert "broken_trace" in _codes(project, Review.SRR)


def test_srr_blocks_when_a_mission_requirement_is_not_flowed_down():
    uncovered = _mission_requirement(id="MR-002")
    project = _project_ready_for_srr(
        requirements=(_mission_requirement(), uncovered, *_system_requirements())
    )

    assert "uncovered_mission_requirement" in _codes(project, Review.SRR)


def test_srr_blocks_when_a_required_function_has_no_system_requirement():
    remaining = tuple(
        item for item in _system_requirements() if item.function is not Function.THERMAL_CONTROL
    )
    project = _project_ready_for_srr(requirements=(_mission_requirement(), *remaining))

    assert "uncovered_function" in _codes(project, Review.SRR)


def test_orbit_control_is_not_required_for_every_cubesat():
    assert Function.ORBIT_CONTROL not in REQUIRED_FUNCTIONS


def test_srr_blocks_without_operations_concept():
    project = _project_ready_for_srr(operations_concept="")

    assert "missing_operations_concept" in _codes(project, Review.SRR)


def test_complete_project_passes_sdr():
    assert evaluate_gate(_project_ready_for_sdr(), Review.SDR).passed


def test_sdr_blocks_on_open_subsystem_requirement():
    open_requirement = Requirement(
        id="SS-099",
        level=RequirementLevel.SUBSYSTEM,
        kind=RequirementKind.PERFORMANCE,
        statement="Battery capacity",
        status=RequirementStatus.OPEN,
        question="How long is the longest eclipse?",
        function=Function.POWER,
        parents=("SR-001",),
    )
    project = _project_ready_for_sdr(
        requirements=(
            _mission_requirement(),
            *_system_requirements(),
            *_subsystem_requirements(),
            open_requirement,
        )
    )

    assert "open_requirement" in _codes(project, Review.SDR)


def test_sdr_blocks_on_broken_subsystem_trace():
    orphan = _functional("SS-099", RequirementLevel.SUBSYSTEM, Function.POWER, "MR-001")
    project = _project_ready_for_sdr(
        requirements=(
            _mission_requirement(),
            *_system_requirements(),
            *_subsystem_requirements(),
            orphan,
        )
    )

    assert "broken_trace" in _codes(project, Review.SDR)


def test_sdr_blocks_without_subsystem_requirements():
    project = _project_ready_for_sdr(requirements=(_mission_requirement(), *_system_requirements()))

    assert "no_subsystem_requirement" in _codes(project, Review.SDR)


def test_sdr_blocks_when_a_system_requirement_is_not_flowed_down():
    remaining = _subsystem_requirements()[1:]
    project = _project_ready_for_sdr(
        requirements=(_mission_requirement(), *_system_requirements(), *remaining)
    )

    subjects = {
        finding.subject
        for finding in evaluate_gate(project, Review.SDR).findings
        if finding.code == "uncovered_system_requirement"
    }

    assert subjects == {"SR-001"}


def test_orbit_requirement_needs_no_subsystem_requirement():
    orbit_requirements = [
        item for item in _system_requirements() if item.function is Function.ORBIT
    ]

    assert orbit_requirements
    assert evaluate_gate(_project_ready_for_sdr(), Review.SDR).passed


def test_subsystem_requirement_may_serve_a_different_function_than_its_parent():
    cross_function = _functional("SS-099", RequirementLevel.SUBSYSTEM, Function.STRUCTURE, "SR-001")
    project = _project_ready_for_sdr(
        requirements=(
            _mission_requirement(),
            *_system_requirements(),
            *_subsystem_requirements(),
            cross_function,
        )
    )

    assert evaluate_gate(project, Review.SDR).passed


def test_sdr_blocks_without_a_design():
    assert "missing_design" in _codes(_project_ready_for_sdr(design=None), Review.SDR)


def test_sdr_blocks_on_design_out_of_scope():
    design = SatelliteDesign(
        form_factor="3U", orbit=Orbit(altitude_m=35_786e3, inclination_deg=0.0)
    )

    assert "altitude_out_of_scope" in _codes(_project_ready_for_sdr(design=design), Review.SDR)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"mission": None}, "missing_mission"),
        ({"operations_concept": ""}, "missing_operations_concept"),
        (
            {
                "requirements": (
                    _mission_requirement(status=RequirementStatus.OPEN, question="Which band?"),
                    *_system_requirements(),
                    *_subsystem_requirements(),
                )
            },
            "open_requirement",
        ),
        (
            {
                "requirements": (
                    _mission_requirement(),
                    *_system_requirements(),
                    *_subsystem_requirements(),
                    _functional("SR-099", RequirementLevel.SYSTEM, Function.POWER, "MR-404"),
                )
            },
            "broken_trace",
        ),
    ],
)
def test_change_made_after_an_earlier_review_blocks_the_next_gate(overrides, code):
    assert code in _codes(_project_ready_for_sdr(**overrides), Review.SDR)


def test_gates_without_defined_checks_still_rerun_earlier_rules():
    project = _project_ready_for_sdr(
        operations_concept="", passed_reviews=(Review.MDR, Review.SRR, Review.SDR)
    )

    assert "missing_operations_concept" in _codes(project, Review.PDR)


def test_blank_operations_concept_does_not_count():
    project = _project_ready_for_srr(operations_concept="   ")

    assert "missing_operations_concept" in _codes(project, Review.SRR)


@pytest.mark.parametrize(
    "fields",
    [
        {"objective": "   ", "stakeholders": ("Lab",)},
        {"objective": "Demo", "stakeholders": ("   ",)},
    ],
)
def test_mission_definition_rejects_blank_text(fields):
    with pytest.raises(ValidationError):
        MissionDefinition(**fields)


@pytest.mark.parametrize("review", [Review.PDR, Review.CDR])
def test_gates_without_defined_checks_fail_closed(review):
    passed = (Review.MDR, Review.SRR, Review.SDR, Review.PDR)
    project = _project_ready_for_sdr(passed_reviews=passed[: 3 if review is Review.PDR else 4])

    result = evaluate_gate(project, review)

    assert not result.passed
    assert "checks_undefined" in {finding.code for finding in result.findings}


def test_pass_review_returns_a_new_project_and_leaves_the_original_unchanged():
    project = _project_ready_for_mdr()

    advanced = pass_review(project, Review.MDR)

    assert advanced.passed_reviews == (Review.MDR,)
    assert project.passed_reviews == ()


def test_pass_review_raises_with_the_findings_when_blocked():
    project = _project_ready_for_mdr(mission=None)

    with pytest.raises(GateBlockedError) as error:
        pass_review(project, Review.MDR)

    assert "missing_mission" in {finding.code for finding in error.value.result.findings}


def test_findings_use_japanese_level_names():
    project = _project_ready_for_sdr(requirements=(_mission_requirement(), *_system_requirements()))

    messages = [finding.message for finding in evaluate_gate(project, Review.SDR).findings]

    assert messages
    assert all("subsystem" not in message for message in messages)
    assert any("サブシステム" in message for message in messages)


def test_findings_name_the_requirement_they_concern():
    project = _project_ready_for_srr(
        requirements=(
            _mission_requirement(status=RequirementStatus.OPEN, question="Which band?"),
            *_system_requirements(),
        )
    )

    subjects = {
        finding.subject
        for finding in evaluate_gate(project, Review.SRR).findings
        if finding.code == "open_requirement"
    }

    assert subjects == {"MR-001"}
