from satellitecreator.document import SectionState, build_document
from satellitecreator.intake import build_intake
from satellitecreator.project import Project

PROMPT = "高度 400 km、軌道傾斜角 51.6 度の 3U CubeSat で光通信を実証したい"


def _section(document, number):
    return next(item for item in document.sections if item.number == number)


def _item(document, number):
    return next(item for item in document.checklist if item.number == number)


def test_chapters_follow_the_contest_format():
    document = build_document(build_intake(PROMPT, {}).project)

    assert [item.number for item in document.sections] == [
        "1",
        "2",
        "3",
        "4",
        "5.1",
        "5.2",
        "5.3",
        "5.4",
        "5.5",
        "6",
        "7",
        "8",
    ]


def test_checklist_has_the_thirteen_contest_items():
    document = build_document(build_intake(PROMPT, {}).project)

    assert [item.number for item in document.checklist] == list(range(1, 14))


def test_chapter_one_carries_the_request():
    document = build_document(build_intake(PROMPT, {}).project)

    assert any(PROMPT in line for line in _section(document, "1").lines)


def test_system_section_reports_orbit_and_envelope_from_data():
    document = build_document(build_intake(PROMPT, {}).project)

    text = "\n".join(_section(document, "5.1").lines)

    assert "400 km" in text
    assert "51.6" in text
    assert "100 × 100 × 340.5 mm" in text
    assert "4.5 kg" in text


def test_unknown_design_leaves_the_system_section_pending():
    document = build_document(build_intake("光通信を実証したい", {}).project)

    assert _section(document, "5.1").state is SectionState.PENDING


def test_uncomputed_chapters_are_pending_with_a_reason_and_no_values():
    document = build_document(build_intake(PROMPT, {}).project)

    for number in ("6", "7"):
        section = _section(document, number)
        assert section.state is SectionState.PENDING
        assert section.lines == ()
        assert section.pending_note


def test_mission_analysis_shows_the_calculated_orbit_with_its_equation():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "2")

    assert section.state is SectionState.PARTIAL
    assert any("軌道周期: 92.6 分" in line and "T = 2π" in line for line in section.lines)
    assert any(line.startswith("最大の日陰時間: 36.1 分") for line in section.lines)
    assert "円軌道" in section.pending_note


def test_stand_in_note_appears_only_when_mass_and_thermal_were_calculated():
    prompt = "高度 500 km、傾斜角 97 度の 6U 衛星"

    with_bus = _section(build_document(build_intake(PROMPT, {}).project), "2")
    without_bus = _section(build_document(build_intake(prompt, {}).project), "2")

    assert "OPT-CUBE" in with_bus.pending_note
    assert "OPT-CUBE" not in without_bus.pending_note


def test_mission_analysis_is_pending_without_an_orbit():
    document = build_document(build_intake("光通信を実証したい", {}).project)

    section = _section(document, "2")

    assert section.state is SectionState.PENDING
    assert section.lines == ()


def test_references_include_the_sources_of_the_equations():
    document = build_document(build_intake(PROMPT, {}).project)

    assert any("ntrs.nasa.gov" in item.url for item in document.references)


def test_subsystem_section_stays_partial_until_calculations_exist():
    document = build_document(build_intake(PROMPT, {}).project)

    assert _section(document, "5.3").state is SectionState.PARTIAL


def test_success_level_is_shown_in_japanese():
    answers = {"stakeholders": "大学の研究室", "minimum_success": "地上で光信号を検出する"}
    document = build_document(build_intake(PROMPT, answers).project)

    text = "\n".join(_section(document, "1").lines)

    assert "ミニマムサクセス: 地上で光信号を検出する" in text
    assert "minimum" not in text


def test_project_without_requirements_leaves_the_subsystem_section_pending():
    document = build_document(Project(name="Demo"))

    assert _section(document, "5.3").state is SectionState.PENDING


def test_operations_concept_appears_in_the_operations_section():
    answers = {"operations_concept": "地上局の上空通過時に通信する"}
    document = build_document(build_intake(PROMPT, answers).project)

    section = _section(document, "5.5")

    assert section.state is SectionState.PARTIAL
    assert section.lines == ("地上局の上空通過時に通信する",)
    assert _item(document, 6).state is SectionState.PARTIAL


def test_checklist_marks_only_what_the_project_actually_has():
    document = build_document(build_intake(PROMPT, {}).project)

    assert _item(document, 1).state is SectionState.PARTIAL
    assert _item(document, 2).state is SectionState.PENDING


def test_checklist_credits_mass_and_temperature_only_when_they_are_calculated():
    calculated = build_document(build_intake(PROMPT, {}).project)
    prompt = "高度 500 km、傾斜角 97 度の 6U 衛星"
    not_calculated = build_document(build_intake(prompt, {}).project)

    for number in (3, 4, 11):
        assert _item(calculated, number).state is SectionState.PARTIAL
        assert _item(not_calculated, number).state is SectionState.PENDING


def test_checklist_does_not_credit_a_stated_orbit_as_a_rationale():
    document = build_document(build_intake(PROMPT, {}).project)

    assert _item(document, 5).state is SectionState.PENDING


def test_launch_section_states_the_baseline_vehicle_and_its_requirement():
    document = build_document(build_intake(PROMPT, {}).project)

    text = "\n".join(_section(document, "5.2").lines)

    assert "H-IIA" in text
    assert "100 Hz" in text
    assert "50 Hz" in text
    assert _item(document, 13).state is SectionState.PARTIAL


def test_subsystem_section_labels_its_lines_as_requirements_not_results():
    answers = {"communication": "UHF でテレメトリを降ろす"}
    document = build_document(build_intake(PROMPT, answers).project)

    section = _section(document, "5.3")

    assert any(line.startswith("通信系への要求: UHF") for line in section.lines)
    assert "要求" in section.pending_note


def test_orbit_outside_the_scope_is_flagged_in_the_system_section():
    prompt = "高度 5000 km、軌道傾斜角 51.6 度の 3U 衛星"
    document = build_document(build_intake(prompt, {}).project)

    assert "範囲外" in _section(document, "5.1").pending_note


def test_mission_analysis_shows_mass_and_temperature_marked_provisional():
    document = build_document(build_intake(PROMPT, {}).project)

    lines = _section(document, "2").lines

    assert any(line.startswith("総質量: 3.98 kg（暫定）") for line in lines)
    assert any(line.startswith("周回の最高温度") and "（暫定）" in line for line in lines)


def test_references_list_the_sources_of_the_values_used():
    document = build_document(build_intake(PROMPT, {}).project)

    urls = {item.url for item in document.references}

    assert "https://www.satcon.jp/contest/doc/1_boshu26.pdf" in urls
    assert any("nasa.gov" in url for url in urls)


def test_markdown_has_every_chapter_and_marks_pending_ones():
    document = build_document(build_intake(PROMPT, {}).project)

    assert "## 5.1" in document.markdown
    assert "## 7" in document.markdown
    assert "未計算" in document.markdown
    assert "https://www.satcon.jp/contest/doc/1_boshu26.pdf" in document.markdown
