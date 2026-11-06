import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from satellitecreator.catalog import load_reference_buses, reference_bus
from satellitecreator.equipment import (
    UnknownEquipmentError,
    check_selection,
    equipment_effect,
    load_equipment,
    selected_options,
)
from satellitecreator.intake import build_intake, load_question_options
from satellitecreator.session import run_session
from satellitecreator.simulation import project_ledger

ONE_UNIT = "高度 500 km、軌道傾斜角 97.5 度の 1U CubeSat で地球を撮影したい"


def _value(prompt, name, equipment=()):
    return project_ledger(build_intake(prompt, {}, equipment=equipment).project).get(name).value


def test_every_bus_has_one_default_option_per_category():
    categories = [item.id for item in load_equipment().categories]

    for bus in load_reference_buses():
        selected = selected_options(bus.form_factor, ())
        assert [item.category for item in selected] == categories


def test_default_equipment_leaves_the_published_bus_unchanged():
    for bus in load_reference_buses():
        effect = equipment_effect(bus, ())

        assert effect.mass_delta_kg == 0
        assert effect.power_delta_w == 0
        assert effect.generation_ratio == 1
        assert effect.link == bus.link


def test_a_choice_replaces_only_the_option_of_its_category():
    selected = selected_options("1U", ("camera_large",))

    assert [item.id for item in selected] == [
        "camera_large",
        "body_cells",
        "uhf_radio",
        "magnetorquer",
    ]


def test_heavier_payload_raises_the_total_mass_by_the_difference():
    base = _value(ONE_UNIT, "total_mass_kg")

    assert _value(ONE_UNIT, "total_mass_kg", ("camera_large",)) == pytest.approx(base + 0.38)


def test_deployed_panels_raise_the_generated_energy():
    base = _value(ONE_UNIT, "orbit_generated_energy_j")

    chosen = _value(ONE_UNIT, "orbit_generated_energy_j", ("deployed_panels",))

    assert chosen == pytest.approx(base * 2.48)


def test_radio_choice_uses_the_link_of_the_matching_bus():
    effect = equipment_effect(reference_bus("1U"), ("s_band_radio",))

    assert effect.link == reference_bus("3U").link


def test_unknown_equipment_is_rejected():
    with pytest.raises(UnknownEquipmentError):
        check_selection(("warp_drive",))


def test_session_lists_the_choices_with_the_selection():
    result = run_session(ONE_UNIT, {}, ("camera_large",))

    payload = result.equipment[0]
    assert payload.id == "payload"
    assert payload.selected == "camera_large"
    assert "望遠カメラ" in [item.label for item in payload.options]


def test_session_offers_no_equipment_without_a_bus():
    assert run_session("高度 500 km、傾斜角 97 度の 6U 衛星", {}).equipment == ()


def test_diagrams_carry_ledger_values():
    diagrams = run_session(ONE_UNIT, {}).diagrams

    assert diagrams.altitude_m == 500e3
    assert diagrams.inclination_deg == 97.5
    assert diagrams.orbit_period_s > 0
    assert diagrams.link_margin_db is not None
    assert diagrams.usable_sunlit_power_w > 0
    assert diagrams.provisional


def test_diagrams_stay_empty_before_an_orbit_is_known():
    diagrams = run_session("小型衛星で大気を測りたい", {}).diagrams

    assert diagrams.altitude_m is None
    assert not diagrams.provisional


def test_api_rejects_unknown_equipment():
    client = TestClient(create_app())

    response = client.post("/session", json={"prompt": ONE_UNIT, "equipment": ["warp_drive"]})

    assert response.status_code == 422


def test_every_question_offers_options():
    questions = build_intake(ONE_UNIT, {}).questions

    assert all(item.options for item in questions)
    assert set(load_question_options()) == {item.id for item in questions}


def test_every_offered_option_can_be_read_as_an_answer():
    for question in build_intake("衛星", {}).questions:
        for option in question.options:
            answered = build_intake("衛星", {question.id: option}).questions
            state = next(item for item in answered if item.id == question.id)
            assert state.answered, (question.id, option)
