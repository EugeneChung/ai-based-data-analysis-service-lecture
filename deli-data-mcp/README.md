# deli-data-mcp

딜리(Deli) 예제용 **data-gateway MCP 서버**. 사내
`teamdable/data-gateway-mcp` 를 강의 크기로 줄인 공개 예시다.

옆에 있는 [`deli-db-mcp`](../deli-db-mcp) 가 *모델이 직접 SQL 을 쓰는*
자유 탐색 도구라면, 이쪽은 그 반대다. **이미 검토를 마친 고정 SQL** 을
파라미터만 받는 MCP Tool 로 노출한다. 매번 같은 질문(대시보드, 정기
리포트)을 모델이 매번 새로 SQL 을 짜게 두지 않고, 한 번 정해 둔 쿼리를
재사용한다.

한 에이전트가 두 커넥터를 같이 쓴다 — 반복되는 신뢰 질문은
`deli-gateway`, 처음 보는 탐색 질문은 `deli-db`.

## 핵심 아이디어: Tool = 파일 두 개

Tool 하나는 짝이 되는 파일 두 개로 정의된다. 서버 코드는 건드리지 않는다.

```
catalog/<name>.yaml   파라미터, 기본값, 가드레일, 엔진
queries/<name>.sql    파라미터 자리를 비워 둔 SQL (Jinja2 템플릿)
```

예: `catalog/restaurant_sales.yaml` + `queries/restaurant_sales.sql` 이
`restaurant_sales` Tool 하나가 된다. Tool 을 추가하려면 이 두 파일을
더 넣으면 끝이다.

## 한 번의 호출이 거치는 길

모든 고정 Tool 은 `service.py` 의 한 경로를 똑같이 지난다.

```
호출 파라미터
  └─(1) validate     선언된 파라미터와 대조 + 타입 검사 (validator.py)
        (2) build     기본값·날짜 구간·행 수 상한 계산 (query_builder.py)
        (3) render    Jinja2 템플릿에 안전한 값 채우기 (query_builder.py)
        (4) execute   읽기 전용·상한 적용 실행 + 로그 (executor.py)
            └─ 결과(JSON)
```

`(1) validate` 가 **신뢰 경계**다. 템플릿은 `{{ 값 }}` 자리에 값을
글자 그대로 끼워 넣으므로, 값은 템플릿에 닿기 전에 안전한 형태로
바뀌어야 한다. 그래서 validator 가 한곳에서:

- `integer` → `int(value)`
- `number` → `float(value)`
- `date` → `YYYY-MM-DD` 형식만 통과
- `string` → `pymysql.escape_string` 으로 따옴표 처리

required 누락·미선언 파라미터·형식 오류는 여기서 막히고, 쿼리는 아예
만들어지지 않는다. 검사 규칙이 한 번만 적혀 모든 Tool 에 똑같이 걸린다.

## 가드레일

`config.yaml` 의 전역 값을 `catalog/<name>.yaml` 이 Tool 별로 덮어쓴다.

| 항목 | 뜻 |
|------|----|
| `max_rows` | 반환 행 수 상한 (초과분은 `truncated=true`) |
| `timeout_seconds` | `MAX_EXECUTION_TIME` 으로 거는 실행 시간 상한 |
| `date_range_days` | 날짜를 안 주면 적용할 기본 조회 구간 |
| `limit` | 기본 행 수 (항상 `max_rows` 이하로 깎임) |

실행은 `deli-db-mcp` 와 같은 보호를 쓴다 — 읽기 전용 트랜잭션,
서버측 실행 시간 상한, 행 수 하드캡(`limit+1` 을 가져와 잘림 감지).

## 실행

데이터베이스는 `deli-db-mcp` 와 같은 것을 본다(같은 `DELI_DB_*` 변수).
먼저 일회용 로컬 MySQL 을 띄운다.

```bash
cd ../deli-db-mcp
./local-mysql.sh start      # 일회용 MySQL + 시드 데이터
```

그다음 게이트웨이를 띄운다.

```bash
cd ../deli-data-mcp
python3 -m pip install -r requirements.txt

# stdio (Claude Desktop 설정 파일 경로)
python3 server.py

# 또는 HTTP — "Add custom connector" 로 등록 (8001 포트)
./serve-http.sh             # http://127.0.0.1:8001/mcp
```

`deli-db-mcp` 는 8000, 이쪽은 8001 이라 둘을 동시에 띄워 한 에이전트에
커넥터 둘로 붙일 수 있다.

```bash
claude mcp add deli-gateway -- python3 "$(pwd)/server.py"
```

## 파일

| 파일 | 역할 |
|------|------|
| `catalog/*.yaml` | Tool 명세 — 파라미터·기본값·가드레일 |
| `queries/*.sql` | 짝이 되는 SQL 템플릿 (Jinja2) |
| `config.yaml` | 전역 기본값·가드레일 |
| `catalog.py` | yaml + sql → `ToolSpec` 로드 |
| `validator.py` | 파라미터 검사 (신뢰 경계) |
| `query_builder.py` | 기본값 병합 + 템플릿 렌더 |
| `executor.py` | 읽기 전용·상한 실행 |
| `service.py` | validate→build→render→execute 묶음 |
| `server.py` | catalog 를 돌며 FastMCP Tool 로 등록 |
| `db.py` | MySQL 연결 (deli-db-mcp 와 동일) |

> 강의용 축소판이다. 사내 `data-gateway-mcp` 는 같은 구조에 엔진을
> 여러 개(mysql·trino·athena), Tool 탐색용 메타 Tool(`list_tools`·
> `describe_tool`), 스캔량 상한(`max_scan_mb`) 같은 것을 더 얹은 형태다.
> "고정 Tool 직접 만들어 보기" 실습의 참고 구현으로 쓰면 된다.
