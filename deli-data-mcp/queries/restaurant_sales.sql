-- restaurant_sales: 식당별 일자별 주문 수·매출 (완료 주문 기준)
-- 파라미터 자리(restaurant_id, date_from, date_to, limit)는 catalog 값으로
-- 채워진다. 값은 템플릿에 닿기 전 validator 에서 타입 검사를 마쳤으므로
-- 그대로 끼워 넣어도 안전하다.
SELECT
    DATE(o.ordered_at)   AS date,
    r.name               AS restaurant,
    COUNT(*)             AS orders,
    SUM(o.total_amount)  AS revenue
FROM orders o
JOIN restaurants r ON r.id = o.restaurant_id
WHERE o.restaurant_id = {{ restaurant_id }}
  AND o.status = '완료'
  AND o.ordered_at >= DATE('{{ date_from }}')
  AND o.ordered_at <  DATE('{{ date_to }}') + INTERVAL 1 DAY
GROUP BY DATE(o.ordered_at), r.name
ORDER BY date ASC
LIMIT {{ limit }}
