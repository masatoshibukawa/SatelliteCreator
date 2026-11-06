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


def test_mission_analysis_shows_the_calculated_orbit():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "2")

    assert section.state is SectionState.PARTIAL
    assert "軌道周期: 92.6 分" in section.lines
    assert any(line.startswith("最大の日陰時間: 36.1 分") for line in section.lines)
    assert "円軌道" in section.pending_note


def test_stand_in_note_appears_only_when_mass_and_thermal_were_calculated():
    prompt = "高度 500 km、傾斜角 97 度の 6U 衛星"

    with_bus = _section(build_document(build_intake(PROMPT, {}).project), "2")
    without_bus = _section(build_document(build_intake(prompt, {}).project), "2")

    assert "目安" in with_bus.pending_note
    assert "目安" not in without_bus.pending_note


def test_mission_analysis_is_pending_without_an_orbit():
    document = build_document(build_intake("光通信を実証したい", {}).project)

    section = _section(document, "2")

    assert section.state is SectionState.PENDING
    assert section.lines == ()


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


def test_markdown_has_every_chapter_and_marks_pending_ones():
    document = build_document(build_intake(PROMPT, {}).project)

    assert "## 5.1" in document.markdown
    assert "## 7" in document.markdown
    assert "未計算" in document.markdown


def test_system_section_lists_the_equipment_mass_by_group():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "5.1")
    text = "\n".join(section.lines)

    assert "ミッション: 961.7 g（MOT、LTS、SCC）" in text
    assert "質量余裕: 102.9 g" in text
    assert "寸法と配置" in section.pending_note


def test_system_section_without_a_bus_lists_no_equipment():
    document = build_document(build_intake("高度 500 km、傾斜角 97 度の 6U 衛星", {}).project)

    section = _section(document, "5.1")

    assert not any("質量余裕" in line for line in section.lines)
    assert "搭載機器" in section.pending_note


def test_subsystem_section_shows_calculated_results_beside_the_requirements():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "5.3")
    text = "\n".join(section.lines)

    assert "通信系の結果: 回線マージン:" in text
    assert "電源系の結果: 1 周回の発電量:" in text
    assert "熱制御系の結果: 周回の最高温度:" in text
    assert "構体系の結果: 安全余裕の概算:" in text
    assert "未計算" not in section.pending_note
    assert "姿勢制御系" in section.pending_note


def test_subsystem_section_has_no_results_without_a_bus():
    document = build_document(build_intake("高度 500 km、傾斜角 97 度の 6U 衛星", {}).project)

    assert not any("通信系の結果" in line for line in _section(document, "5.3").lines)


def test_ground_section_reports_the_link_from_the_bus_and_the_ledger():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "5.4")
    text = "\n".join(section.lines)

    assert section.state is SectionState.PARTIAL
    assert "周波数 2.285 GHz" in text
    assert "伝送速度 50 kbps" in text
    assert "最低仰角 5 度" in text
    assert "回線マージン:" in text


def test_ground_section_stays_pending_without_a_link_calculation():
    document = build_document(build_intake("高度 500 km、傾斜角 97 度の 6U 衛星", {}).project)

    section = _section(document, "5.4")

    assert section.state is SectionState.PENDING
    assert section.lines == ()


def test_document_shows_no_formulas_and_no_references():
    document = build_document(build_intake(PROMPT, {}).project)

    assert "T = 2π" not in document.markdown
    assert "## 出典" not in document.markdown
    assert "http" not in document.markdown


def test_summary_counts_the_checks_that_ran():
    document = build_document(build_intake(PROMPT, {}).project)

    section = _section(document, "8")

    assert section.title == "まとめ"
    assert "3U の衛星を、高度 400 km" in section.lines[0]
    assert "整合チェックは実行した" in section.lines[1]


def test_summary_is_pending_without_a_design():
    document = build_document(build_intake("小型衛星で大気を測りたい", {}).project)

    assert _section(document, "8").state is SectionState.PENDING


def test_system_section_reports_the_chosen_equipment_and_its_mass_change():
    prompt = "高度 500 km、軌道傾斜角 97.5 度の 1U CubeSat で地球を撮影したい"
    document = build_document(build_intake(prompt, {}, equipment=("camera_large",)).project)

    text = "\n".join(_section(document, "5.1").lines)

    assert "ミッション機器の選択: 望遠カメラ（400 g、暫定）" in text
    assert "選択による質量の変化: +380.0 g" in text
