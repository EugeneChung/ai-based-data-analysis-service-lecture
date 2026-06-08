# deli-da-bot

Socket Mode 기반 Slack 봇 — 강의용 데모. 세 가지 호출 방식만 받아서 그대로 echo 한다.

| 트리거 | 이벤트 | 동작 |
|---|---|---|
| 채널에서 `@deli-bot 질문…` | `app_mention` | 스레드에 `app_mention received` 카드 |
| 봇 DM | `message.im` | DM 채팅에 `DM received` 카드 |
| 화이트리스트 채널의 일반 채팅 | `message.channels` (또는 `message.groups`) | 스레드에 `reply-all received` 카드 |

분석·SQL·LLM 호출 없음. 순수하게 **이벤트 수신 → 응답 경로** 검증 용도.

---

## 0. 사전 준비

- Python 3.11+
- Slack 워크스페이스 admin 권한 (앱 설치 위해)
- 워크스페이스 ID: `T0B737V1WLD`
- 테스트 채널 예: `C0B7A7WA360`

---

## 1. Slack App 생성 (manifest 방식)

1. <https://api.slack.com/apps> → **Create New App** → **From a manifest**
2. 워크스페이스 선택 (`T0B737V1WLD`)
3. `manifest.yaml` 내용을 그대로 붙여넣기 → **Next** → **Create**

manifest 가 자동 설정해 주는 것:
- Bot 표시 이름: `deli-bot`
- Bot scopes (9개)
- Event Subscriptions: `app_mention`, `message.im`, `message.channels`, `message.groups`
- Socket Mode: **ON** (이게 핵심 — HTTP webhook URL 불필요)

---

## 2. 토큰 발급

### Bot Token (`xoxb-...`)
- **OAuth & Permissions** → **Install to Workspace** → 권한 허용
- 설치 후 페이지 상단 **Bot User OAuth Token** 복사 → `SLACK_BOT_TOKEN`

### App-Level Token (`xapp-...`)
Socket Mode WebSocket 연결용. Bot Token 과 별개.

- **Basic Information** → **App-Level Tokens** → **Generate Token and Scopes**
- Name: 아무거나 (`socket-token` 등)
- Scope 추가: `connections:write`
- **Generate** → `xapp-…` 복사 → `SLACK_APP_TOKEN`

---

## 3. 채널 초대

봇이 메시지를 보내려면 채널에 들어가 있어야 한다.

```text
/invite @deli-bot
```

테스트 채널 `C0B7A7WA360` 에서 실행. DM 은 초대 불필요.

reply-all 모드를 쓸 거면 그 채널 ID 를 `REPLY_ALL_CHANNEL_IDS` 에 추가.
채널 ID 확인: 채널 이름 클릭 → 하단 **Channel ID** 복사 (또는 URL `…/client/T…/C…` 의 `C` 부분).

---

## 4. 실행

```bash
cd ~/project/ai-based-data-analysis-service-lecture/deli-da-bot

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# .env 편집 — SLACK_BOT_TOKEN, SLACK_APP_TOKEN 채우기
# reply-all 테스트하려면 REPLY_ALL_CHANNEL_IDS=C0B7A7WA360

python bot.py
```

성공 로그:
```
[INFO] deli-da-bot: Starting Deli Slack Bot in Socket Mode...
[INFO] deli-da-bot: reply-all whitelist: {'C0B7A7WA360'}
[INFO] slack_bolt.AsyncApp: A new session has been established (session id: ...)
```

---

## 5. 테스트 시나리오

채널 `C0B7A7WA360` 에서:

| 입력 | 기대 |
|---|---|
| `@deli-bot 안녕` | 봇이 스레드에 `app_mention received` 카드 |
| (DM 창에서) `테스트` | 봇이 DM 에 `DM received` 카드 |
| (REPLY_ALL_CHANNEL_IDS 설정 시) 그 채널에 `반응 테스트` | 봇이 스레드에 `reply-all received` 카드 |

봇 자기 메시지에는 반응하지 않도록 가드 있음 (`bot_id` 체크 + 멘션 토큰 중복 방지).

---

## 6. 트러블슈팅

- **`SLACK_BOT_TOKEN` KeyError** → `.env` 누락 or `load_dotenv()` 가 못 읽음. 작업 디렉토리에서 실행했는지 확인
- **봇이 채널 메시지에 반응 안 함** → `/invite @deli-bot` 으로 채널 가입했는지 확인
- **DM 보냈는데 무응답** → App Home → Messages tab **enabled** 인지 (manifest 에 켜져 있음, 재설치 필요할 수 있음)
- **`not_in_channel` 에러** → 위와 동일, 채널 초대 필요
- **WebSocket 연결 안 됨** → `SLACK_APP_TOKEN` 의 scope 가 `connections:write` 인지 확인
- **이벤트 안 들어옴** → manifest 적용 후 **OAuth & Permissions → Reinstall to Workspace** 필요

---

## 7. 다음 단계 (이 데모에서는 안 함)

- 봇 텍스트에 LLM(Claude Agent SDK) 답변 붙이기 → taeho/myungsub-da-bot 방향
- 스레드 컨텍스트 가져오기 (`conversations_replies`) + session 영속화
- 차트 생성 + `files_upload_v2` 업로드
- `data-gateway-mcp` 호출
