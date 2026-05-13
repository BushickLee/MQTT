from __future__ import annotations

from mqtt_bridge.config import BridgeSettings
from mqtt_bridge.models import (
    PHASES,
    RawRiskEvent,
    RiskAlert,
    RiskProbabilities,
    canonical_alert_level,
    canonical_phase,
)


def has_korean_final_consonant(text: str) -> bool:
    for char in reversed(text.strip()):
        code_point = ord(char)
        if 0xAC00 <= code_point <= 0xD7A3:
            return (code_point - 0xAC00) % 28 != 0
    return False


def subject_particle(text: str) -> str:
    return "이" if has_korean_final_consonant(text) else "가"


def build_guardian_message(raw_event: RawRiskEvent) -> str:
    particle = subject_particle(raw_event.phase_ko)
    return (
        f"아이가 {raw_event.object_type_ko}의 가장자리에서 "
        f"{raw_event.phase_ko}{particle} 일어났습니다."
    )


def build_default_probabilities(phase: str, confidence: float) -> RiskProbabilities:
    remaining = max(0.0, 1.0 - confidence)
    other_phases = [candidate for candidate in PHASES if candidate != phase]
    probabilities = {candidate: 0.0 for candidate in PHASES}
    probabilities[phase] = confidence

    if other_phases:
        share = round(remaining / len(other_phases), 6)
        for candidate in other_phases:
            probabilities[candidate] = share
        adjustment = round(1.0 - sum(probabilities.values()), 6)
        probabilities[other_phases[-1]] = round(probabilities[other_phases[-1]] + adjustment, 6)

    return probabilities


def normalize_probabilities(raw_event: RawRiskEvent) -> RiskProbabilities:
    phase = canonical_phase(raw_event.phase)
    probabilities = build_default_probabilities(phase, raw_event.confidence)
    if raw_event.probabilities is None:
        return probabilities

    for phase, value in raw_event.probabilities.items():
        probabilities[canonical_phase(phase)] = value
    return probabilities


def build_alert(
    raw_event: RawRiskEvent,
    settings: BridgeSettings | None = None,
    notification_target: str = "guardian",
) -> RiskAlert:
    settings = settings or BridgeSettings()
    phase = canonical_phase(raw_event.phase)
    alert_level = canonical_alert_level(raw_event.alert_level)

    return RiskAlert(
        event_id=raw_event.event_id,
        camera_id=raw_event.camera_id or settings.default_camera_id,
        frame_id=raw_event.frame_id,
        timestamp=raw_event.timestamp,
        phase=phase,
        phase_ko=raw_event.phase_ko,
        alert_level=alert_level,
        confidence=raw_event.confidence,
        probabilities=normalize_probabilities(raw_event),
        guardian_message=build_guardian_message(raw_event),
        hls_url=raw_event.hls_url or settings.default_hls_url,
        thumbnail_url=raw_event.thumbnail_url or settings.default_thumbnail_url,
        object_type=raw_event.object_type,
        object_type_ko=raw_event.object_type_ko,
        notification_targets=["os_background", "in_app"],
        notification_target=notification_target,
        source_phase=raw_event.phase if raw_event.phase != phase else None,
        source_alert_level=raw_event.alert_level if raw_event.alert_level != alert_level else None,
    )
