import json

from mqtt_bridge.bridge import BridgeRuntime, handle_raw_payload, publish_alerts
from mqtt_bridge.config import BridgeSettings
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


class FakeMqttClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def publish(self, topic: str, payload: str, qos: int, retain: bool) -> None:
        self.calls.append(
            {
                "topic": topic,
                "payload": json.loads(payload),
                "qos": qos,
                "retain": retain,
            }
        )
        return type("PublishInfo", (), {"rc": 0})()


def test_publish_alerts_publishes_to_three_topics() -> None:
    settings = BridgeSettings()
    raw_event = RawRiskEvent.model_validate(RAW_PAYLOAD)
    client = FakeMqttClient()

    published = publish_alerts(client, raw_event, settings)

    assert [item.topic for item in published] == [
        "risk/alerts/guardian",
        "notifications/os-background",
        "notifications/in-app",
    ]
    assert [call["topic"] for call in client.calls] == [
        "risk/alerts/guardian",
        "notifications/os-background",
        "notifications/in-app",
    ]
    assert [call["payload"]["notification_target"] for call in client.calls] == [
        "guardian",
        "os_background",
        "in_app",
    ]
    assert all("camera_id" not in call["payload"] for call in client.calls)
    assert all("probabilities" not in call["payload"] for call in client.calls)
    assert all(call["qos"] == 1 for call in client.calls)
    assert all(call["retain"] is False for call in client.calls)


def test_handle_raw_payload_validates_json_and_publishes() -> None:
    settings = BridgeSettings()
    client = FakeMqttClient()

    handle_raw_payload(client, json.dumps(RAW_PAYLOAD).encode("utf-8"), settings)

    assert len(client.calls) == 3
    assert client.calls[1]["payload"]["guardian_message"] == (
        "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다."
    )


def make_raw_event(**updates: object) -> RawRiskEvent:
    payload = {**RAW_PAYLOAD, **updates}
    return RawRiskEvent.model_validate(payload)


def test_runtime_suppresses_normal_by_default_and_repeated_phase_globally() -> None:
    runtime = BridgeRuntime(BridgeSettings())

    assert runtime.should_forward(make_raw_event(phase="normal", alert_level="none")) is False
    assert runtime.should_forward(make_raw_event(phase="early_warning", confidence=0.70)) is True
    assert runtime.should_forward(make_raw_event(phase="early_warning", confidence=0.72)) is False
    assert runtime.should_forward(make_raw_event(phase="imminent_fall", confidence=0.90)) is True


def test_runtime_waits_for_two_low_confidence_early_warnings() -> None:
    runtime = BridgeRuntime(BridgeSettings())

    first = make_raw_event(event_id="evt-low-1", phase="early_warning", confidence=0.40)
    second = make_raw_event(event_id="evt-low-2", phase="early_warning", confidence=0.40)
    third = make_raw_event(event_id="evt-low-3", phase="early_warning", confidence=0.40)

    assert runtime.should_forward(first) is False
    assert runtime.should_forward(second) is True
    assert runtime.should_forward(third) is False


def test_runtime_suppresses_low_confidence_danger_phase() -> None:
    runtime = BridgeRuntime(BridgeSettings())

    assert runtime.should_forward(make_raw_event(phase="imminent_fall", confidence=0.59)) is False
    assert runtime.should_forward(make_raw_event(phase="imminent_fall", confidence=0.60)) is True
