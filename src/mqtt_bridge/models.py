from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

RiskPhase = Literal["normal", "early_warning", "imminent_fall", "post_fall"]
AlertLevel = Literal["normal", "warning", "critical", "emergency"]
NotificationTarget = Literal["guardian", "os_background", "in_app"]
RiskObjectType = Literal["chair", "sofa", "table", "bed"]

PHASES: tuple[RiskPhase, ...] = (
    "normal",
    "early_warning",
    "imminent_fall",
    "post_fall",
)

RiskProbabilities = dict[RiskPhase, float]


class RawRiskEvent(BaseModel):
    model_config = ConfigDict(extra="allow")

    event_id: str
    frame_id: int = Field(ge=0)
    timestamp: str
    phase: RiskPhase
    phase_ko: str
    alert_level: AlertLevel
    confidence: float = Field(ge=0.0, le=1.0)
    object_type: RiskObjectType
    object_type_ko: str
    camera_id: str | None = None
    probabilities: RiskProbabilities | None = None
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
    def validate_probabilities(cls, value: RiskProbabilities | None) -> RiskProbabilities | None:
        if value is None:
            return value
        for phase, probability in value.items():
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
