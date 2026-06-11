# AI 기반 데이터 분석 서비스 만들기 — Text-to-SQL 강의 자료

가상의 배달앱 **Deli** 도메인 위에서 자연어 질문을 MySQL 쿼리로 바꾸고(Text-to-SQL), 나아가 쿼리를 **실행**해 분석·시각화까지 하는 과정을 다루는 강의 자료.

## 구성

| 경로 | 내용 |
|---|---|
| `prompts/deli-simple-text2sql-sql-only-system-prompt.md` | SQL 생성까지만 하는 시스템 프롬프트 |
| `prompts/deli-simple-text2sql-system-prompt.md` | 실행+분석+그래프까지 하는 agentic 버전 (deli-db MCP 연결) |
| `prompts/deli-da-bot-system-prompt.md` | Slack 봇(deli-da-bot)용 추가분 — Slack mrkdwn 출력·도구 매핑·분석 가이드 |
| `deli-db-mcp/` | Deli DB를 조회하는 MCP 서버 (FastMCP, SELECT 전용) + 로컬 MySQL·시드 스크립트 |

## 두 가지 사용 방식

1. **수동 (SQL only)** — 프롬프트를 Claude(앱 / Project Instructions)에 넣고 질문 → SQL 생성. 사람이 직접 실행.
2. **자동 (agentic + MCP)** — agentic 프롬프트 + `deli-db` MCP connector → Claude가 `run_select` 로 쿼리를 직접 실행하고 결과를 분석·시각화.

## MCP 서버 (`deli-db-mcp/`)

`fastmcp` + `PyMySQL` 로 만든 read-only MySQL 조회 서버. 도구 4개를 노출한다.

| 도구 | 설명 |
|---|---|
| `list_tables` | 테이블 목록 + 행 수 추정 + 코멘트 |
| `get_schema` | 전체 `CREATE TABLE` (컬럼 COMMENT 포함) |
| `describe_table` | 단일 테이블 `CREATE TABLE` |
| `run_select` | 단일 `SELECT`/`WITH` 실행 → 결과 표 |

`run_select` 는 방어적으로 설계됨: `SELECT`/`WITH` 외 거부(쓰기·DDL·다중문 차단), 읽기 전용 트랜잭션, 실행시간(5초)·행 수(기본 200, 최대 1000) 상한.

### 로컬 실행 (macOS 기준)

요구: macOS, Python 3, Homebrew `mysql@8.0`. (`local-mysql.sh` 는 Apple Silicon Homebrew 경로 `/opt/homebrew/opt/mysql@8.0` 를 가정 — Intel Mac·Linux는 경로/설치 방식 조정 필요)

```bash
cd deli-mcp
# 1) 격리된 일회용 MySQL 기동 (Homebrew MySQL을 건드리지 않음)
./local-mysql.sh start
export DELI_DB_SOCKET=/tmp/deli-mcp-mysql.sock
export DELI_DB_PASSWORD=
# 2) DB 생성 + 스키마 적용 + 의존성 설치 + 합성 데이터 시드
./setup.sh
# 3) MCP 서버를 HTTP로 노출
./serve-http.sh                 # → http://127.0.0.1:8000/mcp
```

stdio 로 쓰려면 (Claude Desktop 설정 파일 방식):

```bash
claude mcp add deli-sql -- python3 "$(pwd)/server.py"
```

DB 접속은 환경변수로만 받는다 (`db.py`): `DELI_DB_SOCKET` 또는 `DELI_DB_HOST`/`PORT`, `DELI_DB_USER`(기본 `root`), `DELI_DB_PASSWORD`(기본 없음), `DELI_DB_NAME`(기본 `deli`). 소스에 자격증명을 하드코딩하지 않는다.

## Claude 앱에 연결 (custom connector)

로컬 서버를 외부에서 접근 가능한 https URL로 노출한 뒤 등록한다.

```bash
cloudflared tunnel --url http://127.0.0.1:8000
#   → https://<random>.trycloudflare.com   (끝에 /mcp 를 붙여 사용)
```

Claude 앱 → **Add custom connector** → Name `deli-db`, URL `https://<random>.trycloudflare.com/mcp`.

> **⚠️ 보안 경고**
>
> `cloudflared` 로 만든 URL은 **인증 없이 인터넷에 공개**된다. URL을 아는 사람은 누구나 이 MCP 서버로 DB를 조회할 수 있다.
>
> - **데모/테스트 용으로만** 쓰고, **끝나면 즉시 터널을 내릴 것** (`cloudflared` 프로세스 종료).
> - **실제 데이터·운영 DB에는 절대 연결하지 말 것.** 이 데모 DB는 민감정보 없는 합성 데이터다.
> - 서버는 방어적으로 설계돼 있으나(SELECT 전용·읽기 전용·상한), 공개 노출 위험 자체는 남는다. 가능하면 로컬(stdio)·사내망·인증 게이트를 우선할 것.

## 예시 질문

1. 카테고리별로 운영 중인 식당이 몇 개씩 있는지 알려주세요.
2. 지난달 영등포에 사는 20대가 가장 많이 주문한 메뉴 TOP 5는?

## 데이터 규모: 프롬프트 가정 vs 로컬 데모

프롬프트의 스키마 주석은 운영 규모(`orders` ~500M, `order_items` ~2.5B 행 등)를 가정해 파티션·인덱스 전략을 설명한다. 로컬 데모(`seed.py`)는 그보다 훨씬 작은 합성 데이터를 적재한다 — 쿼리 패턴 학습용이다.
