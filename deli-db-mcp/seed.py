"""Generate simulated Deli data and load it into local MySQL.

Re-runnable: truncates the six tables first, then regenerates a
self-consistent dataset (FKs line up, totals match item lines, dates
land inside the yearly partitions). Tuned so the two lecture questions
return non-empty results:

  Q1: 카테고리별로 운영 중인 식당이 몇 개씩 있는지
  Q2: 지난달 영등포에 사는 20대가 가장 많이 주문한 메뉴 TOP 5

Counts are overridable via env: DELI_USERS, DELI_RESTAURANTS,
DELI_ORDERS. Seeded RNG → deterministic output.
"""

import os
import random
from datetime import date, datetime, timedelta

from db import connect

RNG_SEED = int(os.environ.get("DELI_SEED", "20260527"))
N_USERS = int(os.environ.get("DELI_USERS", "10000"))
N_RESTAURANTS = int(os.environ.get("DELI_RESTAURANTS", "2000"))
N_ORDERS = int(os.environ.get("DELI_ORDERS", "50000"))

random.seed(RNG_SEED)

TODAY = date(2026, 5, 28)

CATEGORIES = [
    "한식", "중식", "일식", "양식", "분식",
    "카페·디저트", "치킨", "피자", "족발·보쌈", "야식", "도시락",
]

# region pool as "{시군구} {행정동}". 영등포구 oversampled so Q2 has data.
GU_DONG = {
    "영등포구": ["영등포동", "영등포동1가", "당산동", "여의도동", "문래동", "신길동", "대림동", "양평동"],
    "강남구": ["역삼동", "삼성동", "논현동", "청담동", "대치동", "신사동"],
    "마포구": ["서교동", "합정동", "망원동", "연남동", "공덕동"],
    "송파구": ["잠실동", "방이동", "가락동", "문정동"],
    "관악구": ["봉천동", "신림동", "남현동"],
    "성동구": ["성수동1가", "성수동2가", "왕십리도선동"],
    "용산구": ["이태원동", "한남동", "청파동"],
    "종로구": ["사직동", "삼청동", "혜화동"],
}
REGION_POOL = []
for gu, dongs in GU_DONG.items():
    weight = 4 if gu == "영등포구" else 1  # oversample 영등포
    for d in dongs:
        REGION_POOL.extend([f"{gu} {d}"] * weight)

NAME_PREFIX = ["행복", "맛나", "왕", "명가", "옛날", "정통", "시골", "바다", "황금",
               "원조", "형제", "자매", "24시", "도담", "오복", "한끼", "푸짐", "단골"]

MENU_POOL = {
    "한식": ["김치찌개", "된장찌개", "불고기", "비빔밥", "제육볶음", "갈비탕", "순두부찌개", "냉면"],
    "중식": ["짜장면", "짬뽕", "탕수육", "마라탕", "볶음밥", "깐풍기", "유산슬", "양장피"],
    "일식": ["초밥세트", "라멘", "우동", "돈카츠", "규동", "사케동", "텐동", "냉모밀"],
    "양식": ["크림파스타", "토마토파스타", "스테이크", "리조또", "샐러드", "함박스테이크", "감바스"],
    "분식": ["떡볶이", "순대", "김밥", "라면", "튀김모둠", "쫄면", "라볶이", "치즈김밥"],
    "카페·디저트": ["아메리카노", "카페라떼", "치즈케이크", "마카롱", "크로플", "팥빙수", "에이드", "티라미수"],
    "치킨": ["후라이드", "양념치킨", "간장치킨", "파닭", "반반치킨", "마늘치킨", "치킨무세트"],
    "피자": ["페퍼로니피자", "콤비네이션피자", "고구마피자", "불고기피자", "포테이토피자", "치즈피자"],
    "족발·보쌈": ["족발", "보쌈", "막국수", "쟁반국수", "족발보쌈세트", "마늘보쌈"],
    "야식": ["곱창", "닭발", "골뱅이무침", "마른안주", "오돌뼈", "닭똥집"],
    "도시락": ["제육도시락", "치킨마요덮밥", "불고기도시락", "돈까스도시락", "스팸마요덮밥", "참치마요덮밥"],
}

REVIEW_GOOD = ["맛있어요 또 시킬게요", "양 많고 좋아요", "배달 빨라요", "재주문합니다", "사장님 친절해요", "가성비 최고"]
REVIEW_MID = ["무난해요", "그냥 그래요", "보통입니다", "가격대비 아쉬워요"]
REVIEW_BAD = ["너무 짜요", "배달이 늦었어요", "양이 적어요", "다신 안 시킬듯"]

ORDER_STATUS = (["완료"] * 80) + (["취소"] * 8) + (["배달중"] * 5) + (["조리"] * 4) + (["결제"] * 3)


def rand_datetime_recent() -> datetime:
    """Weighted toward recent months; ensures 2026-04 (지난달) is well populated."""
    # 60% in the last 90 days, 30% in last year, 10% older (2025).
    r = random.random()
    if r < 0.60:
        days_ago = random.randint(0, 90)
    elif r < 0.90:
        days_ago = random.randint(91, 365)
    else:
        days_ago = random.randint(366, 600)
    d = TODAY - timedelta(days=days_ago)
    return datetime(d.year, d.month, d.day,
                    random.randint(9, 23), random.randint(0, 59), random.randint(0, 59))


def chunked_insert(cur, sql, rows, size=5000):
    for i in range(0, len(rows), size):
        cur.executemany(sql, rows[i:i + size])


def main():
    conn = connect(autocommit=False)
    cur = conn.cursor()
    print(f"seed: users={N_USERS} restaurants={N_RESTAURANTS} orders={N_ORDERS} (seed={RNG_SEED})")

    cur.execute("SET FOREIGN_KEY_CHECKS=0")
    for t in ["order_items", "reviews", "orders", "menus", "restaurants", "users"]:
        cur.execute(f"TRUNCATE TABLE `{t}`")
    cur.execute("SET FOREIGN_KEY_CHECKS=1")

    # ----- users -----
    users = []  # (id, region, birth_year)
    rows = []
    for uid in range(1, N_USERS + 1):
        region = random.choice(REGION_POOL)
        gender = random.choices(["M", "F", None], weights=[47, 47, 6])[0]
        birth_year = random.choices(
            [random.randint(2000, 2007), random.randint(1990, 1999),
             random.randint(1980, 1989), random.randint(1960, 1979), None],
            weights=[22, 30, 25, 18, 5])[0]
        signup = TODAY - timedelta(days=random.randint(1, 1500))
        rows.append((uid, gender, birth_year, region, signup))
        users.append((uid, region, birth_year))
    chunked_insert(cur, "INSERT INTO users (id,gender,birth_year,region,signup_date) VALUES (%s,%s,%s,%s,%s)", rows)
    print(f"  users: {len(rows)}")

    # ----- restaurants -----
    restaurants = []  # (id, category)
    rows = []
    for rid in range(1, N_RESTAURANTS + 1):
        category = random.choice(CATEGORIES)
        name = f"{random.choice(NAME_PREFIX)} {random.choice(MENU_POOL[category])}집"
        region = random.choice(REGION_POOL)
        opened = TODAY - timedelta(days=random.randint(30, 2500))
        status = random.choices(["영업", "휴업", "폐업"], weights=[85, 8, 7])[0]
        rows.append((rid, name, category, region, opened, status))
        restaurants.append((rid, category))
    chunked_insert(cur, "INSERT INTO restaurants (id,name,category,region,opened_date,status) VALUES (%s,%s,%s,%s,%s,%s)", rows)
    print(f"  restaurants: {len(rows)}")

    # ----- menus -----
    rest_menus = {}  # restaurant_id -> [(menu_id, price)]
    rows = []
    mid = 0
    for rid, category in restaurants:
        pool = MENU_POOL[category]
        k = random.randint(3, min(8, len(pool)))
        for mname in random.sample(pool, k):
            mid += 1
            price = random.randint(30, 320) * 100  # 3,000 ~ 32,000
            avail = 1 if random.random() < 0.92 else 0
            rows.append((mid, rid, mname, price, avail))
            rest_menus.setdefault(rid, []).append((mid, price))
    chunked_insert(cur, "INSERT INTO menus (id,restaurant_id,name,price,is_available) VALUES (%s,%s,%s,%s,%s)", rows)
    print(f"  menus: {len(rows)}")

    # ----- orders + order_items + reviews -----
    order_rows, item_rows, review_rows = [], [], []
    review_id = 0
    rest_ids = [r[0] for r in restaurants]

    for oid in range(1, N_ORDERS + 1):
        uid = random.choice(users)[0]
        rid = random.choice(rest_ids)
        menus = rest_menus.get(rid)
        if not menus:
            continue
        ordered_at = rand_datetime_recent()
        status = random.choice(ORDER_STATUS)

        n_items = random.randint(1, min(4, len(menus)))
        picked = random.sample(menus, n_items)
        items_total = 0
        for menu_id, price in picked:
            qty = random.randint(1, 3)
            items_total += price * qty
            item_rows.append((oid, menu_id, qty, price, ordered_at))
        delivery_fee = random.choice([0, 2000, 3000, 3500])
        total_amount = items_total + delivery_fee

        delivered_at = None
        if status == "완료":
            delivered_at = ordered_at + timedelta(minutes=random.randint(20, 75))
        order_rows.append((oid, uid, rid, ordered_at, delivered_at, total_amount, status))

        # review for ~30% of completed orders, created after delivery
        if status == "완료" and delivered_at is not None and random.random() < 0.30:
            review_id += 1
            rating = random.choices([5, 4, 3, 2, 1], weights=[45, 28, 14, 8, 5])[0]
            if rating >= 4:
                content = random.choice(REVIEW_GOOD)
            elif rating == 3:
                content = random.choice(REVIEW_MID)
            else:
                content = random.choice(REVIEW_BAD)
            if random.random() < 0.35:
                content = None
            created_at = delivered_at + timedelta(hours=random.randint(1, 72))
            review_rows.append((review_id, uid, rid, oid, rating, content, created_at))

    chunked_insert(cur, "INSERT INTO orders (id,user_id,restaurant_id,ordered_at,delivered_at,total_amount,status) VALUES (%s,%s,%s,%s,%s,%s,%s)", order_rows)
    print(f"  orders: {len(order_rows)}")
    chunked_insert(cur, "INSERT INTO order_items (order_id,menu_id,quantity,price,ordered_at) VALUES (%s,%s,%s,%s,%s)", item_rows)
    print(f"  order_items: {len(item_rows)}")
    chunked_insert(cur, "INSERT INTO reviews (id,user_id,restaurant_id,order_id,rating,content,created_at) VALUES (%s,%s,%s,%s,%s,%s,%s)", review_rows)
    print(f"  reviews: {len(review_rows)}")

    conn.commit()
    cur.close()
    conn.close()
    print("done.")


if __name__ == "__main__":
    main()
