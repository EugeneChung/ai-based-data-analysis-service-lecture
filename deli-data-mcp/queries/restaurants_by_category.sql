-- restaurants_by_category: 카테고리별 영업 중 식당 수
-- region 은 선택 파라미터. 값이 주어졌을 때만 지역 WHERE 조건이 붙는다.
SELECT
    r.category   AS category,
    COUNT(*)     AS restaurants
FROM restaurants r
WHERE r.status = '영업'
{% if region %}  AND r.region LIKE CONCAT('{{ region }}', '%')
{% endif %}
GROUP BY r.category
ORDER BY restaurants DESC
LIMIT {{ limit }}
