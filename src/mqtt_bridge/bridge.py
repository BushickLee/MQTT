from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from mqtt_bridge.config import BridgeSettings
from mqtt_bridge.message import build_alert
from mqtt_bridge.models import RawRiskEvent

LOGGER = logging.getLogger(__name__)
SUCCESS_CODES = {0, mqtt.MQTT_ERR_SUCCESS}


@dataclass(frozen=True)
class PublishedAlert:
    topic: str
    notification_target: str
    payload: dict[str, Any]


def publish_alerts(
    client: Any,
    raw_event: RawRiskEvent,
    settings: BridgeSettings,
) -> list[PublishedAlert]:
    """Publish one raw event to guardian, OS-background, and in-app topics."""

    published: list[PublishedAlert] = []
    topic_targets = (
        (settings.guardian_topic, "guardian"),
        (settings.os_background_topic, "os_background"),
        (settings.in_app_topic, "in_app"),
    )

    for topic, target in topic_targets:
        alert = build_alert(raw_event, settings, notification_target=target)
        json_payload = alert.model_dump_json(exclude_none=True)
        info = client.publish(topic, json_payload, qos=settings.qos, retain=settings.retain)
        if info is not None and hasattr(info, "rc") and info.rc not in SUCCESS_CODES:
            raise RuntimeError(f"MQTT publish failed for {topic}: rc={info.rc}")
        published.append(
            PublishedAlert(
                topic=topic,
                notification_target=target,
                payload=alert.model_dump(exclude_none=True),
            )
        )

    return published


def handle_raw_payload(
    client: Any,
    payload: bytes | str,
    settings: BridgeSettings,
) -> list[PublishedAlert]:
    raw_event = RawRiskEvent.model_validate_json(payload)
    return publish_alerts(client, raw_event, settings)


def _reason_code_value(reason_code: Any) -> int:
    if hasattr(reason_code, "value"):
        return int(reason_code.value)
    return int(reason_code)


def _on_connect(client: mqtt.Client, userdata: Any, *args: Any) -> None:
    settings = userdata if isinstance(userdata, BridgeSettings) else BridgeSettings.from_env()
    reason_code = args[1] if len(args) == 2 else args[-2]

    if _reason_code_value(reason_code) != 0:
        LOGGER.error("MQTT connect failed: %s", reason_code)
        return

    client.subscribe(settings.raw_topic, qos=settings.qos)
    LOGGER.info("Subscribed to %s with QoS %s", settings.raw_topic, settings.qos)


def _on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
    settings = userdata if isinstance(userdata, BridgeSettings) else BridgeSettings.from_env()

    try:
        published = handle_raw_payload(client, message.payload, settings)
    except (ValueError, ValidationError) as exc:
        LOGGER.warning("Ignored invalid raw risk event on %s: %s", message.topic, exc)
        return

    LOGGER.info(
        "Forwarded raw risk event to %s",
        ", ".join(item.topic for item in published),
    )


def create_client(settings: BridgeSettings) -> mqtt.Client:
    if hasattr(mqtt, "CallbackAPIVersion"):
        client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            client_id=settings.client_id,
        )
    else:
        client = mqtt.Client(client_id=settings.client_id)
    client.user_data_set(settings)
    client.on_connect = _on_connect
    client.on_message = _on_message

    if settings.username:
        client.username_pw_set(settings.username, settings.password)

    return client


def connect_with_retry(client: mqtt.Client, settings: BridgeSettings) -> None:
    while True:
        try:
            client.connect(settings.broker_host, settings.broker_port, keepalive=60)
            return
        except OSError as exc:
            LOGGER.warning(
                "MQTT broker unavailable at %s:%s (%s). Retrying in %ss.",
                settings.broker_host,
                settings.broker_port,
                exc,
                settings.connect_retry_seconds,
            )
            time.sleep(settings.connect_retry_seconds)


def run_bridge(settings: BridgeSettings | None = None) -> None:
    settings = settings or BridgeSettings.from_env()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    client = create_client(settings)
    connect_with_retry(client, settings)
    LOGGER.info(
        "MQTT risk alert bridge started: %s:%s",
        settings.broker_host,
        settings.broker_port,
    )
    client.loop_forever()
