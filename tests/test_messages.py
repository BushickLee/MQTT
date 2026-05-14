import pytest
from pydantic import ValidationError

from mqtt_bridge.config import BridgeSettings
from mqtt_bridge.message import build_alert, build_guardian_message
from mqtt_bridge.models import RawRiskEvent


RAW_PAYLOAD = {
    "event_id": "evt-20260427-001",
    "frame_id": 1234,
    "timestamp": "2026-04-28T23:11:35+09:00",
    "phase": "imminent_fall",
    "phase_ko": "낙상 임박",
    "alert_level": "critical",
    "confidence": 0.91,
    "object_type": "chair",
    "object_type_ko": "의자",
}


def make_raw_event(**updates: object) -> RawRiskEvent:
    payload = {**RAW_PAYLOAD, **updates}
    return RawRiskEvent.model_validate(payload)


def test_guardian_message_uses_batchim_particle() -> None:
    raw_event = make_raw_event()

    assert build_guardian_message(raw_event) == (
        "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다."
    )


def test_guardian_message_uses_no_batchim_particle() -> None:
    raw_event = make_raw_event(phase="early_warning", phase_ko="조기경보")

    assert build_guardian_message(raw_event) == (
        "아이가 의자의 가장자리에서 조기경보가 일어났습니다."
    )


def test_missing_required_field_raises_validation_error() -> None:
    payload = dict(RAW_PAYLOAD)
    payload.pop("event_id")

    with pytest.raises(ValidationError):
        RawRiskEvent.model_validate(payload)


def test_confidence_over_one_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        make_raw_event(confidence=1.2)


def test_unsupported_object_type_raises_validation_error() -> None:
    with pytest.raises(ValidationError):
        make_raw_event(object_type="bookshelf")


def test_default_fields_are_enriched_for_frontend_contract() -> None:
    settings = BridgeSettings()
    raw_event = make_raw_event()

    alert = build_alert(raw_event, settings)
    payload = alert.model_dump(exclude_none=True)

    assert alert.hls_url == "http://localhost:8000/static/live/stream.m3u8"
    assert alert.object_type == "chair"
    assert alert.object_type_ko == "의자"
    assert "camera_id" not in payload
    assert "probabilities" not in payload


def test_alias_phase_is_normalized_for_frontend_contract() -> None:
    settings = BridgeSettings()
    raw_event = make_raw_event(phase="near_fall")

    alert = build_alert(raw_event, settings)
    payload = alert.model_dump(exclude_none=True)

    assert alert.phase == "imminent_fall"
    assert alert.source_phase == "near_fall"
    assert "probabilities" not in payload


def test_post_fall_alert_level_alias_maps_to_emergency() -> None:
    settings = BridgeSettings()
    raw_event = make_raw_event(
        phase="fall_detected",
        phase_ko="낙상 감지",
        alert_level="post_fall",
    )

    alert = build_alert(raw_event, settings)

    assert alert.phase == "post_fall"
    assert alert.alert_level == "emergency"
    assert alert.source_phase == "fall_detected"
    assert alert.source_alert_level == "post_fall"


def test_notification_targets_are_set_per_payload() -> None:
    settings = BridgeSettings()
    raw_event = make_raw_event()

    os_payload = build_alert(raw_event, settings, notification_target="os_background")
    in_app_payload = build_alert(raw_event, settings, notification_target="in_app")

    assert os_payload.notification_target == "os_background"
    assert os_payload.guardian_message
    assert os_payload.phase_ko == "낙상 임박"
    assert os_payload.event_id == "evt-20260427-001"
    assert os_payload.phase == "imminent_fall"
    assert in_app_payload.notification_target == "in_app"
