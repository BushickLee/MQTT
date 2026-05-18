# MQTT 구조 쉬운 설명

이 저장소는 낙상 위험 이벤트를 받아서 보호자 알림으로 바꿔 주는 MQTT 중계 서비스입니다. 영상 스트리밍 자체를 처리하지 않고, "위험이 발생했다"는 작은 JSON 메시지만 빠르게 주고받는 역할입니다.

## 한 줄 구조

```text
위험 이벤트 생산자 -> MQTT broker -> mqtt_bridge -> 보호자 알림 topic -> 앱/backend/모니터
```

## 각 구성요소 역할

### 1. 위험 이벤트 생산자

모델, Edge 코드, 테스트 CLI 같은 쪽입니다. 사람이 넘어질 것 같거나 넘어진 상황을 감지하면 raw JSON을 만듭니다.

이 이벤트는 `risk/alerts/raw` topic으로 보냅니다.

예시:

```json
{
  "event_id": "evt-001",
  "frame_id": 1234,
  "timestamp": "2026-05-18T16:34:00+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.93,
  "object_type": "chair",
  "object_type_ko": "의자"
}
```

### 2. MQTT broker

메시지 중간 허브입니다. 생산자와 소비자가 직접 서로를 몰라도 topic 이름만 맞으면 메시지를 주고받을 수 있게 합니다.

기본 포트는 두 개입니다.

- `1883`: 일반 MQTT TCP 연결
- `9001`: 브라우저가 붙을 수 있는 WebSocket MQTT 연결

Docker가 있으면 Mosquitto broker를 씁니다. Docker가 없는 로컬 확인 환경에서는 `amqtt` Python broker로 같은 포트를 띄워 확인할 수 있습니다.

### 3. mqtt_bridge

이 저장소의 핵심 Python 서비스입니다. `risk/alerts/raw`를 구독하다가 위험 이벤트를 받으면 아래 일을 합니다.

- 필수 필드가 있는지 확인
- `phase`, `alert_level`, `confidence`, `object_type` 값이 유효한지 검사
- HLS URL이 없으면 기본값을 넣음
- 보호자에게 보여줄 한국어 문장 생성
- 같은 위험 이벤트가 너무 많이 반복되지 않도록 일부 이벤트 억제
- 앱/backend가 쓰기 쉬운 알림 payload로 다시 publish

### 4. 출력 topic

bridge는 검증된 이벤트를 세 가지 topic으로 다시 보냅니다.

- `risk/alerts/guardian`: backend나 보호자 알림 저장 계층용
- `notifications/os-background`: FCM/APNs/Expo push bridge로 넘길 payload용
- `notifications/in-app`: 앱 실행 중 화면 알림 또는 브라우저 모니터용

### 5. 시각 확인용 브라우저 모니터

`tools/mangsa-mqtt-monitor.html`은 `ws://localhost:9001`로 broker에 붙어서 `notifications/in-app` topic을 구독합니다.

이 페이지를 열어 둔 상태에서 raw 이벤트를 쏘면 화면에 최신 알림 카드와 원본 payload가 표시됩니다. 실제 앱 UI가 아직 MQTT를 직접 구독하지 않아도, bridge가 알림을 제대로 내보내는지 눈으로 확인할 수 있습니다.

브라우저 모니터는 `mqtt.js`를 CDN에서 불러오므로 처음 열 때 인터넷 연결이 필요합니다.

## 실제 실행 흐름

1. broker 실행
2. bridge 실행
3. 테스트 이벤트를 `risk/alerts/raw`로 publish
4. bridge가 이벤트를 검증하고 보호자 메시지를 생성
5. bridge가 `notifications/in-app` 등 출력 topic으로 publish
6. 브라우저 모니터나 subscriber가 최종 알림 payload를 수신

## 최종 알림 payload 예시

```json
{
  "event_id": "codex-visual-browser-20260518-005",
  "frame_id": 5,
  "timestamp": "2026-05-18T16:34:00+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.93,
  "object_type": "chair",
  "object_type_ko": "의자",
  "guardian_message": "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.",
  "hls_url": "http://localhost:8000/static/live/stream.m3u8",
  "notification_targets": ["os_background", "in_app"],
  "notification_target": "in_app"
}
```

## 이 구조에서 중요한 점

- MQTT는 영상 파일을 보내는 용도가 아니라 위험 알림 신호를 보내는 용도입니다.
- HLS 영상 URL은 payload 안에 들어가지만, 영상 서버는 별도로 떠 있어야 합니다.
- 현재 front 앱은 MQTT topic을 직접 구독하지 않습니다.
- 실제 휴대폰 background push는 이 저장소가 직접 호출하지 않습니다. `notifications/os-background`를 받아 FCM, APNs, Expo로 넘기는 별도 push bridge가 필요합니다.
- 로컬 시연에서는 익명 MQTT 접속을 허용하지만, 배포에서는 계정, ACL, TLS, 네트워크 제한이 필요합니다.

## 빠른 확인 명령

Docker 환경:

```bash
docker compose up --build
```

Docker 없는 로컬 확인. broker와 bridge는 각각 다른 터미널에서 실행합니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]" amqtt
amqtt -c broker/amqtt-broker.yaml
```

```bash
source .venv/bin/activate
python -m mqtt_bridge
```

브라우저 모니터:

```bash
cmd.exe /C start "" "tools\\mangsa-mqtt-monitor.html"
```

테스트 이벤트 publish:

```bash
amqtt_pub --url mqtt://localhost:1883 -t risk/alerts/raw -q 1 -m '{"event_id":"evt-demo-001","frame_id":1,"timestamp":"2026-05-18T16:34:00+09:00","phase":"imminent_fall","phase_ko":"낙상 임박","alert_level":"critical","confidence":0.93,"object_type":"chair","object_type_ko":"의자"}'
```

출력 확인:

```bash
amqtt_sub --url mqtt://localhost:1883 -t notifications/in-app -n 1 -q 1
```
