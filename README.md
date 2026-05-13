# MQTT 위험 알림 중계 서비스

Fall Guard 위험 이벤트를 MQTT로 받아 보호자 알림 payload로 보강해 다시 publish하는 broker + bridge 구성입니다. HLS 영상 스트림과 분리된 경량 위험 이벤트 채널이며, 로컬 네트워크 시연 기준으로 설계했습니다.

## 역할

- Mosquitto MQTT broker 실행
- TCP MQTT listener `1883`, WebSocket MQTT listener `9001` 제공
- bridge가 `risk/alerts/raw` 토픽의 raw 위험 이벤트 구독
- 필수 필드와 값 범위 검증
- 프론트 `RiskAlert` 호환 payload 생성
- 보호자 메시지 생성
- `risk/alerts/guardian`, `notifications/os-background`, `notifications/in-app` 토픽으로 publish

실제 background/terminated 상태의 OS push는 FCM/APNs bridge 또는 Expo push token 연동이 필요합니다. 이 저장소는 외부 push API를 호출하지 않고, OS background용 payload와 mock-forward 구조까지만 제공합니다.

## 전체 실행

broker와 bridge를 함께 실행합니다.

```bash
docker compose up --build
```

열리는 포트:

- `1883`: Python/CLI/Edge publisher용 MQTT TCP
- `9001`: WebSocket MQTT client용 listener

## 기존 front/HLS와의 호환성 판정

이 MQTT repo만 실행한다고 기존 `front`와 `HLS`가 자동으로 end-to-end 연결되지는 않습니다.

- 기존 `HLS`는 HLS 영상 파일을 `http://localhost:8000/static/live/stream.m3u8`로 서빙하지만, MQTT로 raw 위험 이벤트를 publish하는 코드나 endpoint는 없습니다.
- 기존 `front`는 `mockRiskAlert`와 버튼 기반 로컬 알림 시뮬레이션만 사용하며, MQTT broker나 `notifications/in-app` topic을 subscribe하지 않습니다.
- 따라서 MQTT repo만 수정 가능한 조건에서는 broker/bridge 동작과 HLS URL payload 계약까지 검증할 수 있지만, 기존 front 화면에 MQTT 알림을 직접 띄우는 완전한 UI 연동은 불가능합니다.

기존 HLS와 함께 실행할 때는 HLS 서버를 별도로 띄운 뒤, raw MQTT payload의 `hls_url` 또는 `MQTT_DEFAULT_HLS_URL`을 HLS URL로 맞춥니다.

```bash
cd ../HLS
python3 -m venv .venv
source .venv/bin/activate
python -m pip install fastapi uvicorn opencv-python
uvicorn main:app --host 0.0.0.0 --port 8000
```

기존 front는 그대로 실행할 수 있지만, MQTT 알림 topic을 소비하지 않습니다.

```bash
cd ../front
npm install
npm start
```

## Bridge 단독 실행

외부 broker를 이미 띄운 경우 Python bridge만 실행할 수 있습니다.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
set -a
source .env
set +a
python -m mqtt_bridge
```

## 환경 변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `MQTT_BROKER_HOST` | `localhost` | MQTT broker host |
| `MQTT_BROKER_PORT` | `1883` | MQTT broker port |
| `MQTT_CLIENT_ID` | `risk-alert-bridge` | bridge client id |
| `MQTT_USERNAME` | empty | broker username |
| `MQTT_PASSWORD` | empty | broker password |
| `MQTT_RAW_TOPIC` | `risk/alerts/raw` | raw 이벤트 구독 topic |
| `MQTT_GUARDIAN_TOPIC` | `risk/alerts/guardian` | 통합 guardian publish topic |
| `MQTT_OS_BACKGROUND_TOPIC` | `notifications/os-background` | OS background 알림 publish topic |
| `MQTT_IN_APP_TOPIC` | `notifications/in-app` | 앱 내부 알림 publish topic |
| `MQTT_QOS` | `1` | subscribe/publish QoS |
| `MQTT_RETAIN` | `false` | publish retain 여부 |
| `MQTT_CONNECT_RETRY_SECONDS` | `3` | broker 연결 재시도 간격 |
| `MQTT_DEFAULT_CAMERA_ID` | `room-01` | raw에 `camera_id`가 없을 때 보강 |
| `MQTT_DEFAULT_HLS_URL` | `http://localhost:8000/static/live/stream.m3u8` | raw에 `hls_url`이 없을 때 보강 |
| `MQTT_DEFAULT_THUMBNAIL_URL` | empty | raw에 `thumbnail_url`이 없을 때 보강 |

## Topic 흐름

Subscribe:

- `risk/alerts/raw`

Publish:

- `risk/alerts/guardian`
- `notifications/os-background`
- `notifications/in-app`

기본 QoS는 `1`입니다.

전체 demo 흐름:

```text
Edge/Model/CLI publisher
  -> Mosquitto broker risk/alerts/raw
  -> mqtt_bridge
  -> Mosquitto broker notifications/in-app, notifications/os-background
  -> MQTT subscribers
```

기존 front는 마지막 `MQTT subscribers` 역할을 아직 구현하지 않습니다.

## Raw Payload 계약

필수 입력:

```json
{
  "event_id": "evt-20260427-001",
  "frame_id": 1234,
  "timestamp": "2026-04-28T23:11:35+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.91,
  "object_type": "chair",
  "object_type_ko": "의자"
}
```

선택 입력:

- `camera_id`
- `probabilities`
- `hls_url`
- `thumbnail_url`

`phase`는 `normal`, `early_warning`, `imminent_fall`, `post_fall` 중 하나입니다. `alert_level`은 `normal`, `warning`, `critical`, `emergency` 중 하나입니다. 최신 front의 `RiskObjectType`에 맞춰 `object_type`은 `chair`, `sofa`, `table`, `bed` 중 하나만 허용합니다. `confidence`와 각 probability 값은 `0` 이상 `1` 이하입니다.

## Output Payload 계약

각 publish payload는 프론트 `RiskAlert`와 호환되도록 root에 주요 필드를 둡니다.

```json
{
  "event_id": "evt-20260427-001",
  "camera_id": "room-01",
  "frame_id": 1234,
  "timestamp": "2026-04-28T23:11:35+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.91,
  "probabilities": {
    "normal": 0.03,
    "early_warning": 0.03,
    "imminent_fall": 0.91,
    "post_fall": 0.03
  },
  "guardian_message": "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.",
  "hls_url": "http://localhost:8000/static/live/stream.m3u8",
  "object_type": "chair",
  "object_type_ko": "의자",
  "notification_targets": ["os_background", "in_app"],
  "notification_target": "guardian"
}
```

`notifications/os-background`에는 `notification_target="os_background"`, `notifications/in-app`에는 `notification_target="in_app"`, `risk/alerts/guardian`에는 `notification_target="guardian"` payload가 publish됩니다.

OS background용 payload에는 Expo local notification에서 바로 사용할 수 있는 `guardian_message`, `phase_ko`, `event_id`, `camera_id`, `phase`가 포함됩니다.

## 보호자 메시지 규칙

기본 문장:

```text
아이가 {object_type_ko}의 가장자리에서 {phase_ko}{이/가} 일어났습니다.
```

`phase_ko`의 마지막 한글 음절에 받침이 있으면 `이`, 없으면 `가`를 사용합니다.

예시:

```text
아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.
```

## 수동 테스트

MQTT CLI로 raw 이벤트를 직접 publish합니다. HLS 서버를 같이 띄웠다면 `hls_url`은 기존 HLS endpoint를 가리킵니다.

```bash
mosquitto_pub -h localhost -p 1883 -t risk/alerts/raw -q 1 -m '{"event_id":"evt-20260427-001","frame_id":1234,"timestamp":"2026-04-28T23:11:35+09:00","phase":"imminent_fall","phase_ko":"낙상 임박","alert_level":"critical","confidence":0.91,"object_type":"chair","object_type_ko":"의자","hls_url":"http://localhost:8000/static/live/stream.m3u8"}'
```

출력 topic을 확인합니다.

```bash
mosquitto_sub -h localhost -p 1883 -t 'risk/alerts/guardian' -q 1
mosquitto_sub -h localhost -p 1883 -t 'notifications/os-background' -q 1
mosquitto_sub -h localhost -p 1883 -t 'notifications/in-app' -q 1
```

## 테스트

```bash
python -m pytest
```
