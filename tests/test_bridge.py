import json

from mqtt_bridge.bridge import handle_raw_payload, publish_alerts
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
