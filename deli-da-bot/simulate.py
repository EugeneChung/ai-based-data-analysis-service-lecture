#!/usr/bin/env python3
"""deli-da-bot 시뮬레이터 — Claude API 토큰 없이 da-bot 전체 흐름을 재현한다.

슬라이드(text-to-sql 강의)의 da-bot 흐름:

    [1] Slack 이벤트(@멘션/DM/reply-all)
    [2] 스레드 컨텍스트 가져오기 (conversations_replies)
    [3] 질문 검증 + 세션 결정 (thread_key → resume / new)
    [4] ClaudeSDKClient.query(질문 + 스레드 컨텍스트)
    [5] SDK multi-turn 루프 — Claude ↔ 도구
            run_select(sql)  (deli-db MCP, SELECT 실행)
            create_chart(...) (차트 파일)
    [6] 답변 + 차트 업로드(files_upload_v2) → Slack 스레드
    [7] session_id 저장 (후속 질문이 같은 세션으로 이어지게)

이 파일은 위 7단계를 그대로 돌린다. 단 외부 의존 세 군데만 '가짜'로 바꿔
토큰·DB·슬랙 워크스페이스 없이 실행된다:

    Claude Agent SDK  →  FakeAgent     (정해진 시나리오 재생; 실제 LLM 추론 대신)
    deli-db / MySQL   →  FakeDeliDB    (임베드한 작은 데이터셋을 파이썬으로 집계)
    Slack             →  FakeSlack     (스레드 응답을 콘솔에 출력)

실제 봇으로 바꿀 때는 이 세 클래스만 각각 ClaudeSDKClient / deli-db MCP /
slack_bolt 로 갈아끼우면 된다. 가운데 오케스트레이션(handle)은 그대로 쓴다.

시스템 프롬프트는 prompts/deli-simple-text2sql-system-prompt.md 를 그대로 읽어
FakeAgent 에 넘긴다(= 실제로 Claude 에 먹이는 persona·스키마·규칙 한 장).

실행:  python3 simulate.py
산출:  out/q1_chart.html, out/q2_chart.html  (브라우저로 열면 차트)
"""

from __future__ import annotations

import json
import random
import re
import textwrap
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Generator

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
PROMPT_PATH = HERE.parent / "prompts" / "deli-simple-text2sql-system-prompt.md"

# 오늘 기준. "지난달" 윈도우 계산에 쓴다(슬라이드 질문 2).
TODAY = datetime.now()


# ─────────────────────────────────────────────────────────────────────────────
# §0. 시스템 프롬프트 로드 — 실제 Claude 에 먹이는 그 한 장
# ─────────────────────────────────────────────────────────────────────────────
def load_system_prompt() -> str:
    if not PROMPT_PATH.exists():
        return "(system prompt 파일 없음 — prompts/deli-simple-text2sql-system-prompt.md)"
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # 본문은 ````markdown ... ```` 펜스 안에 들어있다. 있으면 그 안만 꺼낸다.
    m = re.search(r"````markdown\n(.*?)\n````", text, re.DOTALL)
    return m.group(1) if m else text


# ─────────────────────────────────────────────────────────────────────────────
# §1. 가짜 데이터셋 — Deli 5테이블 축소판 (seed 고정 → 매번 같은 결과)
#     실제 봇에선 MySQL 에 적재된 시뮬레이션 데이터. 여기선 메모리에 만든다.
# ─────────────────────────────────────────────────────────────────────────────
CATEGORIES = ["한식", "치킨", "중식", "분식", "카페·디저트", "피자", "일식", "양식", "족발·보쌈"]
MENU_POOL = {
    "한식": ["김치찌개", "제육볶음", "된장찌개", "비빔밥"],
    "치킨": ["후라이드치킨", "양념치킨", "간장치킨"],
    "중식": ["짜장면", "짬뽕", "탕수육"],
    "분식": ["떡볶이", "순대", "김밥"],
    "카페·디저트": ["아메리카노", "카페라떼", "치즈케이크"],
    "피자": ["페퍼로니피자", "고구마피자"],
    "일식": ["연어덮밥", "돈카츠"],
    "양식": ["파스타", "스테이크"],
    "족발·보쌈": ["족발", "보쌈"],
}
YEONGDEUNGPO = ["영등포구 영등포동1가", "영등포구 당산동", "영등포구 문래동", "영등포구 여의도동"]
OTHER_REGIONS = ["마포구 합정동", "강남구 역삼동", "관악구 봉천동", "송파구 잠실동"]
ORDER_STATUSES = ["완료", "완료", "완료", "배달중", "조리", "취소"]  # 완료 비중 높게


@dataclass
class DeliData:
    restaurants: list[dict] = field(default_factory=list)
    menus: list[dict] = field(default_factory=list)
    users: list[dict] = field(default_factory=list)
    orders: list[dict] = field(default_factory=list)
    order_items: list[dict] = field(default_factory=list)


def build_dataset() -> DeliData:
    rng = random.Random(42)
    d = DeliData()

    # restaurants — 카테고리 분포 + 영업/휴업/폐업. 질문 1 은 이 테이블만 본다.
    for rid in range(1, 17):
        category = rng.choices(CATEGORIES, weights=[5, 5, 3, 3, 4, 2, 2, 2, 2])[0]
        status = rng.choices(["영업", "휴업", "폐업"], weights=[8, 1, 1])[0]
        region = rng.choice(YEONGDEUNGPO + OTHER_REGIONS)
        d.restaurants.append(
            {"id": rid, "name": f"{category}맛집{rid}", "category": category,
             "region": region, "status": status}
        )

    # menus — 식당마다 2~3개
    mid = 1
    for r in d.restaurants:
        for name in rng.sample(MENU_POOL[r["category"]], k=min(3, len(MENU_POOL[r["category"]]))):
            d.menus.append({"id": mid, "restaurant_id": r["id"], "name": name,
                            "price": rng.randrange(8000, 30000, 500), "is_available": 1})
            mid += 1

    # users — 영등포 20대 풀을 일부러 확보(질문 2 가 의미 있는 TOP5 가 나오게)
    uid = 1
    for _ in range(12):  # 영등포 + 20대
        birth = rng.randint(TODAY.year - 29, TODAY.year - 20)
        d.users.append({"id": uid, "region": rng.choice(YEONGDEUNGPO),
                        "birth_year": birth, "gender": rng.choice(["M", "F"])})
        uid += 1
    for _ in range(20):  # 그 외(타지역 or 다른 연령)
        birth = rng.randint(1970, TODAY.year - 10)
        d.users.append({"id": uid, "region": rng.choice(YEONGDEUNGPO + OTHER_REGIONS),
                        "birth_year": birth, "gender": rng.choice(["M", "F", None])})
        uid += 1

    yeongdeungpo_20s = [u for u in d.users if is_yeongdeungpo_20s(u)]
    last_lo, last_hi = last_month_window()

    # orders/order_items — 지난달 윈도우 안에 흩뿌린다.
    oid = 1

    def make_order(user: dict) -> None:
        nonlocal oid
        r = rng.choice(d.restaurants)
        span = (last_hi - last_lo).days
        ordered_at = last_lo + timedelta(days=rng.randrange(span),
                                         hours=rng.randrange(24), minutes=rng.randrange(60))
        status = rng.choice(ORDER_STATUSES)
        d.orders.append({"id": oid, "user_id": user["id"], "restaurant_id": r["id"],
                         "ordered_at": ordered_at, "status": status,
                         "total_amount": 0})
        r_menus = [m for m in d.menus if m["restaurant_id"] == r["id"]]
        for m in rng.sample(r_menus, k=min(rng.randint(1, 2), len(r_menus))):
            d.order_items.append({"order_id": oid, "menu_id": m["id"],
                                  "quantity": rng.randint(1, 3), "price": m["price"],
                                  "ordered_at": ordered_at})
        oid += 1

    for _ in range(80):  # 영등포 20대 주문(질문 2 표본)
        make_order(rng.choice(yeongdeungpo_20s))
    for _ in range(60):  # 그 외 주문(노이즈)
        make_order(rng.choice(d.users))

    return d


def is_yeongdeungpo_20s(u: dict) -> bool:
    age = TODAY.year - u["birth_year"]
    return u["region"].startswith("영등포") and 20 <= age <= 29


def last_month_window() -> tuple[datetime, datetime]:
    """[지난달 1일, 이번달 1일) 반열린 구간. 슬라이드 질문 2 의 기간 조건."""
    this_first = TODAY.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_first = (this_first - timedelta(days=1)).replace(day=1)
    return last_first, this_first


# ─────────────────────────────────────────────────────────────────────────────
# §2. FakeDeliDB — deli-db MCP 대역. run_select / list_tables / get_schema.
#     실제 서버(deli-db-mcp/server.py)와 같은 '텍스트 표' 포맷으로 돌려준다.
#     일반 SQL 파서를 만들 순 없으니, 두 데모 쿼리만 알아보고
#     임베드한 데이터셋을 파이썬으로 집계한다(= 실제 행 위에서 도는 진짜 집계).
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class ToolResult:
    text: str                 # Claude(=FakeAgent)가 실제로 보는 것 = 텍스트 표뿐
    columns: list[str] = field(default_factory=list)
    rows: list[tuple] = field(default_factory=list)  # 시뮬 편의용(분석 문장 생성에만 사용)


class FakeDeliDB:
    def __init__(self, data: DeliData):
        self.data = data

    def run_select(self, sql: str, max_rows: int = 200) -> ToolResult:
        low = sql.lower()
        if "from restaurants" in low and "group by" in low and "category" in low:
            return self._q1_category_counts()
        if "order_items" in low and "limit 5" in low:
            return self._q2_top5_menus()
        return ToolResult(text="(시뮬레이터는 데모 질문 1·2 의 SQL 만 실행합니다)")

    def _q1_category_counts(self) -> ToolResult:
        counts: dict[str, int] = {}
        for r in self.data.restaurants:
            if r["status"] == "영업":
                counts[r["category"]] = counts.get(r["category"], 0) + 1
        rows = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
        cols = ["category", "restaurant_count"]
        return ToolResult(text=render_table(cols, rows), columns=cols, rows=rows)

    def _q2_top5_menus(self) -> ToolResult:
        lo, hi = last_month_window()
        users = {u["id"]: u for u in self.data.users}
        menus = {m["id"]: m for m in self.data.menus}
        rests = {r["id"]: r for r in self.data.restaurants}
        orders = {o["id"]: o for o in self.data.orders}

        agg: dict[tuple, int] = {}
        for it in self.data.order_items:
            o = orders[it["order_id"]]
            if not (lo <= o["ordered_at"] < hi):
                continue
            if o["status"] == "취소":
                continue
            u = users[o["user_id"]]
            if not is_yeongdeungpo_20s(u):
                continue
            m = menus[it["menu_id"]]
            r = rests[m["restaurant_id"]]
            key = (m["name"], r["name"])
            agg[key] = agg.get(key, 0) + it["quantity"]

        ranked = sorted(agg.items(), key=lambda kv: kv[1], reverse=True)[:5]
        rows = [(menu, rest, qty) for (menu, rest), qty in ranked]
        cols = ["menu_name", "restaurant_name", "total_qty"]
        return ToolResult(text=render_table(cols, rows), columns=cols, rows=rows)

    def list_tables(self) -> ToolResult:
        rows = [
            ("users", len(self.data.users), "회원"),
            ("restaurants", len(self.data.restaurants), "식당"),
            ("menus", len(self.data.menus), "메뉴"),
            ("orders", len(self.data.orders), "주문"),
            ("order_items", len(self.data.order_items), "주문 상세"),
        ]
        cols = ["table", "approx_rows", "comment"]
        return ToolResult(text=render_table(cols, rows), columns=cols, rows=rows)


def render_table(columns: list[str], rows: list[tuple]) -> str:
    """deli-db-mcp/server.py 의 _render 와 같은 모양으로 텍스트 표를 만든다."""
    if not columns:
        return "(no result)"
    if not rows:
        return "columns: " + ", ".join(columns) + "\n(0 rows)"
    cols = list(columns)
    widths = [len(c) for c in cols]
    srows = []
    for r in rows:
        sr = [("NULL" if v is None else str(v)) for v in r]
        srows.append(sr)
        for i, s in enumerate(sr):
            widths[i] = max(widths[i], len(s))
    head = " | ".join(c.ljust(widths[i]) for i, c in enumerate(cols))
    sep = "-+-".join("-" * widths[i] for i in range(len(cols)))
    lines = [head, sep]
    lines += [" | ".join(s.ljust(widths[i]) for i, s in enumerate(sr)) for sr in srows]
    note = f"\n\n({len(rows)} row(s))"
    return "\n".join(lines) + note


# ─────────────────────────────────────────────────────────────────────────────
# §3. create_chart — In-process MCP 도구 대역.
#     실제 봇은 matplotlib → 임시 PNG. 여기선 의존성 0 인 Chart.js HTML 로.
#     실제 서버처럼 "__CHART_FILE__:<path>" 를 돌려준다.
# ─────────────────────────────────────────────────────────────────────────────
def create_chart(chart_type: str, title: str, labels: list[str],
                 values: list[int], x_label: str, y_label: str, out_name: str) -> str:
    OUT.mkdir(exist_ok=True)
    path = OUT / out_name
    html = textwrap.dedent(f"""\
        <!doctype html><html lang="ko"><head><meta charset="utf-8">
        <title>{title}</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script></head>
        <body style="max-width:760px;margin:40px auto;font-family:sans-serif">
        <h3>{title}</h3><canvas id="c"></canvas>
        <script>
        new Chart(document.getElementById('c'), {{
          type: {json.dumps(chart_type)},
          data: {{ labels: {json.dumps(labels, ensure_ascii=False)},
                   datasets: [{{ label: {json.dumps(y_label, ensure_ascii=False)},
                                 data: {json.dumps(values)} }}] }},
          options: {{ scales: {{ x: {{ title: {{ display:true, text:{json.dumps(x_label, ensure_ascii=False)} }} }},
                                 y: {{ title: {{ display:true, text:{json.dumps(y_label, ensure_ascii=False)} }},
                                       beginAtZero:true }} }} }}
        }});
        </script></body></html>
    """)
    path.write_text(html, encoding="utf-8")
    return f"__CHART_FILE__:{path}"


# ─────────────────────────────────────────────────────────────────────────────
# §4. FakeSlack — slack_bolt 대역. 실제론 say()/files_upload_v2()/replies API.
# ─────────────────────────────────────────────────────────────────────────────
class FakeSlack:
    def conversations_replies(self, channel: str, ts: str, limit: int = 50) -> list[dict]:
        # 봇이 처음 멘션돼도 사람들끼리의 직전 대화 맥락을 채워주는 자리.
        return [{"user": "U_PERSON", "text": "(이 스레드의 이전 대화…)"}]

    def say(self, text: str, thread_ts: str) -> None:
        print(f"\n[slack#{thread_ts} ← bot]\n{textwrap.indent(text, '  ')}")

    def files_upload_v2(self, channel: str, thread_ts: str, file: str, title: str) -> None:
        print(f"\n[slack#{thread_ts} ← bot] 파일 업로드: {file}  (title={title!r})")


# ─────────────────────────────────────────────────────────────────────────────
# §5. FakeAgent — Claude Agent SDK(ClaudeSDKClient) 대역.
#     실제론 Claude 가 system prompt 보고 스스로 SQL 을 쓰고 도구를 부른다.
#     여기선 데모 질문 1·2 에 대한 turn 시퀀스를 '재생'한다.
#     run() 은 제너레이터 — SDK 의 multi-turn 루프(Claude→도구→결과→Claude)를 흉내낸다:
#         이벤트를 yield 하고, 도구 결과를 .send() 로 돌려받아 다음 turn 을 잇는다.
# ─────────────────────────────────────────────────────────────────────────────
# 이벤트 타입: ("say", 내레이션) / ("tool", 이름, 인자dict) / ("final", 최종답변)
Event = tuple

Q1_SQL = textwrap.dedent("""\
    SELECT category, COUNT(*) AS restaurant_count
    FROM RESTAURANTS
    WHERE status = '영업'
    GROUP BY category
    ORDER BY restaurant_count DESC;""")

Q2_SQL = textwrap.dedent("""\
    SELECT m.name AS menu_name, r.name AS restaurant_name, SUM(oi.quantity) AS total_qty
    FROM ORDER_ITEMS oi
    JOIN ORDERS      o ON oi.order_id     = o.id
    JOIN USERS       u ON o.user_id       = u.id
    JOIN MENUS       m ON oi.menu_id      = m.id
    JOIN RESTAURANTS r ON m.restaurant_id = r.id
    WHERE o.ordered_at >= DATE_FORMAT(CURRENT_DATE - INTERVAL 1 MONTH, '%Y-%m-01')
      AND o.ordered_at <  DATE_FORMAT(CURRENT_DATE, '%Y-%m-01')
      AND u.region LIKE '영등포%'
      AND YEAR(CURRENT_DATE) - u.birth_year BETWEEN 20 AND 29
      AND o.status <> '취소'
    GROUP BY m.name, r.name
    ORDER BY total_qty DESC
    LIMIT 5;""")


class FakeAgent:
    def __init__(self, system_prompt: str):
        self.system_prompt = system_prompt  # 실제 Claude 에 먹이는 그 한 장(여기선 미사용)

    def run(self, question: str) -> Generator[Event, ToolResult, None]:
        if "카테고리" in question:
            yield from self._q1()
        elif "TOP 5" in question or "인기" in question:
            yield from self._q2()
        else:
            yield ("final", "이 시뮬레이터는 강의 데모 질문 1·2 만 다룹니다.")

    # 질문 1 — restaurants 단일 집계 → 막대그래프
    def _q1(self) -> Generator[Event, ToolResult, None]:
        yield ("say", "질문 정리: 카테고리별 '운영 중(영업)' 식당 수. 가정: 운영 중 = status='영업'.")
        res: ToolResult = yield ("tool", "run_select", {"sql": Q1_SQL})

        total = sum(c for _, c in res.rows)
        top_cat, top_n = res.rows[0]
        yield ("tool", "create_chart", {
            "chart_type": "bar", "title": "카테고리별 운영 중 식당 수",
            "labels": [r[0] for r in res.rows], "values": [r[1] for r in res.rows],
            "x_label": "카테고리", "y_label": "식당 수", "out_name": "q1_chart.html"})

        analysis = (
            f"• 운영 중 식당 총 {total}곳, {len(res.rows)}개 카테고리에 분포\n"
            f"• 1위 *{top_cat}* {top_n}곳 (전체의 {top_n / total * 100:.0f}%)\n"
            f"• 상위 카테고리 쏠림 — 하위 카테고리는 입점이 얕다")
        yield ("final", self._format("카테고리별 운영 중 식당 수",
                                     "운영 중 = restaurants.status='영업'",
                                     Q1_SQL, res.text, analysis, "q1_chart.html"))

    # 질문 2 — 5테이블 JOIN + 기간/지역/연령 필터 → TOP5 막대그래프
    def _q2(self) -> Generator[Event, ToolResult, None]:
        lo, hi = last_month_window()
        yield ("say", "질문 정리: 지난달 영등포 거주 20대의 주문 메뉴 TOP 5. 스키마 확실 → 바로 SQL.")
        res: ToolResult = yield ("tool", "run_select", {"sql": Q2_SQL})

        if not res.rows:
            yield ("final", "지난달 영등포 20대 주문 표본이 비어 있습니다.")
            return
        top_menu, top_rest, top_qty = res.rows[0]
        yield ("tool", "create_chart", {
            "chart_type": "bar", "title": "지난달 영등포 20대 인기 메뉴 TOP 5",
            "labels": [r[0] for r in res.rows], "values": [r[2] for r in res.rows],
            "x_label": "메뉴", "y_label": "주문 수량(합)", "out_name": "q2_chart.html"})

        analysis = (
            f"• 1위 *{top_menu}* ({top_rest}) — 누적 {top_qty}개\n"
            f"• TOP5 합계 {sum(r[2] for r in res.rows)}개, 표본 = 지난달 영등포 20대 주문\n"
            f"• '취소' 주문 제외 · 기간은 [{lo:%Y-%m-%d}, {hi:%Y-%m-%d}) 반열린 구간")
        gasum = "지난달=" + f"[{lo:%Y-%m-01}, {hi:%Y-%m-01}) · 영등포=region LIKE '영등포%' · 20대=만나이 20~29 · 취소 제외"
        yield ("final", self._format("지난달 영등포 20대 인기 메뉴 TOP 5",
                                     gasum, Q2_SQL, res.text, analysis, "q2_chart.html"))

    @staticmethod
    def _format(q: str, assume: str, sql: str, result_text: str,
                analysis: str, chart_name: str) -> str:
        # 시스템 프롬프트의 출력 형식: 질문/가정/SQL/결과/분석/그래프
        return (
            f"*질문*\n{q}\n\n"
            f"*가정*\n{assume}\n\n"
            f"*실행 SQL*\n```\n{sql}\n```\n\n"
            f"*결과*\n```\n{result_text}\n```\n\n"
            f"*분석*\n{analysis}\n\n"
            f"*그래프*\n첨부: {chart_name}")


# ─────────────────────────────────────────────────────────────────────────────
# §6. da-bot 본체 — 7단계 오케스트레이션. 실제 봇과 동일한 뼈대.
#     이 함수만 보면 흐름이 한눈에 들어온다(가짜/진짜 무관하게 똑같다).
# ─────────────────────────────────────────────────────────────────────────────
SESSIONS: dict[str, str] = {}  # 실제론 sessions/{thread_key}.txt (+ S3 동기화)


def handle(event: dict, agent: FakeAgent, db: FakeDeliDB, slack: FakeSlack) -> None:
    channel, thread_ts = event["channel"], event["thread_ts"]
    question = event["text"]
    print("=" * 78)
    print(f"[1] Slack 이벤트 수신: {event['type']}  #{channel}  «{question}»")

    # [2] 스레드 컨텍스트
    ctx = slack.conversations_replies(channel, thread_ts)
    print(f"[2] 스레드 컨텍스트 {len(ctx)}건 prepend")

    # [3] 세션 결정
    thread_key = f"{channel}:{thread_ts}"
    prior = SESSIONS.get(thread_key)
    print(f"[3] 세션: {'resume ' + prior if prior else '신규'} (thread_key={thread_key})")

    # [4]+[5] SDK multi-turn 루프 — Claude ↔ 도구
    print("[4] query → Claude Agent SDK")
    print("[5] multi-turn 루프 시작")
    chart_file: str | None = None
    gen = agent.run(question)
    event_out = next(gen)
    while True:
        kind = event_out[0]
        if kind == "say":
            print(f"      Claude: {event_out[1]}")
            event_out = next(gen)
        elif kind == "tool":
            name, args = event_out[1], event_out[2]
            print(f"      Claude → 도구 {name}({_brief(args)})")
            result = _exec_tool(name, args, db)
            if name == "create_chart":
                chart_file = result  # "__CHART_FILE__:<path>"
                preview = result
            else:
                preview = result.text.splitlines()[0] + " …"
            print(f"      도구 결과 ← {preview}")
            event_out = gen.send(result if name == "run_select" else None)
        elif kind == "final":
            final_text = event_out[1]
            break

    # [6] 응답 + 차트 업로드 → Slack
    print("[6] 응답 스트리밍 + 차트 업로드")
    slack.say(final_text, thread_ts)
    if chart_file and chart_file.startswith("__CHART_FILE__:"):
        slack.files_upload_v2(channel, thread_ts,
                              file=chart_file.split(":", 1)[1], title="차트")

    # [7] 세션 저장
    SESSIONS[thread_key] = f"sess_{abs(hash(thread_key)) % 10000}"
    print(f"[7] session_id 저장: {SESSIONS[thread_key]}")


def _exec_tool(name: str, args: dict, db: FakeDeliDB) -> Any:
    if name == "run_select":
        return db.run_select(args["sql"])
    if name == "create_chart":
        return create_chart(**args)
    raise ValueError(f"unknown tool: {name}")


def _brief(args: dict) -> str:
    if "sql" in args:
        return "sql=" + " ".join(args["sql"].split())[:50] + "…"
    return ", ".join(f"{k}={v}" for k, v in args.items() if k in ("chart_type", "title"))


# ─────────────────────────────────────────────────────────────────────────────
# §7. main — 데모 질문 2개를 전체 흐름에 통과시킨다.
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
    system_prompt = load_system_prompt()
    print(f"system prompt 로드: {len(system_prompt)} 자 "
          f"(첫 줄: {system_prompt.splitlines()[0]!r})")
    print(f"기준일(오늘): {TODAY:%Y-%m-%d} · 지난달 윈도우: "
          f"[{last_month_window()[0]:%Y-%m-%d}, {last_month_window()[1]:%Y-%m-%d})\n")

    data = build_dataset()
    db = FakeDeliDB(data)
    slack = FakeSlack()
    agent = FakeAgent(system_prompt)

    demo_events = [
        {"type": "app_mention", "channel": "C_DEMO", "thread_ts": "1700000001.0001",
         "text": "카테고리별로 운영 중인 식당이 몇 개씩 있는지 알려주세요"},
        {"type": "app_mention", "channel": "C_DEMO", "thread_ts": "1700000002.0002",
         "text": "지난달 영등포에 사는 20대가 가장 많이 주문한 메뉴 TOP 5는?"},
    ]
    for ev in demo_events:
        handle(ev, agent, db, slack)
        print()

    print("=" * 78)
    print(f"차트 산출물: {OUT}/q1_chart.html , {OUT}/q2_chart.html (브라우저로 열기)")


if __name__ == "__main__":
    main()
