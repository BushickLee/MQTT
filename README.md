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

## 기존 front/HLS/fall-guard-app와의 호환성 판정

이 MQTT repo만 실행한다고 기존 `front`, `HLS`, `fall-guard-app`가 자동으로 end-to-end 연결되지는 않습니다.

- 기존 `HLS`는 HLS 영상 파일을 `http://localhost:8000/static/live/stream.m3u8`로 서빙하지만, MQTT로 raw 위험 이벤트를 publish하는 코드나 endpoint는 없습니다.
- 기존 `front`는 `mockRiskAlert`와 버튼 기반 로컬 알림 시뮬레이션만 사용하며, MQTT broker나 `notifications/in-app` topic을 subscribe하지 않습니다.
- 기존 `fall-guard-app`는 Edge AI/backend/app 역할과 LSTM handoff 문서를 갖고 있지만, `backend/`, `edge/`, `configs/`에는 아직 MQTT 실행 코드가 없습니다.
- 따라서 MQTT repo만 수정 가능한 조건에서는 broker/bridge 동작, 모델 handoff payload 수용, HLS URL payload 계약까지 검증할 수 있지만, 기존 앱 화면에 MQTT 알림을 직접 띄우는 완전한 UI 연동은 불가능합니다.

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

## 다른 리포와 합칠 때의 통합 기준

이 저장소는 MQTT broker와 위험 알림 bridge만 책임집니다. `front`, `HLS`, `fall-guard-app`와 통합할 때는 각 리포의 역할을 아래처럼 분리합니다.

| 리포 | 통합 역할 | MQTT와 맞춰야 할 계약 |
| --- | --- | --- |
| `fall-guard-app` | Edge/model/backend 쪽 위험 이벤트 생산자 또는 backend 소비자 | 모델 결과에 `event_id`, `camera_id`, `frame_id`, `timestamp`, `object_type`, `object_type_ko`, `hls_url`을 보강해 `risk/alerts/raw`에 publish |
| `HLS` | 영상 스트림 제공자 | MQTT payload의 `hls_url`이 실제 HLS endpoint를 가리키도록 host/IP와 port를 맞춤 |
| `front` | 보호자 앱 UI | MQTT를 직접 처리하지 않고 backend REST 응답, FCM/Expo push payload, HLS URL을 소비 |
| backend / push bridge | MQTT 소비자와 앱 전달 계층 | `risk/alerts/guardian` 또는 `notifications/*` topic을 구독해 DB 저장, REST API 응답, FCM/APNs/Expo push로 전달 |

권장 end-to-end 흐름:

```text
fall-guard-app Edge/Model
  -> backend or publisher가 raw event 보강
  -> Mosquitto risk/alerts/raw
  -> mqtt_bridge validation/enrichment/gate
  -> Mosquitto risk/alerts/guardian
  -> backend / push bridge
  -> front REST response 또는 FCM/Expo push
  -> front가 hls_url로 HLS 영상 재생
```

통합 시 반드시 확인할 항목:

- `MQTT_DEFAULT_HLS_URL` 또는 raw `hls_url`은 모바일 기기에서 접근 가능한 LAN IP를 써야 합니다. `localhost`는 같은 장비 안에서만 의미가 있습니다.
- 현재 raw `timestamp` 계약은 ISO-8601 문자열입니다. `fall-guard-app` handoff 예시처럼 초 단위 숫자 timestamp를 쓰는 producer는 MQTT publish 전에 문자열 timestamp로 변환해야 합니다.
- `event_id`는 중복 알림 억제, DB 저장, 알림 상세 조회의 기준이 되므로 producer가 안정적으로 생성해야 합니다.
- debounce/rate gate는 한 계층만 책임져야 합니다. 현재 기본값은 이 bridge가 담당하지만, backend나 Edge runtime이 같은 책임을 맡으면 bridge gate 설정을 조정해야 합니다.
- 실제 background/terminated OS push는 이 저장소가 직접 수행하지 않습니다. `notifications/os-background` payload를 받아 FCM/APNs/Expo push로 넘기는 별도 bridge가 필요합니다.
- Mosquitto의 `allow_anonymous true` 설정은 로컬 시연용입니다. 배포 환경에서는 계정, ACL, TLS, 네트워크 제한을 별도로 적용해야 합니다.

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
| `MQTT_SUPPRESS_REPEATED_PHASE` | `true` | 같은 camera에서 마지막 publish와 같은 phase면 suppress |
| `MQTT_PUBLISH_NORMAL_EVENTS` | `false` | `normal` phase도 알림 topic으로 publish할지 여부 |
| `MQTT_EARLY_WARNING_CONFIDENCE_THRESHOLD` | `0.65` | `early_warning`을 1회만으로 publish할 confidence |
| `MQTT_DANGER_CONFIDENCE_THRESHOLD` | `0.60` | `imminent_fall`, `post_fall` publish 최소 confidence |
| `MQTT_EARLY_WARNING_CONSECUTIVE_COUNT` | `2` | 낮은 confidence의 `early_warning` publish에 필요한 연속 감지 횟수 |
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

과거 `mqtt-demo`의 `homcam/alerts/risk`와 일부 문서의 `home/home-001/event/danger`는 legacy/demo topic으로 보고, 현재 기준 topic은 `risk/alerts/raw`입니다. 다른 topic을 써야 하면 코드 수정 없이 `MQTT_RAW_TOPIC`으로 바꿉니다.

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

기준 `phase`는 `normal`, `early_warning`, `imminent_fall`, `post_fall`입니다. `fall-guard-app` 문서와 UI draft의 라벨 drift를 흡수하기 위해 raw 입력에서는 아래 alias도 허용하고 output에서는 기준 phase로 정규화합니다.

| raw phase | output phase |
| --- | --- |
| `normal`, `stable` | `normal` |
| `early_warning`, `unstable`, `caution`, `high_risk` | `early_warning` |
| `imminent_fall`, `fall_like`, `near_fall` | `imminent_fall` |
| `post_fall`, `fallen`, `fall_detected` | `post_fall` |

기준 `alert_level`은 최신 front 계약에 맞춰 `normal`, `warning`, `critical`, `emergency`입니다. raw 입력에서는 모델 handoff의 `none`과 `post_fall`도 허용하며, 각각 `normal`, `emergency`로 정규화합니다.

최신 front의 `RiskObjectType`과 `fall-guard-app` furniture schema에 맞춰 `object_type`은 `chair`, `sofa`, `table`, `bed` 중 하나만 허용합니다. `confidence`와 각 probability 값은 `0` 이상 `1` 이하입니다. `probabilities` key도 phase alias를 허용하며 output에서는 기준 phase key만 publish합니다.

## Publish 정책

bridge는 raw model tick을 그대로 전부 알림 topic으로 내보내지 않습니다. 회의록과 model handoff 기준으로 debounce/rate gate는 한 곳에서만 적용해야 하므로 이 저장소에서는 bridge runtime이 기본 gate를 담당합니다.

- `normal`: 기본값에서는 publish하지 않습니다.
- `early_warning`: confidence가 `MQTT_EARLY_WARNING_CONFIDENCE_THRESHOLD` 이상이면 즉시 publish하고, 낮으면 같은 camera에서 `MQTT_EARLY_WARNING_CONSECUTIVE_COUNT`회 연속 감지된 뒤 publish합니다.
- `imminent_fall`, `post_fall`: confidence가 `MQTT_DANGER_CONFIDENCE_THRESHOLD` 이상이면 publish합니다.
- 같은 camera에서 마지막으로 publish한 phase와 동일한 phase는 `MQTT_SUPPRESS_REPEATED_PHASE=true`일 때 suppress합니다.

이 정책은 OS push 폭주와 in-app modal 반복 표시를 막기 위한 기본값입니다. 이후 Edge runtime이나 backend가 debounce를 맡게 되면 이 bridge의 gate를 끄거나 해당 계층 하나만 책임지도록 맞춰야 합니다.

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

raw `phase` 또는 `alert_level`이 alias였으면 output에 `source_phase`, `source_alert_level`을 추가해 원본 값을 보존합니다. front `RiskAlert`가 모르는 extra field는 JSON consumer가 무시할 수 있게 root에 둡니다.

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

## 문서 갱신 원칙

유의미한 기능 추가 또는 계약 변경이 있으면 코드와 같은 단위로 README도 함께 갱신합니다.

- topic 이름, payload 필드, validation 규칙, debounce 정책, 환경 변수 기본값이 바뀌면 관련 표와 예시 JSON을 수정합니다.
- 다른 리포와의 연결 방식이 바뀌면 `다른 리포와 합칠 때의 통합 기준` 섹션을 먼저 갱신합니다.
- README만 바뀌는 문서 작업도 별도 커밋으로 남겨 추적과 되돌리기가 쉽도록 합니다.
