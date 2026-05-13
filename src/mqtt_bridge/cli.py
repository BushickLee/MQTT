from __future__ import annotations

from mqtt_bridge.bridge import run_bridge
from mqtt_bridge.config import BridgeSettings


def main() -> None:
    run_bridge(BridgeSettings.from_env())
