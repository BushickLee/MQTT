from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskPhase = Literal["normal", "early_warning", "imminent_fall", "post_fall"]
RawRiskPhase = Literal[
    "normal",
    "early_warning",
    "imminent_fall",
    "post_fall",
    "stable",
    "unstable",
    "fall_like",
    "fallen",
    "caution",
    "high_risk",
    "near_fall",
    "fall_detected",
]
AlertLevel = Literal["normal", "warning", "critical", "emergency"]
RawAlertLevel = Literal["normal", "warning", "critical", "emergency", "none", "post_fall"]
NotificationTarget = Literal["guardian", "os_background", "in_app"]
RiskObjectType = Literal["chair", "sofa", "table", "bed"]

PHASES: tuple[RiskPhase, ...] = (
    "normal",
    "early_warning",
    "imminent_fall",
    "post_fall",
)

RiskProbabilities = dict[RiskPhase, float]
RawRiskProbabilities = dict[str, float]

PHASE_ALIASES: dict[str, RiskPhase] = {
    "normal": "normal",
    "stable": "normal",
    "early_warning": "early_warning",
    "unstable": "early_warning",
    "caution": "early_warning",
    "high_risk": "early_warning",
    "imminent_fall": "imminent_fall",
    "fall_like": "imminent_fall",
    "near_fall": "imminent_fall",
    "post_fall": "post_fall",
    "fallen": "post_fall",
    "fall_detected": "post_fall",
}

ALERT_LEVEL_ALIASES: dict[str, AlertLevel] = {
    "none": "normal",
    "normal": "normal",
    "warning": "warning",
    "critical": "critical",
    "post_fall": "emergency",
    "emergency": "emergency",
}


def canonical_phase(phase: str) -> RiskPhase:
    return PHASE_ALIASES[phase]


def canonical_alert_level(alert_level: str) -> AlertLevel:
    return ALERT_LEVEL_ALIASES[alert_level]


class RawRiskEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    frame_id: int = Field(ge=0)
    timestamp: str
    phase: RawRiskPhase
    phase_ko: str
    alert_level: RawAlertLevel
    confidence: float = Field(ge=0.0, le=1.0)
    object_type: RiskObjectType
    object_type_ko: str
    camera_id: str | None = None
    probabilities: RawRiskProbabilities | None = None
    hls_url: str | None = None
    thumbnail_url: str | None = None

    @field_validator(
        "event_id",
        "timestamp",
        "phase_ko",
        "object_type",
        "object_type_ko",
        mode="after",
    )
    @classmethod
    def require_non_empty(cls, value: str) -> str:
        if value.strip() == "":
            raise ValueError("field must not be empty")
        return value

    @field_validator("probabilities", mode="after")
    @classmethod
    def validate_probabilities(
        cls,
        value: RawRiskProbabilities | None,
    ) -> RawRiskProbabilities | None:
        if value is None:
            return value
        for phase, probability in value.items():
            if phase not in PHASE_ALIASES:
                raise ValueError(f"unsupported probability phase: {phase}")
            if probability < 0.0 or probability > 1.0:
                raise ValueError(f"probability for {phase} must be between 0 and 1")
        return value


class RiskAlert(BaseModel):
    event_id: str
    camera_id: str
    frame_id: int
    timestamp: str
    phase: RiskPhase
    phase_ko: str
    alert_level: AlertLevel
    confidence: float = Field(ge=0.0, le=1.0)
    probabilities: RiskProbabilities
    guardian_message: str
    hls_url: str
    thumbnail_url: str | None = None
    object_type: RiskObjectType
    object_type_ko: str
    notification_targets: list[Literal["os_background", "in_app"]]
    notification_target: NotificationTarget
    source_phase: str | None = None
    source_alert_level: str | None = None
