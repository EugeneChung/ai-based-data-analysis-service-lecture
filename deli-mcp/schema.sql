-- Deli Text-to-SQL demo schema (MySQL 8 / InnoDB)
-- Mirrors deli-simple-text2sql-system-prompt.md.
-- Column COMMENTs are intentional: they are what lets an LLM map
-- natural language to the right column and value domain.

SET NAMES utf8mb4;

-- ---------------------------------------------------------------
-- Dimensions (slow-changing)
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `users` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'User PK | 사용자 PK',
  `gender`      CHAR(1)      NULL                    COMMENT "Gender enum 'M'/'F', NULL if unknown | 성별",
  `birth_year`  SMALLINT     NULL                    COMMENT 'Birth year (YYYY), year-based age only | 출생연도',
  `region`      VARCHAR(50)  NOT NULL                COMMENT 'Administrative dong address "{시군구} {행정동}" (e.g. 영등포구 영등포동1가) | 거주 행정동',
  `signup_date` DATE         NOT NULL                COMMENT 'Signup date | 가입일',
  PRIMARY KEY (`id`),
  KEY `IDX_region` (`region`),
  KEY `IDX_signup_date` (`signup_date`),
  KEY `IDX_birth_gender` (`birth_year`, `gender`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='가입 사용자 마스터 — Deli 앱 가입 사용자';

CREATE TABLE IF NOT EXISTS `restaurants` (
  `id`          BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'Restaurant PK | 식당 PK',
  `name`        VARCHAR(100) NOT NULL                COMMENT 'Restaurant name, includes branch suffix | 상호명, 지점명 포함',
  `category`    VARCHAR(20)  NOT NULL                COMMENT 'Food category enum (한식/중식/일식/양식/분식/카페·디저트/치킨/피자/족발·보쌈/야식/도시락) | 음식 카테고리',
  `region`      VARCHAR(50)  NOT NULL                COMMENT 'Administrative dong address "{시군구} {행정동}" | 식당 행정동',
  `opened_date` DATE         NOT NULL                COMMENT 'Franchise registration date, not actual store opening | 가맹 등록일',
  `status`      VARCHAR(4)   NOT NULL                COMMENT 'Operating status enum (영업/휴업/폐업), 영업 = currently operating | 운영 상태',
  PRIMARY KEY (`id`),
  KEY `IDX_status_category` (`status`, `category`),
  KEY `IDX_category_status` (`category`, `status`),
  KEY `IDX_region` (`region`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='가맹 식당 마스터 — Deli에 등록된 식당의 기본 정보';

CREATE TABLE IF NOT EXISTS `menus` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'Menu PK | 메뉴 PK',
  `restaurant_id` BIGINT       NOT NULL                COMMENT 'FK -> restaurants.id | 소속 식당',
  `name`          VARCHAR(100) NOT NULL                COMMENT 'Menu item name | 메뉴명',
  `price`         INT UNSIGNED NOT NULL                COMMENT 'Current price in KRW | 현재 가격(원)',
  `is_available`  TINYINT(1)   NOT NULL DEFAULT 1      COMMENT '1 = orderable now, 0 = hidden/soldout | 주문 가능 여부',
  PRIMARY KEY (`id`),
  KEY `IDX_rest_avail` (`restaurant_id`, `is_available`),
  KEY `IDX_rest_name` (`restaurant_id`, `name`),
  KEY `IDX_price` (`price`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='메뉴 마스터 — 식당별 판매 메뉴와 현재가';

-- ---------------------------------------------------------------
-- Facts (yearly RANGE partitioned by time)
-- ---------------------------------------------------------------

CREATE TABLE IF NOT EXISTS `orders` (
  `id`            BIGINT       NOT NULL AUTO_INCREMENT COMMENT 'Order PK | 주문 PK',
  `user_id`       BIGINT       NOT NULL                COMMENT 'FK -> users.id | 주문 사용자',
  `restaurant_id` BIGINT       NOT NULL                COMMENT 'FK -> restaurants.id | 주문 식당',
  `ordered_at`    DATETIME     NOT NULL                COMMENT 'Order time (KST), partition key | 주문 시각',
  `delivered_at`  DATETIME     NULL                    COMMENT 'Delivery completed time, NULL if cancelled/in-progress | 배달 완료 시각',
  `total_amount`  INT UNSIGNED NOT NULL                COMMENT 'Order total in KRW, incl delivery fee, post-discount | 결제 총액(원)',
  `status`        VARCHAR(10)  NOT NULL                COMMENT 'Order status enum (결제/조리/배달중/완료/취소) | 주문 상태',
  PRIMARY KEY (`id`, `ordered_at`),
  KEY `IDX_user_time` (`user_id`, `ordered_at`),
  KEY `IDX_rest_time` (`restaurant_id`, `ordered_at`),
  KEY `IDX_status_time` (`status`, `ordered_at`),
  KEY `IDX_time` (`ordered_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='주문 팩트 — 1주문 1행, ordered_at 연단위 파티션'
PARTITION BY RANGE COLUMNS(`ordered_at`) (
  PARTITION p2024 VALUES LESS THAN ('2025-01-01'),
  PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
  PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
  PARTITION pmax  VALUES LESS THAN (MAXVALUE)
);

CREATE TABLE IF NOT EXISTS `order_items` (
  `order_id`   BIGINT            NOT NULL COMMENT 'FK -> orders.id | 주문',
  `menu_id`    BIGINT            NOT NULL COMMENT 'FK -> menus.id | 메뉴',
  `quantity`   SMALLINT UNSIGNED NOT NULL COMMENT 'Ordered quantity | 수량',
  `price`      INT UNSIGNED      NOT NULL COMMENT 'Snapshot of menus.price at order time | 주문 시점 단가(원)',
  `ordered_at` DATETIME          NOT NULL COMMENT 'Denormalized from orders.ordered_at, partition key | 주문 시각(비정규화)',
  PRIMARY KEY (`order_id`, `menu_id`, `ordered_at`),
  KEY `IDX_menu_time` (`menu_id`, `ordered_at`),
  KEY `IDX_time` (`ordered_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='주문 상세 팩트 — 1주문 N메뉴, ordered_at 연단위 파티션'
PARTITION BY RANGE COLUMNS(`ordered_at`) (
  PARTITION p2024 VALUES LESS THAN ('2025-01-01'),
  PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
  PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
  PARTITION pmax  VALUES LESS THAN (MAXVALUE)
);

CREATE TABLE IF NOT EXISTS `reviews` (
  `id`            BIGINT           NOT NULL AUTO_INCREMENT COMMENT 'Review PK | 리뷰 PK',
  `user_id`       BIGINT           NOT NULL                COMMENT 'FK -> users.id | 작성 사용자',
  `restaurant_id` BIGINT           NOT NULL                COMMENT 'FK -> restaurants.id | 대상 식당',
  `order_id`      BIGINT           NOT NULL                COMMENT 'FK -> orders.id, 1:1 with order | 대상 주문',
  `rating`        TINYINT UNSIGNED NOT NULL                COMMENT 'Rating 1-5 integer | 평점(1~5)',
  `content`       TEXT             NULL                    COMMENT 'Review text, may be NULL | 리뷰 본문',
  `created_at`    DATETIME         NOT NULL                COMMENT 'Review time (KST), separate timeline from orders.ordered_at, partition key | 리뷰 작성 시각',
  PRIMARY KEY (`id`, `created_at`),
  UNIQUE KEY `UK_order` (`order_id`, `created_at`),
  KEY `IDX_rest_time` (`restaurant_id`, `created_at`),
  KEY `IDX_user_time` (`user_id`, `created_at`),
  KEY `IDX_rating_time` (`rating`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='리뷰 팩트 — 주문당 최대 1건, created_at 연단위 파티션'
PARTITION BY RANGE COLUMNS(`created_at`) (
  PARTITION p2024 VALUES LESS THAN ('2025-01-01'),
  PARTITION p2025 VALUES LESS THAN ('2026-01-01'),
  PARTITION p2026 VALUES LESS THAN ('2027-01-01'),
  PARTITION pmax  VALUES LESS THAN (MAXVALUE)
);
