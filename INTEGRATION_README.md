# Fall Guard MQTT 통합 README

이 문서는 `MQTT` 리포를 `front`, `HLS`, `fall-guard-app`와 합칠 때 참고하는 통합 가이드입니다. 현재 MQTT 리포는 Mosquitto broker와 Python bridge를 제공하며, 다른 리포의 코드를 직접 수정하지 않습니다.

## 통합 목표

MQTT는 영상 스트림을 직접 운반하지 않고, 낙상 위험 이벤트만 경량 메시지로 전달합니다. HLS는 영상 URL을 제공하고, MQTT payload는 그 URL을 포함해 앱이나 backend가 위험 알림과 영상을 함께 보여줄 수 있게 합니다.

권장 목표 흐름:

```text
fall-guard-app Edge/Model
  -> raw 위험 이벤트 생성
  -> backend 또는 publisher가 필수 필드 보강
  -> MQTT broker risk/alerts/raw
  -> mqtt_bridge 검증, 정규화, 알림 메시지 생성, gate 적용
  -> MQTT broker risk/alerts/guardian
  -> backend / push bridge
  -> front REST 응답 또는 FCM/APNs/Expo push
  -> front가 hls_url로 HLS 영상 재생
```

## 리포별 책임

| 리포 | 책임 | MQTT와 맞출 항목 |
| --- | --- | --- |
| `MQTT` | Mosquitto broker, 위험 이벤트 bridge, payload 검증과 정규화 | topic, payload contract, debounce/gate, HLS URL 보강 |
| `fall-guard-app` | 모델 추론, Edge/runtime, backend 후보 영역 | 모델 결과에 이벤트 메타데이터를 붙여 `risk/alerts/raw`로 publish |
| `HLS` | 라이브 영상과 clip 정적 파일 제공 | `hls_url`이 실제 접근 가능한 HLS endpoint를 가리키도록 네트워크 주소 조정 |
| `front` | 보호자 앱 UI, 알림 표시, HLS 재생 | MQTT 직접 구독이 아니라 REST 또는 push payload를 통해 `RiskAlert` 수신 |
| backend / push bridge | MQTT 소비, DB 저장, REST API, OS push | `risk/alerts/guardian` 또는 `notifications/*` 구독 후 앱 전달 |

## 실행 순서

1. HLS 서버를 실행합니다.

```bash
cd ../HLS
uvicorn main:app --host 0.0.0.0 --port 8000
```

2. MQTT broker와 bridge를 실행합니다.

```bash
cd ../MQTT
docker compose up --build
```

3. 모델 또는 테스트 publisher가 raw topic에 이벤트를 publish합니다.

```bash
mosquitto_pub -h localhost -p 1883 -t risk/alerts/raw -q 1 -m '{"event_id":"evt-001","frame_id":1234,"timestamp":"2026-05-14T12:00:00+09:00","phase":"imminent_fall","phase_ko":"낙상 임박","alert_level":"critical","confidence":0.91,"object_type":"chair","object_type_ko":"의자","hls_url":"http://192.168.0.12:8000/static/live/stream.m3u8"}'
```

4. backend 또는 push bridge가 output topic을 구독합니다.

```bash
mosquitto_sub -h localhost -p 1883 -t risk/alerts/guardian -q 1
mosquitto_sub -h localhost -p 1883 -t notifications/os-background -q 1
mosquitto_sub -h localhost -p 1883 -t notifications/in-app -q 1
```

5. `front`는 backend REST 응답이나 push payload에 포함된 `RiskAlert`와 `hls_url`을 사용합니다.

## Raw 입력 계약

`risk/alerts/raw`에 publish하는 최소 payload:

```json
{
  "event_id": "evt-001",
  "frame_id": 1234,
  "timestamp": "2026-05-14T12:00:00+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.91,
  "object_type": "chair",
  "object_type_ko": "의자"
}
```

권장 추가 필드:

```json
{
  "hls_url": "http://192.168.0.12:8000/static/live/stream.m3u8",
  "thumbnail_url": "http://192.168.0.12:8000/static/clips/thumb.jpg"
}
```

주의:

- 현재 `timestamp`는 ISO-8601 문자열을 기준으로 합니다. `fall-guard-app` handoff 예시의 초 단위 숫자 timestamp는 publish 전에 문자열 timestamp로 변환해야 합니다.
- 같은 위험 episode는 같은 `event_id`를 유지하고, 새 위험 episode는 새 `event_id`를 사용합니다. MQTT bridge는 같은 `event_id`와 `phase`의 반복 publish만 suppress합니다.
- `object_type`은 `chair`, `sofa`, `table`, `bed` 중 하나여야 합니다.
- `confidence` 값은 `0.0` 이상 `1.0` 이하입니다.
- `phase` alias는 입력에서 허용되지만, output은 `normal`, `early_warning`, `imminent_fall`, `post_fall`로 정규화됩니다.
- 표시용 카메라 이름과 위치가 필요하면 MQTT alert가 아니라 backend `/stream` API에서 `camera_name`, `camera_location`, `hls_url`, `is_active`, `last_seen_at` 형태로 제공합니다.

## Output 계약

bridge는 아래 세 topic에 publish합니다.

| topic | 목적 | `notification_target` |
| --- | --- | --- |
| `risk/alerts/guardian` | backend와 통합 소비자가 기준으로 삼는 canonical 위험 알림 | `guardian` |
| `notifications/os-background` | OS push bridge가 사용할 알림 payload | `os_background` |
| `notifications/in-app` | 앱 내부 알림 또는 modal 표시용 payload | `in_app` |

output payload는 `front`의 `RiskAlert`와 호환되도록 주요 필드를 root에 둡니다.

```json
{
  "event_id": "evt-001",
  "frame_id": 1234,
  "timestamp": "2026-05-14T12:00:00+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.91,
  "object_type": "chair",
  "object_type_ko": "의자",
  "guardian_message": "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.",
  "hls_url": "http://192.168.0.12:8000/static/live/stream.m3u8",
  "notification_targets": ["os_background", "in_app"],
  "notification_target": "guardian"
}
```

`notification_target`, `notification_targets`, `source_phase`, `source_alert_level`은 MQTT/backend 소비용 내부 필드입니다. backend가 `GET /alerts`, `GET /alerts/{event_id}`로 front에 내려줄 때는 아래 `RiskAlert` 필드만 유지하면 됩니다.

```json
{
  "event_id": "evt-001",
  "frame_id": 1234,
  "timestamp": "2026-05-14T12:00:00+09:00",
  "phase": "imminent_fall",
  "phase_ko": "낙상 임박",
  "alert_level": "critical",
  "confidence": 0.91,
  "object_type": "chair",
  "object_type_ko": "의자",
  "guardian_message": "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.",
  "hls_url": "http://192.168.0.12:8000/static/live/stream.m3u8",
  "thumbnail_url": "http://backend-ip/thumbnails/evt-001.jpg"
}
```

## Stream API 계약

front는 카메라 정보를 MQTT alert에서 읽지 않고 backend `/stream` 응답에서 읽습니다.

```json
{
  "camera_name": "아이방 카메라",
  "camera_location": "아이방",
  "hls_url": "http://jetson-ip:8000/static/live/stream.m3u8",
  "is_active": true,
  "last_seen_at": "2026-05-12T14:32:15+09:00"
}
```

## Push payload 매핑

`notifications/os-background` payload를 Expo push로 넘길 때는 front의 notification listener가 상세 화면으로 이동할 수 있도록 `data.event_id`를 반드시 포함합니다.

```json
{
  "title": "낙상 임박 위험 알림",
  "body": "아이가 의자의 가장자리에서 낙상 임박이 일어났습니다.",
  "data": {
    "event_id": "evt-001",
    "phase": "imminent_fall",
    "object_type": "chair"
  }
}
```

## 네트워크 설정

모바일 기기와 Jetson, 개발 PC가 같은 LAN에 있을 때는 `localhost` 사용을 피합니다.

| 실행 위치 | 권장 주소 |
| --- | --- |
| HLS 서버 | `http://<HLS_HOST_LAN_IP>:8000/static/live/stream.m3u8` |
| MQTT TCP | `<MQTT_HOST_LAN_IP>:1883` |
| MQTT WebSocket | `ws://<MQTT_HOST_LAN_IP>:9001` |

Docker Compose 내부에서 bridge가 broker에 붙을 때만 `MQTT_BROKER_HOST=mosquitto`를 사용합니다. 외부 publisher나 subscriber는 Docker service name이 아니라 host LAN IP 또는 `localhost`를 사용해야 합니다.

## Debounce와 알림 정책

현재 bridge는 기본적으로 다음 gate를 적용합니다.

- `normal`: publish하지 않음
- `early_warning`: confidence `0.65` 이상이면 즉시 publish, 낮으면 단일 stream에서 정확히 2회 연속 감지된 시점에 한 번 publish
- `imminent_fall`, `post_fall`: confidence `0.60` 이상이면 publish
- 단일 stream에서 마지막 publish와 같은 `event_id`와 `phase`가 반복되면 기본적으로 suppress

통합 시 debounce는 한 계층만 책임져야 합니다. Edge runtime이나 backend가 이미 debounce를 담당한다면 MQTT bridge의 관련 환경 변수를 조정합니다.

## 현재 한계와 후속 작업

- `front`는 현재 MQTT를 직접 구독하지 않습니다. backend REST 또는 push bridge가 필요합니다.
- 실제 background/terminated OS push는 이 리포가 직접 호출하지 않습니다. `notifications/os-background`를 FCM/APNs/Expo push로 전달하는 계층이 필요합니다.
- Mosquitto 설정은 로컬 시연용입니다. 운영 배포에는 인증, ACL, TLS, 네트워크 제한이 필요합니다.
- 같은 `event_id`와 `phase` 반복 suppress는 기본 스팸 방지용입니다. 실제 서비스에서 더 정교한 제어가 필요하면 episode timeout 또는 cooldown 기반 정책을 backend와 합의합니다.
- 숫자 timestamp를 그대로 받을 필요가 있으면 MQTT input model을 확장해야 합니다.

## 통합 체크리스트

- [ ] HLS URL이 모바일 기기에서 직접 열리는지 확인
- [ ] raw publisher가 같은 위험 episode에서는 같은 `event_id`, 새 위험 episode에서는 새 `event_id`를 쓰는지 확인
- [ ] raw publisher가 `frame_id`, `timestamp`를 안정적으로 생성하는지 확인
- [ ] raw `timestamp` 형식이 MQTT 계약과 맞는지 확인
- [ ] `risk/alerts/raw` publish 후 `risk/alerts/guardian` 수신 확인
- [ ] backend 또는 push bridge가 canonical alert를 저장하거나 앱으로 전달하는지 확인
- [ ] front가 받은 `hls_url`로 영상을 재생하는지 확인
- [ ] debounce 책임 계층이 하나만 남아 있는지 확인
- [ ] 데모 LAN과 배포 환경의 broker 보안 설정을 분리했는지 확인

## 문서 갱신 규칙

통합에 영향을 주는 변경은 코드와 같은 커밋 단위로 이 문서를 갱신합니다.

- topic 이름 변경
- payload 필드 추가, 삭제, 타입 변경
- validation 또는 alias 규칙 변경
- debounce/gate 정책 변경
- HLS URL 기본값 변경
- front/backend/push bridge 책임 변경
