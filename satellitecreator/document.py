"""Builds the design document in the contest's format (rules, Annex 1 and section 6.1).

A chapter only states what the project record holds. Anything not computed yet stays pending
with a reason, so the document never shows a number that no calculation produced.
"""

from __future__ import annotations

from enum import StrEnum

from satellitecreator.catalog import load_reference_buses, reference_bus
from satellitecreator.core.ledger import Ledger
from satellitecreator.core.registry import load_constants, load_equations
from satellitecreator.design import (
    check_scope,
    envelope,
    form_factor,
    load_launch_vehicle,
    load_scope_limits,
)
from satellitecreator.document_results import (
    equipment_lines,
    ground_link_lines,
    subsystem_result_lines,
)
from satellitecreator.process import load_review_specs
from satellitecreator.project import Project, SuccessLevel
from satellitecreator.requirements import Function, RequirementLevel, RequirementStatus
from satellitecreator.schema import Frozen
from satellitecreator.simulation import format_entry, project_ledger

_SUBSYSTEM_LABELS = {
    Function.ORBIT: "軌道",
    Function.STRUCTURE: "構体系",
    Function.MISSION: "ミッション機器",
    Function.COMMUNICATION: "通信系",
    Function.POWER: "電源系",
    Function.ATTITUDE_CONTROL: "姿勢制御系",
    Function.ORBIT_CONTROL: "軌道制御系",
    Function.THERMAL_CONTROL: "熱制御系",
    Function.DATA_HANDLING: "データ処理系",
}
_STATUS_LABELS = {
    RequirementStatus.CONFIRMED: "確定",
    RequirementStatus.ASSUMED: "仮定",
    RequirementStatus.OPEN: "未定",
}
_SUCCESS_LABELS = {
    SuccessLevel.MINIMUM: "ミニマムサクセス",
    SuccessLevel.FULL: "フルサクセス",
    SuccessLevel.EXTRA: "エクストラサクセス",
}
_CUBESAT_SPECIFICATION_URL = (
    "https://www.nasa.gov/wp-content/uploads/2018/01/"
    "cubesatdesignspecificationrev14_12022-02-09.pdf"
)
_ORBITAL_MECHANICS_URL = (
    "https://ntrs.nasa.gov/api/citations/20205003902/downloads/"
    "Introduction%20to%20Orbital%20Mechanics%20and%20Spacecraft%20Attitudes"
    "%20for%20Thermal%20Engineers%20CHARTS%20PDF.pdf"
)
_SOURCE_TITLES = {
    "https://www.satcon.jp/contest/doc/1_boshu26.pdf": "第34回衛星設計コンテスト 募集要項",
    _CUBESAT_SPECIFICATION_URL: "CubeSat Design Specification Rev. 14.1",
    _ORBITAL_MECHANICS_URL: (
        "NASA, Introduction to Orbital Mechanics and Spacecraft Attitudes for Thermal Engineers"
    ),
    "https://nssdc.gsfc.nasa.gov/planetary/factsheet/earthfact.html": "NASA Earth Fact Sheet",
    "https://sma.jaxa.jp/TechDoc/Docs/JAXA-JERG-2-310A.pdf": "JERG-2-310A 熱制御系設計標準",
    "https://sma.jaxa.jp/TechDoc/Docs/JAXA-JERG-2-214A.pdf": "JERG-2-214A 電源系設計標準",
    "https://arxiv.org/pdf/1908.09501": (
        "CubeSat Communications: Recent Advances and Future Challenges"
    ),
    "https://physics.nist.gov/cgi-bin/cuu/Value?c": "NIST, speed of light",
    "https://physics.nist.gov/cgi-bin/cuu/Value?sigma": "NIST, Stefan-Boltzmann constant",
    "https://tfaws.nasa.gov/wp-content/uploads/On-Orbit_Thermal_Environments_TFAWS_2014.pdf": (
        "NASA TFAWS, Introduction to On-Orbit Thermal Environments"
    ),
    "https://www.satcon.jp/history/prize22/pdf/22_asj.pdf": "OPT-CUBE 解析書（第22回）",
    "https://www.space.pitt.edu/sites/default/files/2024-10/Arnold_AERO12.pdf": (
        "Arnold et al., Energy Budgeting for CubeSats（M-Cubed の電力収支）"
    ),
    "https://www.preprints.org/manuscript/202404.0391": (
        "Okuyama, 超小型衛星の固有振動数に関する論文（H-IIA の要求を引用）"
    ),
    "https://sma.jaxa.jp/TechDoc/Docs/JAXA-JMR-003E.pdf": "JMR-003E スペースデブリ発生防止標準",
    "https://sma.jaxa.jp/TechDoc/Docs/JAXA-JERG-2-100.pdf": "JERG-2-100 システム設計標準",
}


class SectionState(StrEnum):
    FILLED = "filled"
    PARTIAL = "partial"
    PENDING = "pending"


class Section(Frozen):
    number: str
    title: str
    state: SectionState
    lines: tuple[str, ...] = ()
    pending_note: str = ""


class ChecklistItem(Frozen):
    number: int
    label: str
    state: SectionState


class Reference(Frozen):
    title: str
    url: str


class Document(Frozen):
    title: str
    sections: tuple[Section, ...]
    checklist: tuple[ChecklistItem, ...]
    references: tuple[Reference, ...]
    markdown: str


def _pending(number: str, title: str, note: str) -> Section:
    return Section(number=number, title=title, state=SectionState.PENDING, pending_note=note)


def _mission_section(project: Project) -> Section:
    title = "ミッション要求（衛星の目的）と意義"
    requirements = project.at_level(RequirementLevel.MISSION)
    lines = tuple(f"要求: {item.statement}" for item in requirements)
    mission = project.mission
    if mission is None:
        note = "成果の受け手とサクセス基準が未定です"
        return Section(
            number="1", title=title, state=SectionState.PARTIAL, lines=lines, pending_note=note
        )
    details = (
        f"成果の受け手: {'、'.join(mission.stakeholders)}",
        *(f"{_SUCCESS_LABELS[item.level]}: {item.statement}" for item in mission.success_criteria),
    )
    state = SectionState.FILLED if mission.success_criteria else SectionState.PARTIAL
    return Section(number="1", title=title, state=state, lines=(*lines, *details))


def _analysis_section(ledger: Ledger) -> Section:
    title = "ミッション解析結果"
    lines = tuple(
        f"{item.label}: {format_entry(item, ledger.get(item.output))}（{item.formula}）"
        for item in load_equations()
        if item.summary and ledger.get(item.output) is not None
    )
    if not lines:
        return _pending("2", title, "軌道が決まると記載されます")
    stand_in = (
        "質量、熱、電源、回線は公開資料の機器構成を目安にした暫定値です。"
        if (ledger.get("total_mass_kg"))
        else ""
    )
    note = f"円軌道を仮定しています。{stand_in}"
    return Section(
        number="2", title=title, state=SectionState.PARTIAL, lines=lines, pending_note=note
    )


def _results_section(project: Project) -> Section:
    title = "得られる成果"
    criteria = project.mission.success_criteria if project.mission else ()
    if not criteria:
        return _pending("3", title, "サクセス基準が決まると記載されます")
    lines = tuple(item.statement for item in criteria)
    note = "運用で得られる成果の見積もりは未計算です"
    return Section(
        number="3", title=title, state=SectionState.PARTIAL, lines=lines, pending_note=note
    )


def _millimetres(value_m: float) -> str:
    return f"{round(value_m * 1000, 1):g}"


def _system_section(project: Project) -> Section:
    title = "システムの構成、衛星の形状、質量、機能、運用軌道"
    design = project.design
    if design is None:
        return _pending("5.1", title, "大きさと軌道が決まると記載されます")
    size = envelope(design.form_factor)
    dimensions = " × ".join(
        _millimetres(value) for value in (size.width_m, size.depth_m, size.length_m)
    )
    lines = (
        f"形状: {design.form_factor}（打上げ時の外形 {dimensions} mm）",
        f"質量の上限: {form_factor(design.form_factor).max_mass_kg:g} kg",
        f"軌道: 高度 {design.orbit.altitude_m / 1000:g} km、"
        f"軌道傾斜角 {design.orbit.inclination_deg:g} 度",
    )
    bus = reference_bus(design.form_factor)
    choices = (
        *((f"機器構成の目安: {bus.name}",) if bus else ()),
        *(
            ("姿勢: 太陽指向（反復設計で選択。熱の計算には未反映）",)
            if design.attitude == "sun_pointing"
            else ()
        ),
        *(
            (f"放熱面: {design.surface}、本体の {design.radiator_ratio:.0%}（反復設計で選択）",)
            if design.surface
            else ()
        ),
        *(
            (f"ヒータ: {design.heater_power_w:g} W（反復設計で追加）",)
            if design.heater_power_w
            else ()
        ),
    )
    equipment = equipment_lines(bus) if bus else ()
    lines = (*lines, *choices, *equipment)
    out_of_scope = "、".join(item.message for item in check_scope(design))
    missing = "機器の寸法と配置は未検討です" if bus else "搭載機器と質量配分は未計算です"
    note = out_of_scope or missing
    return Section(
        number="5.1", title=title, state=SectionState.PARTIAL, lines=lines, pending_note=note
    )


def _launch_section(project: Project) -> Section:
    title = "制約条件（打ち上げロケットとのインターフェース条件）"
    if project.design is None:
        return _pending("5.2", title, "大きさと軌道が決まると記載されます")
    max_mass_kg = form_factor(project.design.form_factor).max_mass_kg
    vehicle = load_launch_vehicle()
    lines = (
        f"CubeSat 放出ポッドを使う場合の質量上限: {max_mass_kg:g} kg",
        f"基準のロケット: {vehicle.name}",
        f"固有振動数の要求: 機軸方向 {vehicle.longitudinal_frequency_hz:g} Hz 以上、"
        f"機軸直交方向 {vehicle.lateral_frequency_hz:g} Hz 以上",
    )
    note = "ロケットの選定理由と機械環境条件の詳細は未検討です"
    return Section(
        number="5.2", title=title, state=SectionState.PARTIAL, lines=lines, pending_note=note
    )


def _subsystem_section(project: Project, ledger: Ledger) -> Section:
    title = "サブシステムの設計結果"
    requirements = project.at_level(RequirementLevel.SYSTEM)
    if not requirements:
        return _pending("5.3", title, "システム要求が決まると記載されます")
    lines = tuple(
        f"{_SUBSYSTEM_LABELS[item.function]}への要求: {item.statement}"
        f"（{_STATUS_LABELS[item.status]}）"
        for item in requirements
    )
    results = subsystem_result_lines(ledger, _SUBSYSTEM_LABELS)
    note = "姿勢制御系とデータ処理系は要求だけで、解析はありません"
    return Section(
        number="5.3",
        title=title,
        state=SectionState.PARTIAL,
        lines=(*lines, *results),
        pending_note=note,
    )


def _ground_section(project: Project, ledger: Ledger) -> Section:
    title = "データ取得のための地上系との関連"
    bus = reference_bus(project.design.form_factor) if project.design else None
    if bus is None or ledger.get("link_margin_db") is None:
        return _pending("5.4", title, "機器構成と軌道が決まると記載されます")
    note = "地上局の条件は公開資料の値を目安にしています。可視時間とデータ量は未計算です"
    return Section(
        number="5.4",
        title=title,
        state=SectionState.PARTIAL,
        lines=ground_link_lines(bus, ledger),
        pending_note=note,
    )


def _operations_section(project: Project) -> Section:
    title = "衛星の運用手順、データ取得手順"
    if not project.operations_concept:
        return _pending("5.5", title, "運用コンセプトが決まると記載されます")
    note = "運用シーケンスの詳細は未検討です"
    return Section(
        number="5.5",
        title=title,
        state=SectionState.PARTIAL,
        lines=(project.operations_concept,),
        pending_note=note,
    )


def _references() -> tuple[Reference, ...]:
    limits = load_scope_limits()
    sources = (
        *(item.source for item in limits.form_factors),
        *(item.source for item in limits.envelopes),
        limits.leo_max_altitude.source,
        load_launch_vehicle().source,
        *(item.source for item in load_review_specs()),
        *(item.source for item in load_reference_buses()),
        *(item.source for item in load_constants()),
        *(item.source for item in load_equations()),
    )
    unique = dict.fromkeys(source for source in sources if source)
    return tuple(Reference(title=_SOURCE_TITLES.get(url, url), url=url) for url in unique)


def _sections(
    project: Project, ledger: Ledger, references: tuple[Reference, ...]
) -> tuple[Section, ...]:
    return (
        _mission_section(project),
        _analysis_section(ledger),
        _results_section(project),
        _pending("4", "主張したい独創性または社会的効果", "対話の項目に追加すると記載されます"),
        _system_section(project),
        _launch_section(project),
        _subsystem_section(project, ledger),
        _ground_section(project, ledger),
        _operations_section(project),
        _pending(
            "6",
            "具体的なミッション達成方法、開発・運用内容及び費用",
            "部品カタログを実装すると記載されます",
        ),
        _pending("7", "開発・製造・打上スケジュール", "対話の項目に追加すると記載されます"),
        Section(
            number="8",
            title="まとめ、参考文献等",
            state=SectionState.PARTIAL,
            lines=tuple(item.title for item in references),
            pending_note="まとめは設計が完了すると記載されます",
        ),
    )


def _checklist(project: Project, ledger: Ledger) -> tuple[ChecklistItem, ...]:
    design_known = SectionState.PARTIAL if project.design else SectionState.PENDING
    mass_known = SectionState.PARTIAL if ledger.get("total_mass_kg") else SectionState.PENDING
    link_known = SectionState.PARTIAL if ledger.get("link_margin_db") else SectionState.PENDING
    power_known = (
        SectionState.PARTIAL if ledger.get("orbit_generated_energy_j") else SectionState.PENDING
    )
    thermal_known = (
        SectionState.PARTIAL if ledger.get("temperature_margin_k") else SectionState.PENDING
    )
    operations_known = SectionState.PARTIAL if project.operations_concept else SectionState.PENDING
    pending = SectionState.PENDING
    items = (
        ("打上げ時および軌道上の衛星形状", design_known),
        ("システムブロックダイアグラム", pending),
        ("搭載機器一覧（質量や寸法を含む）", mass_known),
        ("質量特性（全質量、慣性モーメントなど）", mass_known),
        ("軌道およびその設定根拠", pending),
        ("運用シーケンス", operations_known),
        ("姿勢プロファイル", pending),
        ("データ処理の流れと回線設計結果", link_known),
        ("姿勢制御が可能であること", pending),
        ("軌道制御が可能であること", pending),
        ("搭載機器の温度余裕", thermal_known),
        ("電力プロファイルとバッテリ容量", power_known),
        ("打上げロケットとのインターフェース条件", design_known),
    )
    return tuple(
        ChecklistItem(number=number, label=label, state=state)
        for number, (label, state) in enumerate(items, start=1)
    )


def _section_markdown(section: Section) -> str:
    body = [f"- {line}" for line in section.lines]
    if section.pending_note:
        body.append(f"\n> 未計算: {section.pending_note}")
    return "\n".join([f"## {section.number} {section.title}", "", *body])


def _to_markdown(
    title: str,
    sections: tuple[Section, ...],
    checklist: tuple[ChecklistItem, ...],
    references: tuple[Reference, ...],
) -> str:
    rows = [f"| {item.number} | {item.label} | {item.state} |" for item in checklist]
    links = [f"- [{item.title}]({item.url})" for item in references]
    return "\n\n".join(
        [
            f"# 設計書: {title}",
            *(_section_markdown(section) for section in sections),
            "\n".join(["## 記載項目の状況", "", "| 番号 | 項目 | 状態 |", "|---|---|---|", *rows]),
            "\n".join(["## 出典", "", *links]),
        ]
    )


def build_document(project: Project) -> Document:
    references = _references()
    ledger = project_ledger(project)
    sections = _sections(project, ledger, references)
    checklist = _checklist(project, ledger)
    return Document(
        title=project.name,
        sections=sections,
        checklist=checklist,
        references=references,
        markdown=_to_markdown(project.name, sections, checklist, references),
    )
