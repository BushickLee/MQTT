from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value


def _env_optional(name: str) -> str | None:
    value = os.getenv(name)
    if value is None or value == "":
        return None
    return value


def _env_int(name: str, default: int) -> int:
    raw = _env(name, str(default))
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


def _env_float(name: str, default: float) -> float:
    raw = _env(name, str(default))
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number") from exc


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, str(default)).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


@dataclass(frozen=True)
class BridgeSettings:
    broker_host: str = "localhost"
    broker_port: int = 1883
    client_id: str = "risk-alert-bridge"
    username: str | None = None
    password: str | None = None
    raw_topic: str = "risk/alerts/raw"
    guardian_topic: str = "risk/alerts/guardian"
    os_background_topic: str = "notifications/os-background"
    in_app_topic: str = "notifications/in-app"
    qos: int = 1
    retain: bool = False
    connect_retry_seconds: int = 3
    suppress_repeated_phase: bool = True
    publish_normal_events: bool = False
    early_warning_confidence_threshold: float = 0.65
    danger_confidence_threshold: float = 0.60
    early_warning_consecutive_count: int = 2
    default_hls_url: str = "http://localhost:8000/static/live/stream.m3u8"
    default_thumbnail_url: str | None = None

    @classmethod
    def from_env(cls) -> "BridgeSettings":
        return cls(
            broker_host=_env("MQTT_BROKER_HOST", cls.broker_host),
            broker_port=_env_int("MQTT_BROKER_PORT", cls.broker_port),
            client_id=_env("MQTT_CLIENT_ID", cls.client_id),
            username=_env_optional("MQTT_USERNAME"),
            password=_env_optional("MQTT_PASSWORD"),
            raw_topic=_env("MQTT_RAW_TOPIC", cls.raw_topic),
            guardian_topic=_env("MQTT_GUARDIAN_TOPIC", cls.guardian_topic),
            os_background_topic=_env("MQTT_OS_BACKGROUND_TOPIC", cls.os_background_topic),
            in_app_topic=_env("MQTT_IN_APP_TOPIC", cls.in_app_topic),
            qos=_env_int("MQTT_QOS", cls.qos),
            retain=_env_bool("MQTT_RETAIN", cls.retain),
            connect_retry_seconds=_env_int(
                "MQTT_CONNECT_RETRY_SECONDS",
                cls.connect_retry_seconds,
            ),
            suppress_repeated_phase=_env_bool(
                "MQTT_SUPPRESS_REPEATED_PHASE",
                cls.suppress_repeated_phase,
            ),
            publish_normal_events=_env_bool(
                "MQTT_PUBLISH_NORMAL_EVENTS",
                cls.publish_normal_events,
            ),
            early_warning_confidence_threshold=_env_float(
                "MQTT_EARLY_WARNING_CONFIDENCE_THRESHOLD",
                cls.early_warning_confidence_threshold,
            ),
            danger_confidence_threshold=_env_float(
                "MQTT_DANGER_CONFIDENCE_THRESHOLD",
                cls.danger_confidence_threshold,
            ),
            early_warning_consecutive_count=_env_int(
                "MQTT_EARLY_WARNING_CONSECUTIVE_COUNT",
                cls.early_warning_consecutive_count,
            ),
            default_hls_url=_env("MQTT_DEFAULT_HLS_URL", cls.default_hls_url),
            default_thumbnail_url=_env_optional("MQTT_DEFAULT_THUMBNAIL_URL"),
        )
