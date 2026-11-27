-- OMM PostgreSQL 스키마 v4 (인사이트) · PostgreSQL 16
-- 만개의레시피 + KAMIS + 식약처 영양성분 + YouTube → 메뉴 추천 · 물가×요리 인사이트 · 분석 8개
-- 생성: gen_ddl.py · 정의: schema.py

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;   -- 제목 · 후기 본문 LIKE 검색 (맛 표현 · 사람 이름 · 키워드)

-- 공통코드 · 상태 · 종류 값을 한곳에서 관리 (소매/도매, 정량/모호, 난이도, 신뢰도 …). 다른 테이블은 code_id 로 참조하고 화면 표시 이름 · 순서는 여기서 읽음
CREATE TABLE omm_common_codes (
    code_id              VARCHAR(30) NOT NULL,
    group_code           VARCHAR(30) NOT NULL,
    group_nm             VARCHAR(50) NOT NULL,
    code                 VARCHAR(20) NOT NULL,
    code_nm              VARCHAR(100) NOT NULL,
    group_sort           SMALLINT NOT NULL DEFAULT 0,
    sort                 SMALLINT NOT NULL DEFAULT 0,
    use_yn               CHAR(1) NOT NULL DEFAULT 'Y' CHECK (use_yn IN ('Y','N')),
    description          VARCHAR(200),
    CONSTRAINT pk_omm_common_codes PRIMARY KEY (code_id),
    CONSTRAINT uq_omm_common_codes_group_code_code UNIQUE (group_code, code)
);
COMMENT ON TABLE omm_common_codes IS '공통코드 - 상태 · 종류 값을 한곳에서 관리 (소매/도매, 정량/모호, 난이도, 신뢰도 …). 다른 테이블은 code_id 로 참조하고 화면 표시 이름 · 순서는 여기서 읽음';
COMMENT ON COLUMN omm_common_codes.code_id IS '코드번호 (그룹_값: MARKET_RETAIL, AMOUNT_VAGUE)';
COMMENT ON COLUMN omm_common_codes.group_code IS '그룹 코드 (MARKET_TYPE, AMOUNT_CLASS …)';
COMMENT ON COLUMN omm_common_codes.group_nm IS '그룹 이름 (시장 구분, 수량 표기 …)';
COMMENT ON COLUMN omm_common_codes.code IS '값 (원본 코드 · KAMIS 01 등)';
COMMENT ON COLUMN omm_common_codes.code_nm IS '코드 이름 (화면 표시: 소매, 모호 표현)';
COMMENT ON COLUMN omm_common_codes.group_sort IS '그룹 정렬 순서';
COMMENT ON COLUMN omm_common_codes.sort IS '그룹 안 정렬 순서';
COMMENT ON COLUMN omm_common_codes.use_yn IS '사용 여부';
COMMENT ON COLUMN omm_common_codes.description IS '설명';
CREATE INDEX ix_omm_common_codes_group ON omm_common_codes(group_code, sort);

-- 재료 분류 · 채소 · 육류 · 수산 · 유제품 · 양념 …
CREATE TABLE omm_ingredient_categories (
    category_id          SMALLSERIAL NOT NULL,
    name                 VARCHAR(30) NOT NULL UNIQUE,
    sort_order           SMALLINT NOT NULL DEFAULT 0,
    CONSTRAINT pk_omm_ingredient_categories PRIMARY KEY (category_id)
);
COMMENT ON TABLE omm_ingredient_categories IS '재료 분류 - 채소 · 육류 · 수산 · 유제품 · 양념 …';
COMMENT ON COLUMN omm_ingredient_categories.category_id IS '분류 번호';
COMMENT ON COLUMN omm_ingredient_categories.name IS '분류 이름';
COMMENT ON COLUMN omm_ingredient_categories.sort_order IS '화면 표시 순서';

-- 표준 재료 · 4개 출처를 잇는 중심 테이블. 만개 재료 · KAMIS 품목 · 영양성분 · YouTube 키워드가 모두 ingredient_id로 연결
CREATE TABLE omm_ingredients (
    ingredient_id        SERIAL NOT NULL,
    name                 VARCHAR(50) NOT NULL UNIQUE,
    category_id          SMALLINT NOT NULL,
    is_seasoning         BOOLEAN NOT NULL DEFAULT false,
    nutr_food_cd         VARCHAR(20),
    grams_per_unit       NUMERIC(7,1),
    default_unit         VARCHAR(10),
    recipe_count         INT NOT NULL DEFAULT 0,
    CONSTRAINT pk_omm_ingredients PRIMARY KEY (ingredient_id)
);
COMMENT ON TABLE omm_ingredients IS '표준 재료 - 4개 출처를 잇는 중심 테이블. 만개 재료 · KAMIS 품목 · 영양성분 · YouTube 키워드가 모두 ingredient_id로 연결';
COMMENT ON COLUMN omm_ingredients.ingredient_id IS '재료 번호';
COMMENT ON COLUMN omm_ingredients.name IS '표준 이름 (대파, 다진마늘, 건표고버섯)';
COMMENT ON COLUMN omm_ingredients.category_id IS '분류';
COMMENT ON COLUMN omm_ingredients.is_seasoning IS '양념 · 조미료 여부. 시세 배지 · 네트워크 분석에서 뺌';
COMMENT ON COLUMN omm_ingredients.nutr_food_cd IS '영양성분 식품코드 (분석 6). 대표 식품 하나를 연결';
COMMENT ON COLUMN omm_ingredients.grams_per_unit IS '1개 · 1모 · 1대 무게 g (감자 1개 = 150g). 수량 → g 환산';
COMMENT ON COLUMN omm_ingredients.default_unit IS '이 재료의 기본 셈 단위 (개, 모, 대, 포기)';
COMMENT ON COLUMN omm_ingredients.recipe_count IS '이 재료가 나오는 레시피 수';
CREATE INDEX ix_ingredients_category ON omm_ingredients(category_id);

-- 재료 별칭 · 여러 표기를 표준 재료로 (송송 썬 대파 · 파 → 대파, 달걀 → 계란). 크롤링 재료명 정규화
CREATE TABLE omm_ingredient_aliases (
    alias                VARCHAR(100) NOT NULL,
    ingredient_id        INT NOT NULL,
    source               VARCHAR(30) NOT NULL DEFAULT 'SRC_MANUAL',
    CONSTRAINT pk_omm_ingredient_aliases PRIMARY KEY (alias)
);
COMMENT ON TABLE omm_ingredient_aliases IS '재료 별칭 - 여러 표기를 표준 재료로 (송송 썬 대파 · 파 → 대파, 달걀 → 계란). 크롤링 재료명 정규화';
COMMENT ON COLUMN omm_ingredient_aliases.alias IS '별칭 (공백 제거한 값)';
COMMENT ON COLUMN omm_ingredient_aliases.ingredient_id IS '재료 번호';
COMMENT ON COLUMN omm_ingredient_aliases.source IS '어디서 나온 표기인지 · 공통코드(DATA_SOURCE)';

-- 단위 환산 · 정량 분류 · 수량 단위 → g, 그리고 정량 / 개수 / 모호 분류 (분석 8). ingredient_id가 NULL이면 모든 재료에 공통
CREATE TABLE omm_unit_conversions (
    unit_id              SERIAL NOT NULL,
    unit                 VARCHAR(20) NOT NULL,
    ingredient_id        INT,
    grams                NUMERIC(8,2),
    amount_class         VARCHAR(30) NOT NULL,
    CONSTRAINT pk_omm_unit_conversions PRIMARY KEY (unit_id),
    CONSTRAINT cs_omm_unit_conversions_1 UNIQUE NULLS NOT DISTINCT (unit, ingredient_id)
);
COMMENT ON TABLE omm_unit_conversions IS '단위 환산 · 정량 분류 - 수량 단위 → g, 그리고 정량 / 개수 / 모호 분류 (분석 8). ingredient_id가 NULL이면 모든 재료에 공통';
COMMENT ON COLUMN omm_unit_conversions.unit_id IS '번호';
COMMENT ON COLUMN omm_unit_conversions.unit IS '단위 표기 (g, ml, T, 큰술, 컵, 개, 모, 줌, 약간, 넉넉히)';
COMMENT ON COLUMN omm_unit_conversions.ingredient_id IS '재료별 환산일 때 (두부 1모 = 300g). NULL = 공통';
COMMENT ON COLUMN omm_unit_conversions.grams IS '1단위당 g (T = 15, 컵 = 200). 모호 표현은 대표값 또는 NULL';
COMMENT ON COLUMN omm_unit_conversions.amount_class IS '정량 / 개수 / 모호 분류 · 공통코드(AMOUNT_CLASS)';

-- 취향 태그 · 취향 입력 화면의 칩 (얼큰한 국물 · 고기 · 면 요리 / 제외: 오이 · 해산물). 태그 하나 = 규칙 하나
CREATE TABLE omm_filter_tags (
    tag_id               SERIAL NOT NULL,
    label                VARCHAR(30) NOT NULL,
    kind                 VARCHAR(30) NOT NULL,
    rule_type            VARCHAR(30) NOT NULL,
    rule_ref_id          INT NOT NULL,
    sort_order           SMALLINT NOT NULL DEFAULT 0,
    CONSTRAINT pk_omm_filter_tags PRIMARY KEY (tag_id),
    CONSTRAINT uq_omm_filter_tags_label_kind_rule_type_rule_ref_id UNIQUE (label, kind, rule_type, rule_ref_id)
);
COMMENT ON TABLE omm_filter_tags IS '취향 태그 - 취향 입력 화면의 칩 (얼큰한 국물 · 고기 · 면 요리 / 제외: 오이 · 해산물). 태그 하나 = 규칙 하나';
COMMENT ON COLUMN omm_filter_tags.tag_id IS '태그 번호';
COMMENT ON COLUMN omm_filter_tags.label IS '화면 표시 이름';
COMMENT ON COLUMN omm_filter_tags.kind IS '먹고 싶은 음식 / 제외할 음식 · 공통코드(TAG_KIND)';
COMMENT ON COLUMN omm_filter_tags.rule_type IS '무엇으로 거를지 · 공통코드(TAG_RULE)';
COMMENT ON COLUMN omm_filter_tags.rule_ref_id IS 'rule_type이 가리키는 번호 (taste_id, category_id, ingredient_id, menu_id, cluster_id)';
COMMENT ON COLUMN omm_filter_tags.sort_order IS '표시 순서';

-- 메뉴 · 같은 요리 레시피를 묶은 단위 (돼지고기 고추장찌개 = 레시피 312개). 추천 · 관심도 · 트렌드는 메뉴 기준
CREATE TABLE omm_menus (
    menu_id              SERIAL NOT NULL,
    name                 VARCHAR(50) NOT NULL UNIQUE,
    dish_type            VARCHAR(20) NOT NULL,
    rep_recipe_id        INT,
    recipe_count         INT NOT NULL DEFAULT 0,
    match_keywords       TEXT[],
    CONSTRAINT pk_omm_menus PRIMARY KEY (menu_id)
);
COMMENT ON TABLE omm_menus IS '메뉴 - 같은 요리 레시피를 묶은 단위 (돼지고기 고추장찌개 = 레시피 312개). 추천 · 관심도 · 트렌드는 메뉴 기준';
COMMENT ON COLUMN omm_menus.menu_id IS '메뉴 번호';
COMMENT ON COLUMN omm_menus.name IS '메뉴 이름';
COMMENT ON COLUMN omm_menus.dish_type IS '요리 종류 (국·찌개, 반찬, 밥, 면, 김치 …). 만개 종류별 분류에서';
COMMENT ON COLUMN omm_menus.rep_recipe_id IS '대표 레시피 = 최근 1년 후기가 가장 많은 레시피';
COMMENT ON COLUMN omm_menus.recipe_count IS '이 메뉴 레시피 수';
COMMENT ON COLUMN omm_menus.match_keywords IS '제목에서 메뉴를 찾는 키워드 (고추장찌개, 고추장 찌개)';

-- 레시피 · 만개의레시피 레시피 1건. 작성자 닉네임 · 조리 단계 · 사진 파일은 저장하지 않음 (이미지는 URL만)
CREATE TABLE omm_recipes (
    recipe_id            INT NOT NULL,
    menu_id              INT,
    title                VARCHAR(200) NOT NULL,
    intro                TEXT,
    image_url            VARCHAR(500),
    registered_at        DATE,
    servings             SMALLINT,
    cook_time_min        SMALLINT,
    difficulty           VARCHAR(30),
    view_count           INT,
    avg_rating           NUMERIC(3,2) CHECK (avg_rating BETWEEN 0 AND 5),
    review_count         INT NOT NULL DEFAULT 0,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_recipes PRIMARY KEY (recipe_id)
);
COMMENT ON TABLE omm_recipes IS '레시피 - 만개의레시피 레시피 1건. 작성자 닉네임 · 조리 단계 · 사진 파일은 저장하지 않음 (이미지는 URL만)';
COMMENT ON COLUMN omm_recipes.recipe_id IS '만개의레시피 레시피 번호';
COMMENT ON COLUMN omm_recipes.menu_id IS '메뉴 (제목으로 매칭. 못 찾으면 NULL)';
COMMENT ON COLUMN omm_recipes.title IS '제목';
COMMENT ON COLUMN omm_recipes.intro IS '소개 (소제목)';
COMMENT ON COLUMN omm_recipes.image_url IS '대표 이미지 URL';
COMMENT ON COLUMN omm_recipes.registered_at IS '등록일';
COMMENT ON COLUMN omm_recipes.servings IS '인분 (숫자만. "6인분 이상" = 6)';
COMMENT ON COLUMN omm_recipes.cook_time_min IS '조리시간 분 ("30분 이내" = 30, "2시간 이상" = 120)';
COMMENT ON COLUMN omm_recipes.difficulty IS '난이도 · 공통코드(DIFFICULTY)';
COMMENT ON COLUMN omm_recipes.view_count IS '조회수 (수집 시점)';
COMMENT ON COLUMN omm_recipes.avg_rating IS '평균 별점';
COMMENT ON COLUMN omm_recipes.review_count IS '후기 총개수 (사이트 표시값)';
COMMENT ON COLUMN omm_recipes.collected_at IS '수집 일시';
CREATE INDEX ix_recipes_menu ON omm_recipes(menu_id);
CREATE INDEX ix_recipes_registered ON omm_recipes(registered_at);

-- 레시피 분류 코드 · 만개 분류: 종류별(cat4) · 상황별(cat2) · 재료별(cat3) · 방법별(cat1)
CREATE TABLE omm_recipe_category_codes (
    category_id          SERIAL NOT NULL,
    cat_type             VARCHAR(30) NOT NULL,
    code                 VARCHAR(10) NOT NULL,
    name                 VARCHAR(30) NOT NULL,
    CONSTRAINT pk_omm_recipe_category_codes PRIMARY KEY (category_id),
    CONSTRAINT uq_omm_recipe_category_codes_cat_type_code UNIQUE (cat_type, code)
);
COMMENT ON TABLE omm_recipe_category_codes IS '레시피 분류 코드 - 만개 분류: 종류별(cat4) · 상황별(cat2) · 재료별(cat3) · 방법별(cat1)';
COMMENT ON COLUMN omm_recipe_category_codes.category_id IS '분류 번호';
COMMENT ON COLUMN omm_recipe_category_codes.cat_type IS '분류 종류 · 공통코드(RCP_CAT_TYPE)';
COMMENT ON COLUMN omm_recipe_category_codes.code IS '만개 분류 코드 (63 = 밑반찬)';
COMMENT ON COLUMN omm_recipe_category_codes.name IS '분류 값 (밑반찬, 메인반찬, 국/탕 …)';

-- 레시피 분류 · 레시피 ↔ 분류 (N:M)
CREATE TABLE omm_recipe_categories (
    recipe_id            INT NOT NULL,
    category_id          INT NOT NULL,
    CONSTRAINT pk_omm_recipe_categories PRIMARY KEY (recipe_id, category_id)
);
COMMENT ON TABLE omm_recipe_categories IS '레시피 분류 - 레시피 ↔ 분류 (N:M)';
COMMENT ON COLUMN omm_recipe_categories.recipe_id IS '레시피';
COMMENT ON COLUMN omm_recipe_categories.category_id IS '분류';

-- 레시피 재료 · 레시피 재료 한 줄. 원문(raw)은 그대로 두고 표준 재료 · 수량 · g · 정량 분류를 붙임
CREATE TABLE omm_recipe_ingredients (
    recipe_id            INT NOT NULL,
    seq                  SMALLINT NOT NULL,
    group_name           VARCHAR(30),
    raw_name             VARCHAR(100) NOT NULL,
    raw_amount           VARCHAR(50),
    material_no          INT,
    ingredient_id        INT,
    qty                  NUMERIC(8,2),
    unit                 VARCHAR(20),
    grams                NUMERIC(8,1),
    amount_class         VARCHAR(30) NOT NULL DEFAULT 'AMOUNT_MISSING',
    CONSTRAINT pk_omm_recipe_ingredients PRIMARY KEY (recipe_id, seq)
);
COMMENT ON TABLE omm_recipe_ingredients IS '레시피 재료 - 레시피 재료 한 줄. 원문(raw)은 그대로 두고 표준 재료 · 수량 · g · 정량 분류를 붙임';
COMMENT ON COLUMN omm_recipe_ingredients.recipe_id IS '레시피';
COMMENT ON COLUMN omm_recipe_ingredients.seq IS '순서';
COMMENT ON COLUMN omm_recipe_ingredients.group_name IS '재료 묶음 이름 ([재료], [양념], [소스])';
COMMENT ON COLUMN omm_recipe_ingredients.raw_name IS '재료 이름 원문';
COMMENT ON COLUMN omm_recipe_ingredients.raw_amount IS '수량 원문 ("1/2개", "2T", "약간")';
COMMENT ON COLUMN omm_recipe_ingredients.material_no IS '만개 재료 번호 (viewMaterial)';
COMMENT ON COLUMN omm_recipe_ingredients.ingredient_id IS '표준 재료 (별칭표로 매칭. 못 찾으면 NULL)';
COMMENT ON COLUMN omm_recipe_ingredients.qty IS '수량 숫자 (1/2 → 0.5)';
COMMENT ON COLUMN omm_recipe_ingredients.unit IS '단위 (개, T, g, 약간)';
COMMENT ON COLUMN omm_recipe_ingredients.grams IS '추정 g (qty × 환산값). 모호 표현은 NULL';
COMMENT ON COLUMN omm_recipe_ingredients.amount_class IS '정량 / 개수 / 모호 / 수량 없음 (분석 8) · 공통코드(AMOUNT_CLASS)';
CREATE INDEX ix_recipe_ingredients_ingredient ON omm_recipe_ingredients(ingredient_id);

-- 요리 후기 · 만개 후기. 작성자 닉네임은 저장하지 않음
CREATE TABLE omm_reviews (
    review_id            INT NOT NULL,
    recipe_id            INT NOT NULL,
    written_at           DATE NOT NULL,
    rating               SMALLINT CHECK (rating BETWEEN 1 AND 5),
    body                 TEXT,
    CONSTRAINT pk_omm_reviews PRIMARY KEY (review_id)
);
COMMENT ON TABLE omm_reviews IS '요리 후기 - 만개 후기. 작성자 닉네임은 저장하지 않음';
COMMENT ON COLUMN omm_reviews.review_id IS '후기 번호 (replyReviewDiv_N)';
COMMENT ON COLUMN omm_reviews.recipe_id IS '레시피';
COMMENT ON COLUMN omm_reviews.written_at IS '작성일';
COMMENT ON COLUMN omm_reviews.rating IS '별점';
COMMENT ON COLUMN omm_reviews.body IS '본문 (맛 표현 · 대체 재료 · 실패 요인 분석)';
CREATE INDEX ix_reviews_recipe_date ON omm_reviews(recipe_id, written_at);
CREATE INDEX ix_reviews_date ON omm_reviews(written_at);

-- 레시피 태그 · 레시피 하단 해시태그
CREATE TABLE omm_recipe_tags (
    recipe_id            INT NOT NULL,
    tag                  VARCHAR(50) NOT NULL,
    CONSTRAINT pk_omm_recipe_tags PRIMARY KEY (recipe_id, tag)
);
COMMENT ON TABLE omm_recipe_tags IS '레시피 태그 - 레시피 하단 해시태그';
COMMENT ON COLUMN omm_recipe_tags.recipe_id IS '레시피';
COMMENT ON COLUMN omm_recipe_tags.tag IS '태그';

-- KAMIS 품목 · 품종 · discover로 찾은 품목 109개 · 품종 180개. 표준 재료와 연결하고, 재료당 대표 품종 하나를 is_primary로
CREATE TABLE omm_kamis_items (
    item_cd              VARCHAR(10) NOT NULL,
    vrty_cd              VARCHAR(10) NOT NULL,
    ctgry_nm             VARCHAR(20) NOT NULL,
    item_nm              VARCHAR(30) NOT NULL,
    vrty_nm              VARCHAR(30),
    unit                 VARCHAR(10),
    unit_sz              NUMERIC(8,2),
    grams_per_unit       NUMERIC(9,1),
    ingredient_id        INT,
    is_primary           BOOLEAN NOT NULL DEFAULT false,
    CONSTRAINT pk_omm_kamis_items PRIMARY KEY (item_cd, vrty_cd)
);
COMMENT ON TABLE omm_kamis_items IS 'KAMIS 품목 · 품종 - discover로 찾은 품목 109개 · 품종 180개. 표준 재료와 연결하고, 재료당 대표 품종 하나를 is_primary로';
COMMENT ON COLUMN omm_kamis_items.item_cd IS '품목 코드';
COMMENT ON COLUMN omm_kamis_items.vrty_cd IS '품종 코드';
COMMENT ON COLUMN omm_kamis_items.ctgry_nm IS '부류 (채소류, 축산물 …)';
COMMENT ON COLUMN omm_kamis_items.item_nm IS '품목 이름';
COMMENT ON COLUMN omm_kamis_items.vrty_nm IS '품종 이름';
COMMENT ON COLUMN omm_kamis_items.unit IS '조사 단위 (kg, 개, 포기)';
COMMENT ON COLUMN omm_kamis_items.unit_sz IS '단위 크기 (1포기, 10개, 20kg)';
COMMENT ON COLUMN omm_kamis_items.grams_per_unit IS '조사 단위 1개의 g (100g당 가격 환산용)';
COMMENT ON COLUMN omm_kamis_items.ingredient_id IS '표준 재료';
COMMENT ON COLUMN omm_kamis_items.is_primary IS '이 재료의 대표 품종 (월별 시세 계산에 씀)';
CREATE UNIQUE INDEX uq_kamis_primary ON omm_kamis_items(ingredient_id) WHERE is_primary;

-- KAMIS 일별 가격 · perDay API 원본. se_cd 01 소매 · 02 도매
CREATE TABLE omm_kamis_prices (
    price_id             BIGSERIAL NOT NULL,
    exmn_ymd             DATE NOT NULL,
    item_cd              VARCHAR(10) NOT NULL,
    vrty_cd              VARCHAR(10) NOT NULL,
    se_cd                VARCHAR(30) NOT NULL,
    grd_cd               VARCHAR(4) NOT NULL DEFAULT '',
    mrkt_nm              VARCHAR(30) NOT NULL DEFAULT '전국',
    price                INT NOT NULL CHECK (price > 0),
    CONSTRAINT pk_omm_kamis_prices PRIMARY KEY (price_id),
    CONSTRAINT uq_omm_kamis_prices_1 UNIQUE (exmn_ymd, item_cd, vrty_cd, se_cd, grd_cd, mrkt_nm)
);
COMMENT ON TABLE omm_kamis_prices IS 'KAMIS 일별 가격 - perDay API 원본. se_cd 01 소매 · 02 도매';
COMMENT ON COLUMN omm_kamis_prices.price_id IS '번호';
COMMENT ON COLUMN omm_kamis_prices.exmn_ymd IS '조사일';
COMMENT ON COLUMN omm_kamis_prices.item_cd IS '품목 코드';
COMMENT ON COLUMN omm_kamis_prices.vrty_cd IS '품종 코드';
COMMENT ON COLUMN omm_kamis_prices.se_cd IS '소매 / 도매 · 공통코드(MARKET_TYPE)';
COMMENT ON COLUMN omm_kamis_prices.grd_cd IS '등급 코드';
COMMENT ON COLUMN omm_kamis_prices.mrkt_nm IS '조사 지역 · 시장';
COMMENT ON COLUMN omm_kamis_prices.price IS '가격 (원, 조사 단위 기준)';
CREATE INDEX ix_kamis_prices_item_date ON omm_kamis_prices(item_cd, vrty_cd, exmn_ymd);

-- 재료 월별 시세 · 대표 품종 일별 가격 → 재료 · 월 · 소매/도매 평균. 평년 대비 · 작년 대비를 미리 계산 (배지 · 산점도 · 3년 흐름)
CREATE TABLE omm_price_monthly (
    ingredient_id        INT NOT NULL,
    ym                   DATE NOT NULL CHECK (extract(day FROM ym) = 1),
    market_type          VARCHAR(30) NOT NULL,
    avg_price            INT NOT NULL,
    unit_label           VARCHAR(20) NOT NULL,
    price_per_100g       NUMERIC(9,1),
    normal_price         INT,
    vs_normal_pct        NUMERIC(6,1),
    yoy_pct              NUMERIC(6,1),
    day_count            SMALLINT NOT NULL,
    price_source         VARCHAR(30),
    CONSTRAINT pk_omm_price_monthly PRIMARY KEY (ingredient_id, ym, market_type)
);
COMMENT ON TABLE omm_price_monthly IS '재료 월별 시세 - 대표 품종 일별 가격 → 재료 · 월 · 소매/도매 평균. 평년 대비 · 작년 대비를 미리 계산 (배지 · 산점도 · 3년 흐름)';
COMMENT ON COLUMN omm_price_monthly.ingredient_id IS '재료';
COMMENT ON COLUMN omm_price_monthly.ym IS '월 (그 달 1일. 2026-11-01 = 2026년 11월)';
COMMENT ON COLUMN omm_price_monthly.market_type IS '소매 / 도매 · 공통코드(MARKET_TYPE)';
COMMENT ON COLUMN omm_price_monthly.avg_price IS '월 평균 가격 (조사 단위 기준)';
COMMENT ON COLUMN omm_price_monthly.unit_label IS '가격 단위 표시 (1포기, 1kg, 10개)';
COMMENT ON COLUMN omm_price_monthly.price_per_100g IS '100g당 가격 (재료비 · 영양 효율 계산)';
COMMENT ON COLUMN omm_price_monthly.normal_price IS '평년 가격 = 직전 5년 같은 달 중 최고 · 최저 뺀 3년 평균 (데이터가 3년 미만이면 있는 해 평균)';
COMMENT ON COLUMN omm_price_monthly.vs_normal_pct IS '평년 대비 등락 %';
COMMENT ON COLUMN omm_price_monthly.yoy_pct IS '작년 같은 달 대비 %';
COMMENT ON COLUMN omm_price_monthly.day_count IS '평균에 쓴 조사일 수';
COMMENT ON COLUMN omm_price_monthly.price_source IS '가격 출처 (팀 공유 데이터: KAMIS 소매 → 참가격 → KAMIS 도매). NULL = 자체 수집 KAMIS로 마트가 계산 · 공통코드(PRICE_SOURCE)';

-- 식품 영양성분 · 식약처 FoodNtrCpntDbInfo03 (원재료성 식품). 모두 100g당
CREATE TABLE omm_nutrition_foods (
    food_cd              VARCHAR(20) NOT NULL,
    food_nm              VARCHAR(100) NOT NULL,
    food_group           VARCHAR(50),
    energy_kcal          NUMERIC(7,1),
    protein_g            NUMERIC(7,2),
    fat_g                NUMERIC(7,2),
    carb_g               NUMERIC(7,2),
    sugar_g              NUMERIC(7,2),
    fiber_g              NUMERIC(7,2),
    sodium_mg            NUMERIC(8,1),
    calcium_mg           NUMERIC(8,1),
    iron_mg              NUMERIC(7,2),
    data_date            DATE,
    CONSTRAINT pk_omm_nutrition_foods PRIMARY KEY (food_cd)
);
COMMENT ON TABLE omm_nutrition_foods IS '식품 영양성분 - 식약처 FoodNtrCpntDbInfo03 (원재료성 식품). 모두 100g당';
COMMENT ON COLUMN omm_nutrition_foods.food_cd IS '식품 코드';
COMMENT ON COLUMN omm_nutrition_foods.food_nm IS '식품 이름';
COMMENT ON COLUMN omm_nutrition_foods.food_group IS '식품 대분류';
COMMENT ON COLUMN omm_nutrition_foods.energy_kcal IS '에너지 kcal';
COMMENT ON COLUMN omm_nutrition_foods.protein_g IS '단백질 g';
COMMENT ON COLUMN omm_nutrition_foods.fat_g IS '지방 g';
COMMENT ON COLUMN omm_nutrition_foods.carb_g IS '탄수화물 g';
COMMENT ON COLUMN omm_nutrition_foods.sugar_g IS '당류 g';
COMMENT ON COLUMN omm_nutrition_foods.fiber_g IS '식이섬유 g';
COMMENT ON COLUMN omm_nutrition_foods.sodium_mg IS '나트륨 mg';
COMMENT ON COLUMN omm_nutrition_foods.calcium_mg IS '칼슘 mg';
COMMENT ON COLUMN omm_nutrition_foods.iron_mg IS '철 mg';
COMMENT ON COLUMN omm_nutrition_foods.data_date IS '데이터 기준일';

-- 메뉴 영양성분 · 식약처 음식 영양성분 DB를 메뉴에 맞춘 값 (팀 공유 데이터 menu_nutrition.csv). 레시피 재료로 계산한 영양값이 없을 때 대신 씀
CREATE TABLE omm_menu_nutrition (
    menu_id              INT NOT NULL,
    value_kind           VARCHAR(30),
    food_names           TEXT,
    serving_g            NUMERIC(7,1),
    kcal_serving         NUMERIC(7,1),
    protein_g_serving    NUMERIC(7,2),
    fat_g_serving        NUMERIC(7,2),
    carb_g_serving       NUMERIC(7,2),
    sugar_g_serving      NUMERIC(7,2),
    sodium_mg_serving    NUMERIC(8,1),
    kcal_100g            NUMERIC(7,1),
    research_date        DATE,
    CONSTRAINT pk_omm_menu_nutrition PRIMARY KEY (menu_id)
);
COMMENT ON TABLE omm_menu_nutrition IS '메뉴 영양성분 - 식약처 음식 영양성분 DB를 메뉴에 맞춘 값 (팀 공유 데이터 menu_nutrition.csv). 레시피 재료로 계산한 영양값이 없을 때 대신 씀';
COMMENT ON COLUMN omm_menu_nutrition.menu_id IS '메뉴';
COMMENT ON COLUMN omm_menu_nutrition.value_kind IS '값 종류 (분석 · g, mL (산출), 시판 제품 …)';
COMMENT ON COLUMN omm_menu_nutrition.food_names IS '맞춘 식약처 음식 이름 (| 로 구분)';
COMMENT ON COLUMN omm_menu_nutrition.serving_g IS '1인분 기준량 g (또는 mL)';
COMMENT ON COLUMN omm_menu_nutrition.kcal_serving IS '1인분 열량';
COMMENT ON COLUMN omm_menu_nutrition.protein_g_serving IS '1인분 단백질 g';
COMMENT ON COLUMN omm_menu_nutrition.fat_g_serving IS '1인분 지방 g';
COMMENT ON COLUMN omm_menu_nutrition.carb_g_serving IS '1인분 탄수화물 g';
COMMENT ON COLUMN omm_menu_nutrition.sugar_g_serving IS '1인분 당류 g';
COMMENT ON COLUMN omm_menu_nutrition.sodium_mg_serving IS '1인분 나트륨 mg';
COMMENT ON COLUMN omm_menu_nutrition.kcal_100g IS '100g당 열량';
COMMENT ON COLUMN omm_menu_nutrition.research_date IS '식약처 조사일';

-- 트렌드 키워드 · YouTube 검색어 (로제, 두바이, 어묵탕 …). 메뉴나 재료와 연결할 수 있으면 연결
CREATE TABLE omm_trend_keywords (
    keyword_id           SERIAL NOT NULL,
    keyword              VARCHAR(50) NOT NULL UNIQUE,
    kind                 VARCHAR(30) NOT NULL,
    menu_id              INT,
    ingredient_id        INT,
    is_active            BOOLEAN NOT NULL DEFAULT true,
    CONSTRAINT pk_omm_trend_keywords PRIMARY KEY (keyword_id)
);
COMMENT ON TABLE omm_trend_keywords IS '트렌드 키워드 - YouTube 검색어 (로제, 두바이, 어묵탕 …). 메뉴나 재료와 연결할 수 있으면 연결';
COMMENT ON COLUMN omm_trend_keywords.keyword_id IS '키워드 번호';
COMMENT ON COLUMN omm_trend_keywords.keyword IS '키워드';
COMMENT ON COLUMN omm_trend_keywords.kind IS '메뉴 / 재료 / 스타일 (로제, 마라, 두바이) · 공통코드(KEYWORD_KIND)';
COMMENT ON COLUMN omm_trend_keywords.menu_id IS '연결 메뉴';
COMMENT ON COLUMN omm_trend_keywords.ingredient_id IS '연결 재료';
COMMENT ON COLUMN omm_trend_keywords.is_active IS '수집 대상 여부 (API 할당량 관리)';

-- YouTube 영상 · search.list + videos.list 결과. 채널은 ID만 저장
CREATE TABLE omm_youtube_videos (
    video_id             VARCHAR(11) NOT NULL,
    title                VARCHAR(300) NOT NULL,
    published_at         TIMESTAMPTZ NOT NULL,
    channel_id           VARCHAR(30),
    view_count           BIGINT,
    like_count           BIGINT,
    comment_count        BIGINT,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_youtube_videos PRIMARY KEY (video_id)
);
COMMENT ON TABLE omm_youtube_videos IS 'YouTube 영상 - search.list + videos.list 결과. 채널은 ID만 저장';
COMMENT ON COLUMN omm_youtube_videos.video_id IS '영상 ID';
COMMENT ON COLUMN omm_youtube_videos.title IS '제목';
COMMENT ON COLUMN omm_youtube_videos.published_at IS '게시 일시';
COMMENT ON COLUMN omm_youtube_videos.channel_id IS '채널 ID';
COMMENT ON COLUMN omm_youtube_videos.view_count IS '조회수 (수집 시점)';
COMMENT ON COLUMN omm_youtube_videos.like_count IS '좋아요';
COMMENT ON COLUMN omm_youtube_videos.comment_count IS '댓글 수';
COMMENT ON COLUMN omm_youtube_videos.collected_at IS '수집 일시';
CREATE INDEX ix_youtube_videos_published ON omm_youtube_videos(published_at);

-- 영상 ↔ 키워드 · 어떤 키워드로 찾았는지 (N:M)
CREATE TABLE omm_youtube_video_keywords (
    video_id             VARCHAR(11) NOT NULL,
    keyword_id           INT NOT NULL,
    matched_by           VARCHAR(30) NOT NULL DEFAULT 'MATCH_SEARCH',
    CONSTRAINT pk_omm_youtube_video_keywords PRIMARY KEY (video_id, keyword_id)
);
COMMENT ON TABLE omm_youtube_video_keywords IS '영상 ↔ 키워드 - 어떤 키워드로 찾았는지 (N:M)';
COMMENT ON COLUMN omm_youtube_video_keywords.video_id IS '영상';
COMMENT ON COLUMN omm_youtube_video_keywords.keyword_id IS '키워드';
COMMENT ON COLUMN omm_youtube_video_keywords.matched_by IS '검색 결과 / 제목에 포함 · 공통코드(MATCHED_BY)';

-- 식약처 레시피 · 식약처 조리식품 레시피 DB (COOKRCP01). 몽고 OMM_recipes 와 rcp_seq 로 연결. 조리 단계 · 단계 사진은 몽고에만 저장
CREATE TABLE omm_fs_recipes (
    rcp_seq              INT NOT NULL,
    menu_id              INT,
    name                 VARCHAR(100) NOT NULL,
    dish_type            VARCHAR(30) NOT NULL,
    cook_method          VARCHAR(20),
    servings             SMALLINT,
    kcal                 NUMERIC(7,1),
    protein_g            NUMERIC(6,1),
    fat_g                NUMERIC(6,1),
    carb_g               NUMERIC(6,1),
    sodium_mg            NUMERIC(8,1),
    image_url            VARCHAR(500),
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_fs_recipes PRIMARY KEY (rcp_seq)
);
COMMENT ON TABLE omm_fs_recipes IS '식약처 레시피 - 식약처 조리식품 레시피 DB (COOKRCP01). 몽고 OMM_recipes 와 rcp_seq 로 연결. 조리 단계 · 단계 사진은 몽고에만 저장';
COMMENT ON COLUMN omm_fs_recipes.rcp_seq IS '레시피 일련번호 (RCP_SEQ). 몽고 OMM_recipes.rcp_seq';
COMMENT ON COLUMN omm_fs_recipes.menu_id IS '같은 요리의 메뉴 (만개 레시피와 메뉴 단위로 연결). 못 찾으면 NULL';
COMMENT ON COLUMN omm_fs_recipes.name IS '메뉴 이름 (RCP_NM)';
COMMENT ON COLUMN omm_fs_recipes.dish_type IS '요리 종류 (밥, 국&찌개, 반찬, 일품, 후식) · 공통코드(FS_DISH_TYPE)';
COMMENT ON COLUMN omm_fs_recipes.cook_method IS '조리 방법 (RCP_WAY2: 끓이기, 볶기, 굽기 …)';
COMMENT ON COLUMN omm_fs_recipes.servings IS '원래 몇 인분인지';
COMMENT ON COLUMN omm_fs_recipes.kcal IS '열량 (INFO_ENG)';
COMMENT ON COLUMN omm_fs_recipes.protein_g IS '단백질 g (INFO_PRO)';
COMMENT ON COLUMN omm_fs_recipes.fat_g IS '지방 g (INFO_FAT)';
COMMENT ON COLUMN omm_fs_recipes.carb_g IS '탄수화물 g (INFO_CAR)';
COMMENT ON COLUMN omm_fs_recipes.sodium_mg IS '나트륨 mg (INFO_NA)';
COMMENT ON COLUMN omm_fs_recipes.image_url IS '메뉴 이미지 주소 (ATT_FILE_NO_MAIN)';
COMMENT ON COLUMN omm_fs_recipes.collected_at IS '수집 일시';
CREATE INDEX ix_fs_recipes_menu ON omm_fs_recipes(menu_id);

-- 식약처 레시피 재료 · 식약처 레시피의 재료 한 줄. 몽고 OMM_recipes.ingredients 와 같은 내용을 분석용으로 정리 (재료 번호는 PG가 발급)
CREATE TABLE omm_fs_recipe_ingredients (
    rcp_seq              INT NOT NULL,
    seq                  SMALLINT NOT NULL,
    raw_name             VARCHAR(100) NOT NULL,
    ingredient_id        INT,
    amount_text          VARCHAR(50),
    weight_g             NUMERIC(8,1),
    CONSTRAINT pk_omm_fs_recipe_ingredients PRIMARY KEY (rcp_seq, seq)
);
COMMENT ON TABLE omm_fs_recipe_ingredients IS '식약처 레시피 재료 - 식약처 레시피의 재료 한 줄. 몽고 OMM_recipes.ingredients 와 같은 내용을 분석용으로 정리 (재료 번호는 PG가 발급)';
COMMENT ON COLUMN omm_fs_recipe_ingredients.rcp_seq IS '레시피';
COMMENT ON COLUMN omm_fs_recipe_ingredients.seq IS '재료 순서';
COMMENT ON COLUMN omm_fs_recipe_ingredients.raw_name IS '레시피 원문 재료 이름 (몽고 ingredients.raw_name)';
COMMENT ON COLUMN omm_fs_recipe_ingredients.ingredient_id IS '표준 재료 (몽고 ingredients.ingredient_id). 못 찾으면 NULL';
COMMENT ON COLUMN omm_fs_recipe_ingredients.amount_text IS '원문 수량 (2큰술, 100g)';
COMMENT ON COLUMN omm_fs_recipe_ingredients.weight_g IS '1인분 필요량 g (몽고 ingredients.weight_g)';
CREATE INDEX ix_fs_recipe_ingredients_ingredient ON omm_fs_recipe_ingredients(ingredient_id);

-- 회원 · 회원 기본 정보. 몽고 OMM_fridge · OMM_receipts · OMM_user_events 의 user_id 가 참조. 비밀번호는 해시만 저장
CREATE TABLE omm_users (
    user_id              SERIAL NOT NULL,
    email                VARCHAR(100) NOT NULL UNIQUE,
    password_hash        VARCHAR(100) NOT NULL,
    nickname             VARCHAR(30) NOT NULL,
    household_size       SMALLINT CHECK (household_size BETWEEN 1 AND 10),
    status               VARCHAR(30) NOT NULL DEFAULT 'USER_ACTIVE',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_users PRIMARY KEY (user_id)
);
COMMENT ON TABLE omm_users IS '회원 - 회원 기본 정보. 몽고 OMM_fridge · OMM_receipts · OMM_user_events 의 user_id 가 참조. 비밀번호는 해시만 저장';
COMMENT ON COLUMN omm_users.user_id IS '회원 번호 (몽고 user_id)';
COMMENT ON COLUMN omm_users.email IS '로그인 이메일';
COMMENT ON COLUMN omm_users.password_hash IS '비밀번호 해시 (bcrypt 등). 원문 저장 안 함';
COMMENT ON COLUMN omm_users.nickname IS '화면 표시 이름';
COMMENT ON COLUMN omm_users.household_size IS '가구원 수 (인분 계산 기본값)';
COMMENT ON COLUMN omm_users.status IS '회원 상태 · 공통코드(USER_STATUS)';
COMMENT ON COLUMN omm_users.created_at IS '가입 일시';

-- 회원 취향 · 취향 입력 화면에서 고른 태그 (먹고 싶은 / 제외할). 입력 기록 원본은 몽고 OMM_user_events
CREATE TABLE omm_user_preferences (
    user_id              INT NOT NULL,
    tag_id               INT NOT NULL,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_user_preferences PRIMARY KEY (user_id, tag_id)
);
COMMENT ON TABLE omm_user_preferences IS '회원 취향 - 취향 입력 화면에서 고른 태그 (먹고 싶은 / 제외할). 입력 기록 원본은 몽고 OMM_user_events';
COMMENT ON COLUMN omm_user_preferences.user_id IS '회원';
COMMENT ON COLUMN omm_user_preferences.tag_id IS '취향 태그';
COMMENT ON COLUMN omm_user_preferences.created_at IS '고른 일시';

-- 컬리 상품 · 재료별 컬리 상품 목록. 날짜별 가격 · 품절은 몽고 OMM_kurly_prices, 제외 상품은 몽고 OMM_kurly_excluded
CREATE TABLE omm_kurly_products (
    goods_no             BIGINT NOT NULL,
    product_name         VARCHAR(200) NOT NULL,
    ingredient_id        INT NOT NULL,
    rank                 SMALLINT,
    product_url          VARCHAR(500),
    is_active            BOOLEAN NOT NULL DEFAULT true,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_kurly_products PRIMARY KEY (goods_no)
);
COMMENT ON TABLE omm_kurly_products IS '컬리 상품 - 재료별 컬리 상품 목록. 날짜별 가격 · 품절은 몽고 OMM_kurly_prices, 제외 상품은 몽고 OMM_kurly_excluded';
COMMENT ON COLUMN omm_kurly_products.goods_no IS '컬리 상품번호 (몽고 goods_no)';
COMMENT ON COLUMN omm_kurly_products.product_name IS '상품 이름';
COMMENT ON COLUMN omm_kurly_products.ingredient_id IS '매핑된 재료';
COMMENT ON COLUMN omm_kurly_products.rank IS '그 재료 안에서의 순위 (싼 순)';
COMMENT ON COLUMN omm_kurly_products.product_url IS '상품 페이지 주소';
COMMENT ON COLUMN omm_kurly_products.is_active IS '판매 · 매핑 사용 여부';
COMMENT ON COLUMN omm_kurly_products.updated_at IS '마지막 갱신';
CREATE INDEX ix_kurly_products_ingredient ON omm_kurly_products(ingredient_id, rank);

-- 주문 · 장보기 주문 (OMM 구매). 몽고 OMM_fridge.items.order_id · OMM_user_events.order_id 가 참조
CREATE TABLE omm_orders (
    order_id             BIGSERIAL NOT NULL,
    user_id              INT NOT NULL,
    menu_id              INT,
    rcp_seq              INT,
    status               VARCHAR(30) NOT NULL DEFAULT 'ORDER_CART',
    total_price          INT NOT NULL DEFAULT 0,
    ordered_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_orders PRIMARY KEY (order_id)
);
COMMENT ON TABLE omm_orders IS '주문 - 장보기 주문 (OMM 구매). 몽고 OMM_fridge.items.order_id · OMM_user_events.order_id 가 참조';
COMMENT ON COLUMN omm_orders.order_id IS '주문 번호 (몽고 order_id)';
COMMENT ON COLUMN omm_orders.user_id IS '회원';
COMMENT ON COLUMN omm_orders.menu_id IS '어떤 메뉴 장보기로 산 건지 (없으면 NULL)';
COMMENT ON COLUMN omm_orders.rcp_seq IS '식약처 레시피로 산 경우 (몽고 OMM_menu_costs.rcp_seq)';
COMMENT ON COLUMN omm_orders.status IS '주문 상태 · 공통코드(ORDER_STATUS)';
COMMENT ON COLUMN omm_orders.total_price IS '합계 금액';
COMMENT ON COLUMN omm_orders.ordered_at IS '주문 일시';
CREATE INDEX ix_orders_user ON omm_orders(user_id, ordered_at);

-- 주문 상품 · 주문에 담긴 컬리 상품. 가격은 주문 시점 값으로 저장
CREATE TABLE omm_order_items (
    order_id             BIGINT NOT NULL,
    goods_no             BIGINT NOT NULL,
    ingredient_id        INT,
    quantity             SMALLINT NOT NULL DEFAULT 1 CHECK (quantity > 0),
    unit_price           INT NOT NULL,
    CONSTRAINT pk_omm_order_items PRIMARY KEY (order_id, goods_no)
);
COMMENT ON TABLE omm_order_items IS '주문 상품 - 주문에 담긴 컬리 상품. 가격은 주문 시점 값으로 저장';
COMMENT ON COLUMN omm_order_items.order_id IS '주문';
COMMENT ON COLUMN omm_order_items.goods_no IS '컬리 상품';
COMMENT ON COLUMN omm_order_items.ingredient_id IS '어떤 재료로 산 건지';
COMMENT ON COLUMN omm_order_items.quantity IS '수량';
COMMENT ON COLUMN omm_order_items.unit_price IS '주문 시점 판매가';

-- 메뉴 군집 · 분석 1. 조리시간 × 재료비 K-means 4개 (자취형 · 대접형 …)
CREATE TABLE omm_menu_clusters (
    cluster_id           SMALLINT NOT NULL,
    name                 VARCHAR(20) NOT NULL UNIQUE,
    description          VARCHAR(200),
    center_cook_min      NUMERIC(6,1),
    center_cost_won      INT,
    recipe_count         INT NOT NULL DEFAULT 0,
    CONSTRAINT pk_omm_menu_clusters PRIMARY KEY (cluster_id)
);
COMMENT ON TABLE omm_menu_clusters IS '메뉴 군집 - 분석 1. 조리시간 × 재료비 K-means 4개 (자취형 · 대접형 …)';
COMMENT ON COLUMN omm_menu_clusters.cluster_id IS '군집 번호';
COMMENT ON COLUMN omm_menu_clusters.name IS '군집 이름 (자취형, 간편 한 끼, 주말 요리, 대접형)';
COMMENT ON COLUMN omm_menu_clusters.description IS '설명';
COMMENT ON COLUMN omm_menu_clusters.center_cook_min IS '중심 조리시간 분';
COMMENT ON COLUMN omm_menu_clusters.center_cost_won IS '중심 1인분 재료비';
COMMENT ON COLUMN omm_menu_clusters.recipe_count IS '레시피 수';

-- 레시피 분석값 · 레시피 1건당 1행. 재료비 · 영양 · 신뢰도 · 사람 이름 · 군집 (분석 1·2·3·6·8)
CREATE TABLE omm_recipe_metrics (
    recipe_id            INT NOT NULL,
    base_ym              DATE NOT NULL,
    est_cost_won         INT,
    cost_per_serving     INT,
    priced_ratio         NUMERIC(4,3),
    kcal_per_serving     NUMERIC(7,1),
    protein_per_serving  NUMERIC(6,1),
    sodium_per_serving   NUMERIC(8,1),
    protein_per_1000won  NUMERIC(6,2),
    kcal_per_1000won     NUMERIC(7,1),
    measured_ratio       NUMERIC(4,3),
    vague_count          SMALLINT NOT NULL DEFAULT 0,
    reliability_grade    VARCHAR(30),
    person_name          VARCHAR(20),
    cluster_id           SMALLINT,
    reviews_1y           INT NOT NULL DEFAULT 0,
    calculated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_recipe_metrics PRIMARY KEY (recipe_id)
);
COMMENT ON TABLE omm_recipe_metrics IS '레시피 분석값 - 레시피 1건당 1행. 재료비 · 영양 · 신뢰도 · 사람 이름 · 군집 (분석 1·2·3·6·8)';
COMMENT ON COLUMN omm_recipe_metrics.recipe_id IS '레시피';
COMMENT ON COLUMN omm_recipe_metrics.base_ym IS '재료비 계산에 쓴 시세 월';
COMMENT ON COLUMN omm_recipe_metrics.est_cost_won IS '예상 재료비 (양념 제외, 가격 있는 재료만)';
COMMENT ON COLUMN omm_recipe_metrics.cost_per_serving IS '1인분 재료비';
COMMENT ON COLUMN omm_recipe_metrics.priced_ratio IS '가격을 찾은 재료 비율 (낮으면 재료비 신뢰 낮음)';
COMMENT ON COLUMN omm_recipe_metrics.kcal_per_serving IS '1인분 열량';
COMMENT ON COLUMN omm_recipe_metrics.protein_per_serving IS '1인분 단백질 g';
COMMENT ON COLUMN omm_recipe_metrics.sodium_per_serving IS '1인분 나트륨 mg';
COMMENT ON COLUMN omm_recipe_metrics.protein_per_1000won IS '1,000원당 단백질 g (분석 6)';
COMMENT ON COLUMN omm_recipe_metrics.kcal_per_1000won IS '1,000원당 열량';
COMMENT ON COLUMN omm_recipe_metrics.measured_ratio IS '정량(MEASURED + COUNTED) 재료 비율 (분석 8)';
COMMENT ON COLUMN omm_recipe_metrics.vague_count IS '모호 표현 재료 수';
COMMENT ON COLUMN omm_recipe_metrics.reliability_grade IS '신뢰도 등급 A ≥ 90% 정량 … D < 50% · 공통코드(RELIABILITY)';
COMMENT ON COLUMN omm_recipe_metrics.person_name IS '제목 속 사람 이름 (백종원, 류수영 …). 없으면 NULL (분석 3)';
COMMENT ON COLUMN omm_recipe_metrics.cluster_id IS '군집 (분석 1)';
COMMENT ON COLUMN omm_recipe_metrics.reviews_1y IS '최근 1년 후기 수 (대표 레시피 · 정렬)';
COMMENT ON COLUMN omm_recipe_metrics.calculated_at IS '계산 일시';
CREATE INDEX ix_recipe_metrics_cluster ON omm_recipe_metrics(cluster_id);

-- 맛 표현 사전 · 분석 4. 매콤 · 칼칼 · 얼큰 → 매운맛, 고소 · 담백 …
CREATE TABLE omm_taste_words (
    taste_id             SERIAL NOT NULL,
    word                 VARCHAR(20) NOT NULL UNIQUE,
    taste_group          VARCHAR(10) NOT NULL,
    CONSTRAINT pk_omm_taste_words PRIMARY KEY (taste_id)
);
COMMENT ON TABLE omm_taste_words IS '맛 표현 사전 - 분석 4. 매콤 · 칼칼 · 얼큰 → 매운맛, 고소 · 담백 …';
COMMENT ON COLUMN omm_taste_words.taste_id IS '번호';
COMMENT ON COLUMN omm_taste_words.word IS '표현 (매콤, 얼큰, 달달)';
COMMENT ON COLUMN omm_taste_words.taste_group IS '맛 묶음 (매운맛, 단맛, 짠맛, 고소함, 담백함, 새콤함, 국물)';

-- 레시피 맛 표현 · 제목 · 소개 · 태그 · 후기에서 찾은 맛 표현 횟수
CREATE TABLE omm_recipe_tastes (
    recipe_id            INT NOT NULL,
    taste_id             INT NOT NULL,
    source               VARCHAR(30) NOT NULL,
    mention_count        SMALLINT NOT NULL DEFAULT 1,
    CONSTRAINT pk_omm_recipe_tastes PRIMARY KEY (recipe_id, taste_id, source)
);
COMMENT ON TABLE omm_recipe_tastes IS '레시피 맛 표현 - 제목 · 소개 · 태그 · 후기에서 찾은 맛 표현 횟수';
COMMENT ON COLUMN omm_recipe_tastes.recipe_id IS '레시피';
COMMENT ON COLUMN omm_recipe_tastes.taste_id IS '맛 표현';
COMMENT ON COLUMN omm_recipe_tastes.source IS '어디서 찾았는지 · 공통코드(TASTE_SOURCE)';
COMMENT ON COLUMN omm_recipe_tastes.mention_count IS '등장 횟수';
CREATE INDEX ix_recipe_tastes_taste ON omm_recipe_tastes(taste_id);

-- 재료 월별 관심도 · 재료가 들어간 신규 레시피 + 후기 + YouTube 영상. 같은 달 작년 대비로 계절 효과 제거
CREATE TABLE omm_ingredient_interest_monthly (
    ingredient_id        INT NOT NULL,
    ym                   DATE NOT NULL CHECK (extract(day FROM ym) = 1),
    new_recipe_cnt       INT NOT NULL DEFAULT 0,
    review_cnt           INT NOT NULL DEFAULT 0,
    yt_video_cnt         INT NOT NULL DEFAULT 0,
    interest_cnt         INT NOT NULL DEFAULT 0,
    interest_index       NUMERIC(5,1),
    yoy_pct              NUMERIC(6,1),
    CONSTRAINT pk_omm_ingredient_interest_monthly PRIMARY KEY (ingredient_id, ym)
);
COMMENT ON TABLE omm_ingredient_interest_monthly IS '재료 월별 관심도 - 재료가 들어간 신규 레시피 + 후기 + YouTube 영상. 같은 달 작년 대비로 계절 효과 제거';
COMMENT ON COLUMN omm_ingredient_interest_monthly.ingredient_id IS '재료';
COMMENT ON COLUMN omm_ingredient_interest_monthly.ym IS '월 (그 달 1일. 2026-11-01 = 2026년 11월)';
COMMENT ON COLUMN omm_ingredient_interest_monthly.new_recipe_cnt IS '그 달 등록된 레시피 수';
COMMENT ON COLUMN omm_ingredient_interest_monthly.review_cnt IS '그 달 작성된 후기 수';
COMMENT ON COLUMN omm_ingredient_interest_monthly.yt_video_cnt IS '그 달 게시된 YouTube 영상 수';
COMMENT ON COLUMN omm_ingredient_interest_monthly.interest_cnt IS '관심도 = 신규 레시피 + 후기';
COMMENT ON COLUMN omm_ingredient_interest_monthly.interest_index IS '최근 12개월 최대 달 = 100';
COMMENT ON COLUMN omm_ingredient_interest_monthly.yoy_pct IS '작년 같은 달 대비 %';

-- 메뉴 월별 관심도 · 메뉴 카드 관심도 ▲% · 상세 차트 · 뜨는/지는 메뉴
CREATE TABLE omm_menu_interest_monthly (
    menu_id              INT NOT NULL,
    ym                   DATE NOT NULL CHECK (extract(day FROM ym) = 1),
    new_recipe_cnt       INT NOT NULL DEFAULT 0,
    review_cnt           INT NOT NULL DEFAULT 0,
    yt_video_cnt         INT NOT NULL DEFAULT 0,
    interest_cnt         INT NOT NULL DEFAULT 0,
    interest_index       NUMERIC(5,1),
    yt_index             NUMERIC(5,1),
    yoy_pct              NUMERIC(6,1),
    yt_yoy_pct           NUMERIC(6,1),
    CONSTRAINT pk_omm_menu_interest_monthly PRIMARY KEY (menu_id, ym)
);
COMMENT ON TABLE omm_menu_interest_monthly IS '메뉴 월별 관심도 - 메뉴 카드 관심도 ▲% · 상세 차트 · 뜨는/지는 메뉴';
COMMENT ON COLUMN omm_menu_interest_monthly.menu_id IS '메뉴';
COMMENT ON COLUMN omm_menu_interest_monthly.ym IS '월 (그 달 1일. 2026-11-01 = 2026년 11월)';
COMMENT ON COLUMN omm_menu_interest_monthly.new_recipe_cnt IS '신규 레시피 수';
COMMENT ON COLUMN omm_menu_interest_monthly.review_cnt IS '후기 수';
COMMENT ON COLUMN omm_menu_interest_monthly.yt_video_cnt IS 'YouTube 영상 수';
COMMENT ON COLUMN omm_menu_interest_monthly.interest_cnt IS '관심도 = 신규 레시피 + 후기';
COMMENT ON COLUMN omm_menu_interest_monthly.interest_index IS '최근 12개월 최대 달 = 100';
COMMENT ON COLUMN omm_menu_interest_monthly.yt_index IS 'YouTube 영상 지수 (최대 달 = 100)';
COMMENT ON COLUMN omm_menu_interest_monthly.yoy_pct IS '관심도 작년 같은 달 대비 %';
COMMENT ON COLUMN omm_menu_interest_monthly.yt_yoy_pct IS 'YouTube 작년 같은 달 대비 %';

-- 키워드 월별 트렌드 · 분석 5. YouTube 영상 수 · 조회수 + 같은 키워드의 만개 레시피 수
CREATE TABLE omm_keyword_trend_monthly (
    keyword_id           INT NOT NULL,
    ym                   DATE NOT NULL CHECK (extract(day FROM ym) = 1),
    yt_video_cnt         INT NOT NULL DEFAULT 0,
    yt_view_sum          BIGINT NOT NULL DEFAULT 0,
    recipe_cnt           INT NOT NULL DEFAULT 0,
    yoy_pct              NUMERIC(6,1),
    CONSTRAINT pk_omm_keyword_trend_monthly PRIMARY KEY (keyword_id, ym)
);
COMMENT ON TABLE omm_keyword_trend_monthly IS '키워드 월별 트렌드 - 분석 5. YouTube 영상 수 · 조회수 + 같은 키워드의 만개 레시피 수';
COMMENT ON COLUMN omm_keyword_trend_monthly.keyword_id IS '키워드';
COMMENT ON COLUMN omm_keyword_trend_monthly.ym IS '월 (그 달 1일. 2026-11-01 = 2026년 11월)';
COMMENT ON COLUMN omm_keyword_trend_monthly.yt_video_cnt IS '게시 영상 수';
COMMENT ON COLUMN omm_keyword_trend_monthly.yt_view_sum IS '그 달 게시 영상 조회수 합';
COMMENT ON COLUMN omm_keyword_trend_monthly.recipe_cnt IS '제목에 키워드가 든 신규 만개 레시피 수';
COMMENT ON COLUMN omm_keyword_trend_monthly.yoy_pct IS '영상 수 작년 대비 %';

-- 가격-관심도 시차 상관 · 평년 대비 가격 vs 0~3개월 뒤 관심도 변화의 상관계수. ingredient_id NULL = 재료 전체
CREATE TABLE omm_price_interest_corr (
    corr_id              SERIAL NOT NULL,
    ingredient_id        INT,
    lag_month            SMALLINT NOT NULL CHECK (lag_month BETWEEN 0 AND 6),
    corr                 NUMERIC(4,3) NOT NULL,
    n_months             SMALLINT NOT NULL,
    period_from          DATE NOT NULL,
    period_to            DATE NOT NULL,
    CONSTRAINT pk_omm_price_interest_corr PRIMARY KEY (corr_id),
    CONSTRAINT cs_omm_price_interest_corr_1 UNIQUE NULLS NOT DISTINCT (ingredient_id, lag_month, period_from, period_to)
);
COMMENT ON TABLE omm_price_interest_corr IS '가격-관심도 시차 상관 - 평년 대비 가격 vs 0~3개월 뒤 관심도 변화의 상관계수. ingredient_id NULL = 재료 전체';
COMMENT ON COLUMN omm_price_interest_corr.corr_id IS '번호';
COMMENT ON COLUMN omm_price_interest_corr.ingredient_id IS '재료 (NULL = 전체)';
COMMENT ON COLUMN omm_price_interest_corr.lag_month IS '시차 (개월)';
COMMENT ON COLUMN omm_price_interest_corr.corr IS '상관계수 r';
COMMENT ON COLUMN omm_price_interest_corr.n_months IS '계산에 쓴 개월 수';
COMMENT ON COLUMN omm_price_interest_corr.period_from IS '기간 시작 월';
COMMENT ON COLUMN omm_price_interest_corr.period_to IS '기간 끝 월';

-- 재료 네트워크 노드 · 분석 7. 중심성 · 커뮤니티 (양념 제외)
CREATE TABLE omm_ingredient_network_nodes (
    ingredient_id        INT NOT NULL,
    recipe_count         INT NOT NULL,
    degree               INT NOT NULL,
    degree_centrality    NUMERIC(6,4),
    betweenness          NUMERIC(6,4),
    community_id         SMALLINT,
    community_name       VARCHAR(30),
    CONSTRAINT pk_omm_ingredient_network_nodes PRIMARY KEY (ingredient_id)
);
COMMENT ON TABLE omm_ingredient_network_nodes IS '재료 네트워크 노드 - 분석 7. 중심성 · 커뮤니티 (양념 제외)';
COMMENT ON COLUMN omm_ingredient_network_nodes.ingredient_id IS '재료';
COMMENT ON COLUMN omm_ingredient_network_nodes.recipe_count IS '등장 레시피 수';
COMMENT ON COLUMN omm_ingredient_network_nodes.degree IS '연결 재료 수';
COMMENT ON COLUMN omm_ingredient_network_nodes.degree_centrality IS '연결 중심성';
COMMENT ON COLUMN omm_ingredient_network_nodes.betweenness IS '매개 중심성 (요리군을 잇는 다리 재료)';
COMMENT ON COLUMN omm_ingredient_network_nodes.community_id IS 'Louvain 커뮤니티 번호';
COMMENT ON COLUMN omm_ingredient_network_nodes.community_name IS '커뮤니티 이름 (찌개군, 파스타군 …)';

-- 재료 네트워크 연결 · 같은 레시피에 함께 쓰인 재료 쌍. a < b로 한 번만 저장
CREATE TABLE omm_ingredient_network_edges (
    ingredient_a         INT NOT NULL,
    ingredient_b         INT NOT NULL,
    co_count             INT NOT NULL,
    lift                 NUMERIC(8,3),
    pmi                  NUMERIC(7,3),
    CONSTRAINT pk_omm_ingredient_network_edges PRIMARY KEY (ingredient_a, ingredient_b),
    CONSTRAINT ck_omm_ingredient_network_edges_1 CHECK (ingredient_a < ingredient_b)
);
COMMENT ON TABLE omm_ingredient_network_edges IS '재료 네트워크 연결 - 같은 레시피에 함께 쓰인 재료 쌍. a < b로 한 번만 저장';
COMMENT ON COLUMN omm_ingredient_network_edges.ingredient_a IS '재료 A (번호 작은 쪽)';
COMMENT ON COLUMN omm_ingredient_network_edges.ingredient_b IS '재료 B';
COMMENT ON COLUMN omm_ingredient_network_edges.co_count IS '함께 나온 레시피 수';
COMMENT ON COLUMN omm_ingredient_network_edges.lift IS 'Lift (1보다 크면 우연보다 자주 같이 씀)';
COMMENT ON COLUMN omm_ingredient_network_edges.pmi IS 'PMI';
CREATE INDEX ix_network_edges_b ON omm_ingredient_network_edges(ingredient_b);

-- 비슷한 메뉴 · 재료 겹침(Jaccard)으로 구한 비슷한 메뉴 (상세 화면)
CREATE TABLE omm_menu_similarities (
    menu_id              INT NOT NULL,
    similar_menu_id      INT NOT NULL,
    score                NUMERIC(4,3) NOT NULL,
    rank                 SMALLINT NOT NULL,
    CONSTRAINT pk_omm_menu_similarities PRIMARY KEY (menu_id, similar_menu_id),
    CONSTRAINT ck_omm_menu_similarities_1 CHECK (menu_id <> similar_menu_id)
);
COMMENT ON TABLE omm_menu_similarities IS '비슷한 메뉴 - 재료 겹침(Jaccard)으로 구한 비슷한 메뉴 (상세 화면)';
COMMENT ON COLUMN omm_menu_similarities.menu_id IS '메뉴';
COMMENT ON COLUMN omm_menu_similarities.similar_menu_id IS '비슷한 메뉴';
COMMENT ON COLUMN omm_menu_similarities.score IS '유사도 0~1';
COMMENT ON COLUMN omm_menu_similarities.rank IS '순위';

-- 대체 재료 · 비싸지면 무엇으로 바꿀까. NETWORK 이웃 유사 · REVIEW 후기 "대신" 언급 · TREND 같은 요리 종류에서 관심도 반대로 움직임
CREATE TABLE omm_ingredient_substitutes (
    ingredient_id        INT NOT NULL,
    substitute_id        INT NOT NULL,
    basis                VARCHAR(30) NOT NULL,
    dish_type            VARCHAR(20),
    score                NUMERIC(6,3) NOT NULL,
    evidence_cnt         INT NOT NULL DEFAULT 0,
    CONSTRAINT pk_omm_ingredient_substitutes PRIMARY KEY (ingredient_id, substitute_id, basis),
    CONSTRAINT ck_omm_ingredient_substitutes_1 CHECK (ingredient_id <> substitute_id)
);
COMMENT ON TABLE omm_ingredient_substitutes IS '대체 재료 - 비싸지면 무엇으로 바꿀까. NETWORK 이웃 유사 · REVIEW 후기 "대신" 언급 · TREND 같은 요리 종류에서 관심도 반대로 움직임';
COMMENT ON COLUMN omm_ingredient_substitutes.ingredient_id IS '원래 재료';
COMMENT ON COLUMN omm_ingredient_substitutes.substitute_id IS '대체 재료';
COMMENT ON COLUMN omm_ingredient_substitutes.basis IS '근거 · 공통코드(SUBST_BASIS)';
COMMENT ON COLUMN omm_ingredient_substitutes.dish_type IS '어떤 요리 종류에서 (김치, 국 …). NULL = 전체';
COMMENT ON COLUMN omm_ingredient_substitutes.score IS '점수 (클수록 우선)';
COMMENT ON COLUMN omm_ingredient_substitutes.evidence_cnt IS '근거 수 (레시피 · 후기 수)';

-- 수집 · 계산 기록 · 크롤링 · API 수집 · 마트 계산 실행 기록 (KAMIS 일 10,000건 · YouTube 일 10,000 units 관리)
CREATE TABLE omm_etl_runs (
    run_id               BIGSERIAL NOT NULL,
    source               VARCHAR(30) NOT NULL,
    job                  VARCHAR(50) NOT NULL,
    started_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at          TIMESTAMPTZ,
    status               VARCHAR(30) NOT NULL DEFAULT 'ETL_RUNNING',
    row_count            INT,
    api_units            INT,
    message              TEXT,
    CONSTRAINT pk_omm_etl_runs PRIMARY KEY (run_id)
);
COMMENT ON TABLE omm_etl_runs IS '수집 · 계산 기록 - 크롤링 · API 수집 · 마트 계산 실행 기록 (KAMIS 일 10,000건 · YouTube 일 10,000 units 관리)';
COMMENT ON COLUMN omm_etl_runs.run_id IS '실행 번호';
COMMENT ON COLUMN omm_etl_runs.source IS '출처 · 공통코드(DATA_SOURCE)';
COMMENT ON COLUMN omm_etl_runs.job IS '작업 이름 (crawl_10000recipe, kamis_monthly 2026-10 …)';
COMMENT ON COLUMN omm_etl_runs.started_at IS '시작';
COMMENT ON COLUMN omm_etl_runs.finished_at IS '끝';
COMMENT ON COLUMN omm_etl_runs.status IS '상태 · 공통코드(ETL_STATUS)';
COMMENT ON COLUMN omm_etl_runs.row_count IS '적재 행 수';
COMMENT ON COLUMN omm_etl_runs.api_units IS 'API 호출 수 · YouTube units';
COMMENT ON COLUMN omm_etl_runs.message IS '오류 · 메모';
CREATE INDEX ix_etl_runs_source ON omm_etl_runs(source, started_at);

-- 공통코드 기본값 (상태 · 종류 값을 한곳에서 관리)
INSERT INTO omm_common_codes (code_id, group_code, group_nm, code, code_nm, group_sort, sort, description) VALUES
  ('MARKET_RETAIL', 'MARKET_TYPE', '시장 구분', 'RETAIL', '소매', 1, 1, 'KAMIS se_cd 01'),
  ('MARKET_WHOLESALE', 'MARKET_TYPE', '시장 구분', 'WHOLESALE', '도매', 1, 2, 'KAMIS se_cd 02'),
  ('AMOUNT_MEASURED', 'AMOUNT_CLASS', '수량 표기', 'MEASURED', '정량 (g · ml · T · 컵)', 2, 1, NULL),
  ('AMOUNT_COUNTED', 'AMOUNT_CLASS', '수량 표기', 'COUNTED', '개수 (개 · 모 · 대)', 2, 2, NULL),
  ('AMOUNT_VAGUE', 'AMOUNT_CLASS', '수량 표기', 'VAGUE', '모호 (약간 · 적당량 · 넉넉히)', 2, 3, '분석 8'),
  ('AMOUNT_MISSING', 'AMOUNT_CLASS', '수량 표기', 'MISSING', '수량 없음', 2, 4, NULL),
  ('DIFF_ANYONE', 'DIFFICULTY', '난이도', 'ANYONE', '아무나', 3, 1, NULL),
  ('DIFF_BEGINNER', 'DIFFICULTY', '난이도', 'BEGINNER', '초급', 3, 2, NULL),
  ('DIFF_INTERMEDIATE', 'DIFFICULTY', '난이도', 'INTERMEDIATE', '중급', 3, 3, NULL),
  ('DIFF_ADVANCED', 'DIFFICULTY', '난이도', 'ADVANCED', '고급', 3, 4, NULL),
  ('DIFF_MASTER', 'DIFFICULTY', '난이도', 'MASTER', '신의경지', 3, 5, NULL),
  ('CATTYPE_KIND', 'RCP_CAT_TYPE', '레시피 분류 종류', 'KIND', '종류별', 4, 1, '만개 cat4'),
  ('CATTYPE_SITUATION', 'RCP_CAT_TYPE', '레시피 분류 종류', 'SITUATION', '상황별', 4, 2, 'cat2'),
  ('CATTYPE_INGREDIENT', 'RCP_CAT_TYPE', '레시피 분류 종류', 'INGREDIENT', '재료별', 4, 3, 'cat3'),
  ('CATTYPE_METHOD', 'RCP_CAT_TYPE', '레시피 분류 종류', 'METHOD', '방법별', 4, 4, 'cat1'),
  ('REL_A', 'RELIABILITY', '수량 표기 신뢰도', 'A', 'A (정량 90% 이상)', 5, 1, NULL),
  ('REL_B', 'RELIABILITY', '수량 표기 신뢰도', 'B', 'B (70% 이상)', 5, 2, NULL),
  ('REL_C', 'RELIABILITY', '수량 표기 신뢰도', 'C', 'C (50% 이상)', 5, 3, NULL),
  ('REL_D', 'RELIABILITY', '수량 표기 신뢰도', 'D', 'D (50% 미만)', 5, 4, NULL),
  ('TAGKIND_WANT', 'TAG_KIND', '취향 태그 종류', 'WANT', '먹고 싶은 음식', 6, 1, NULL),
  ('TAGKIND_EXCLUDE', 'TAG_KIND', '취향 태그 종류', 'EXCLUDE', '제외할 음식', 6, 2, NULL),
  ('RULE_TASTE', 'TAG_RULE', '취향 태그 규칙', 'TASTE', '맛 표현', 7, 1, 'taste_id'),
  ('RULE_RECIPE_CATEGORY', 'TAG_RULE', '취향 태그 규칙', 'RECIPE_CATEGORY', '레시피 분류', 7, 2, 'category_id'),
  ('RULE_INGREDIENT', 'TAG_RULE', '취향 태그 규칙', 'INGREDIENT', '재료', 7, 3, 'ingredient_id'),
  ('RULE_INGREDIENT_CATEGORY', 'TAG_RULE', '취향 태그 규칙', 'INGREDIENT_CATEGORY', '재료 분류', 7, 4, 'category_id'),
  ('RULE_MENU', 'TAG_RULE', '취향 태그 규칙', 'MENU', '메뉴', 7, 5, 'menu_id'),
  ('RULE_CLUSTER', 'TAG_RULE', '취향 태그 규칙', 'CLUSTER', '메뉴 군집', 7, 6, 'cluster_id'),
  ('KWKIND_MENU', 'KEYWORD_KIND', '트렌드 키워드 종류', 'MENU', '메뉴', 8, 1, NULL),
  ('KWKIND_INGREDIENT', 'KEYWORD_KIND', '트렌드 키워드 종류', 'INGREDIENT', '재료', 8, 2, NULL),
  ('KWKIND_STYLE', 'KEYWORD_KIND', '트렌드 키워드 종류', 'STYLE', '스타일', 8, 3, '로제 · 마라 · 두바이'),
  ('KWKIND_QUERY', 'KEYWORD_KIND', '트렌드 키워드 종류', 'QUERY', '넓은 검색어', 8, 4, '먹방 · 요즘 유행 음식 (팀 공유 데이터)'),
  ('MATCH_SEARCH', 'MATCHED_BY', '영상 키워드 매칭', 'SEARCH', '검색 결과', 9, 1, NULL),
  ('MATCH_TITLE', 'MATCHED_BY', '영상 키워드 매칭', 'TITLE', '제목에 포함', 9, 2, NULL),
  ('TSRC_TITLE', 'TASTE_SOURCE', '맛 표현 출처', 'TITLE', '제목', 10, 1, NULL),
  ('TSRC_INTRO', 'TASTE_SOURCE', '맛 표현 출처', 'INTRO', '소개', 10, 2, NULL),
  ('TSRC_TAG', 'TASTE_SOURCE', '맛 표현 출처', 'TAG', '태그', 10, 3, NULL),
  ('TSRC_REVIEW', 'TASTE_SOURCE', '맛 표현 출처', 'REVIEW', '후기', 10, 4, NULL),
  ('BASIS_NETWORK', 'SUBST_BASIS', '대체 재료 근거', 'NETWORK', '재료 네트워크', 11, 1, '이웃 유사'),
  ('BASIS_REVIEW', 'SUBST_BASIS', '대체 재료 근거', 'REVIEW', '후기 언급', 11, 2, '"대신"'),
  ('BASIS_TREND', 'SUBST_BASIS', '대체 재료 근거', 'TREND', '관심도 변화', 11, 3, NULL),
  ('SRC_MANGAE', 'DATA_SOURCE', '데이터 출처', 'MANGAE', '만개의레시피', 12, 1, '크롤링'),
  ('SRC_KAMIS', 'DATA_SOURCE', '데이터 출처', 'KAMIS', 'KAMIS', 12, 2, 'API'),
  ('SRC_NUTR', 'DATA_SOURCE', '데이터 출처', 'NUTR', '식약처 영양성분', 12, 3, 'API'),
  ('SRC_YOUTUBE', 'DATA_SOURCE', '데이터 출처', 'YOUTUBE', 'YouTube', 12, 4, 'API'),
  ('SRC_MANUAL', 'DATA_SOURCE', '데이터 출처', 'MANUAL', '직접 입력', 12, 5, NULL),
  ('SRC_MART', 'DATA_SOURCE', '데이터 출처', 'MART', '분석 계산', 12, 6, NULL),
  ('SRC_FOODSAFETY', 'DATA_SOURCE', '데이터 출처', 'FOODSAFETY', '식약처 레시피', 12, 7, 'COOKRCP01 API'),
  ('SRC_KURLY', 'DATA_SOURCE', '데이터 출처', 'KURLY', '마켓컬리', 12, 8, '크롤링 (몽고 담당)'),
  ('SRC_TEAM', 'DATA_SOURCE', '데이터 출처', 'TEAM', '팀 공유 데이터', 12, 9, 'omm_team_data 묶음'),
  ('ETL_RUNNING', 'ETL_STATUS', '실행 상태', 'RUNNING', '실행 중', 13, 1, NULL),
  ('ETL_OK', 'ETL_STATUS', '실행 상태', 'OK', '성공', 13, 2, NULL),
  ('ETL_FAILED', 'ETL_STATUS', '실행 상태', 'FAILED', '실패', 13, 3, NULL),
  ('DISH_RICE', 'FS_DISH_TYPE', '식약처 요리 종류', 'RICE', '밥', 14, 1, NULL),
  ('DISH_SOUP', 'FS_DISH_TYPE', '식약처 요리 종류', 'SOUP', '국&찌개', 14, 2, NULL),
  ('DISH_SIDE', 'FS_DISH_TYPE', '식약처 요리 종류', 'SIDE', '반찬', 14, 3, NULL),
  ('DISH_ONEDISH', 'FS_DISH_TYPE', '식약처 요리 종류', 'ONEDISH', '일품', 14, 4, NULL),
  ('DISH_DESSERT', 'FS_DISH_TYPE', '식약처 요리 종류', 'DESSERT', '후식', 14, 5, NULL),
  ('DISH_ETC', 'FS_DISH_TYPE', '식약처 요리 종류', 'ETC', '기타', 14, 6, NULL),
  ('USER_ACTIVE', 'USER_STATUS', '회원 상태', 'ACTIVE', '사용 중', 15, 1, NULL),
  ('USER_DORMANT', 'USER_STATUS', '회원 상태', 'DORMANT', '휴면', 15, 2, NULL),
  ('USER_WITHDRAWN', 'USER_STATUS', '회원 상태', 'WITHDRAWN', '탈퇴', 15, 3, NULL),
  ('PSRC_KAMIS_RETAIL', 'PRICE_SOURCE', '가격 출처', 'KAMIS_RETAIL', 'KAMIS 소매', 16, 1, NULL),
  ('PSRC_CHAMGAGYEOK', 'PRICE_SOURCE', '가격 출처', 'CHAMGAGYEOK', '참가격 (한국소비자원)', 16, 2, '양념 · 가공식품'),
  ('PSRC_KAMIS_WHOLESALE', 'PRICE_SOURCE', '가격 출처', 'KAMIS_WHOLESALE', 'KAMIS 도매', 16, 3, '소매가 없을 때'),
  ('ORDER_CART', 'ORDER_STATUS', '주문 상태', 'CART', '장바구니', 17, 1, NULL),
  ('ORDER_PAID', 'ORDER_STATUS', '주문 상태', 'PAID', '결제 완료', 17, 2, NULL),
  ('ORDER_DELIVERED', 'ORDER_STATUS', '주문 상태', 'DELIVERED', '배송 완료', 17, 3, NULL),
  ('ORDER_CANCELED', 'ORDER_STATUS', '주문 상태', 'CANCELED', '취소', 17, 4, NULL)
ON CONFLICT (code_id) DO UPDATE SET code_nm = EXCLUDED.code_nm, group_nm = EXCLUDED.group_nm, sort = EXCLUDED.sort;

-- 외래키 (omm_menus ↔ omm_recipes 가 서로를 가리켜서 테이블을 모두 만든 뒤 한꺼번에 추가)
ALTER TABLE omm_ingredients ADD CONSTRAINT fk_omm_ingredients_category_id FOREIGN KEY (category_id) REFERENCES omm_ingredient_categories(category_id);
ALTER TABLE omm_ingredients ADD CONSTRAINT fk_omm_ingredients_nutr_food_cd FOREIGN KEY (nutr_food_cd) REFERENCES omm_nutrition_foods(food_cd) ON DELETE SET NULL;
ALTER TABLE omm_ingredient_aliases ADD CONSTRAINT fk_omm_ingredient_aliases_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_aliases ADD CONSTRAINT fk_omm_ingredient_aliases_source FOREIGN KEY (source) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_unit_conversions ADD CONSTRAINT fk_omm_unit_conversions_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_unit_conversions ADD CONSTRAINT fk_omm_unit_conversions_amount_class FOREIGN KEY (amount_class) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_filter_tags ADD CONSTRAINT fk_omm_filter_tags_kind FOREIGN KEY (kind) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_filter_tags ADD CONSTRAINT fk_omm_filter_tags_rule_type FOREIGN KEY (rule_type) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_menus ADD CONSTRAINT fk_omm_menus_rep_recipe_id FOREIGN KEY (rep_recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE SET NULL;
ALTER TABLE omm_recipes ADD CONSTRAINT fk_omm_recipes_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE SET NULL;
ALTER TABLE omm_recipes ADD CONSTRAINT fk_omm_recipes_difficulty FOREIGN KEY (difficulty) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_recipe_category_codes ADD CONSTRAINT fk_omm_recipe_category_codes_cat_type FOREIGN KEY (cat_type) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_recipe_categories ADD CONSTRAINT fk_omm_recipe_categories_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_recipe_categories ADD CONSTRAINT fk_omm_recipe_categories_category_id FOREIGN KEY (category_id) REFERENCES omm_recipe_category_codes(category_id);
ALTER TABLE omm_recipe_ingredients ADD CONSTRAINT fk_omm_recipe_ingredients_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_recipe_ingredients ADD CONSTRAINT fk_omm_recipe_ingredients_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id) ON DELETE SET NULL;
ALTER TABLE omm_recipe_ingredients ADD CONSTRAINT fk_omm_recipe_ingredients_amount_class FOREIGN KEY (amount_class) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_reviews ADD CONSTRAINT fk_omm_reviews_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_recipe_tags ADD CONSTRAINT fk_omm_recipe_tags_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_kamis_items ADD CONSTRAINT fk_omm_kamis_items_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id) ON DELETE SET NULL;
ALTER TABLE omm_kamis_prices ADD CONSTRAINT fk_omm_kamis_prices_se_cd FOREIGN KEY (se_cd) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_kamis_prices ADD CONSTRAINT fk_omm_kamis_prices_x1 FOREIGN KEY (item_cd, vrty_cd) REFERENCES omm_kamis_items(item_cd, vrty_cd);
ALTER TABLE omm_price_monthly ADD CONSTRAINT fk_omm_price_monthly_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_price_monthly ADD CONSTRAINT fk_omm_price_monthly_market_type FOREIGN KEY (market_type) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_price_monthly ADD CONSTRAINT fk_omm_price_monthly_price_source FOREIGN KEY (price_source) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_menu_nutrition ADD CONSTRAINT fk_omm_menu_nutrition_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_trend_keywords ADD CONSTRAINT fk_omm_trend_keywords_kind FOREIGN KEY (kind) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_trend_keywords ADD CONSTRAINT fk_omm_trend_keywords_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE SET NULL;
ALTER TABLE omm_trend_keywords ADD CONSTRAINT fk_omm_trend_keywords_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id) ON DELETE SET NULL;
ALTER TABLE omm_youtube_video_keywords ADD CONSTRAINT fk_omm_youtube_video_keywords_video_id FOREIGN KEY (video_id) REFERENCES omm_youtube_videos(video_id) ON DELETE CASCADE;
ALTER TABLE omm_youtube_video_keywords ADD CONSTRAINT fk_omm_youtube_video_keywords_keyword_id FOREIGN KEY (keyword_id) REFERENCES omm_trend_keywords(keyword_id);
ALTER TABLE omm_youtube_video_keywords ADD CONSTRAINT fk_omm_youtube_video_keywords_matched_by FOREIGN KEY (matched_by) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_fs_recipes ADD CONSTRAINT fk_omm_fs_recipes_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_fs_recipes ADD CONSTRAINT fk_omm_fs_recipes_dish_type FOREIGN KEY (dish_type) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_fs_recipe_ingredients ADD CONSTRAINT fk_omm_fs_recipe_ingredients_rcp_seq FOREIGN KEY (rcp_seq) REFERENCES omm_fs_recipes(rcp_seq);
ALTER TABLE omm_fs_recipe_ingredients ADD CONSTRAINT fk_omm_fs_recipe_ingredients_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_users ADD CONSTRAINT fk_omm_users_status FOREIGN KEY (status) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_user_preferences ADD CONSTRAINT fk_omm_user_preferences_user_id FOREIGN KEY (user_id) REFERENCES omm_users(user_id);
ALTER TABLE omm_user_preferences ADD CONSTRAINT fk_omm_user_preferences_tag_id FOREIGN KEY (tag_id) REFERENCES omm_filter_tags(tag_id);
ALTER TABLE omm_kurly_products ADD CONSTRAINT fk_omm_kurly_products_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_orders ADD CONSTRAINT fk_omm_orders_user_id FOREIGN KEY (user_id) REFERENCES omm_users(user_id);
ALTER TABLE omm_orders ADD CONSTRAINT fk_omm_orders_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_orders ADD CONSTRAINT fk_omm_orders_rcp_seq FOREIGN KEY (rcp_seq) REFERENCES omm_fs_recipes(rcp_seq);
ALTER TABLE omm_orders ADD CONSTRAINT fk_omm_orders_status FOREIGN KEY (status) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_order_items ADD CONSTRAINT fk_omm_order_items_order_id FOREIGN KEY (order_id) REFERENCES omm_orders(order_id);
ALTER TABLE omm_order_items ADD CONSTRAINT fk_omm_order_items_goods_no FOREIGN KEY (goods_no) REFERENCES omm_kurly_products(goods_no);
ALTER TABLE omm_order_items ADD CONSTRAINT fk_omm_order_items_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_recipe_metrics ADD CONSTRAINT fk_omm_recipe_metrics_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_recipe_metrics ADD CONSTRAINT fk_omm_recipe_metrics_reliability_grade FOREIGN KEY (reliability_grade) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_recipe_metrics ADD CONSTRAINT fk_omm_recipe_metrics_cluster_id FOREIGN KEY (cluster_id) REFERENCES omm_menu_clusters(cluster_id) ON DELETE SET NULL;
ALTER TABLE omm_recipe_tastes ADD CONSTRAINT fk_omm_recipe_tastes_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE CASCADE;
ALTER TABLE omm_recipe_tastes ADD CONSTRAINT fk_omm_recipe_tastes_taste_id FOREIGN KEY (taste_id) REFERENCES omm_taste_words(taste_id);
ALTER TABLE omm_recipe_tastes ADD CONSTRAINT fk_omm_recipe_tastes_source FOREIGN KEY (source) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_ingredient_interest_monthly ADD CONSTRAINT fk_omm_ingredient_interest_monthly_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_menu_interest_monthly ADD CONSTRAINT fk_omm_menu_interest_monthly_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_keyword_trend_monthly ADD CONSTRAINT fk_omm_keyword_trend_monthly_keyword_id FOREIGN KEY (keyword_id) REFERENCES omm_trend_keywords(keyword_id);
ALTER TABLE omm_price_interest_corr ADD CONSTRAINT fk_omm_price_interest_corr_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_network_nodes ADD CONSTRAINT fk_omm_ingredient_network_nodes_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_network_edges ADD CONSTRAINT fk_omm_ingredient_network_edges_ingredient_a FOREIGN KEY (ingredient_a) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_network_edges ADD CONSTRAINT fk_omm_ingredient_network_edges_ingredient_b FOREIGN KEY (ingredient_b) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_menu_similarities ADD CONSTRAINT fk_omm_menu_similarities_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_menu_similarities ADD CONSTRAINT fk_omm_menu_similarities_similar_menu_id FOREIGN KEY (similar_menu_id) REFERENCES omm_menus(menu_id) ON DELETE CASCADE;
ALTER TABLE omm_ingredient_substitutes ADD CONSTRAINT fk_omm_ingredient_substitutes_ingredient_id FOREIGN KEY (ingredient_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_substitutes ADD CONSTRAINT fk_omm_ingredient_substitutes_substitute_id FOREIGN KEY (substitute_id) REFERENCES omm_ingredients(ingredient_id);
ALTER TABLE omm_ingredient_substitutes ADD CONSTRAINT fk_omm_ingredient_substitutes_basis FOREIGN KEY (basis) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_etl_runs ADD CONSTRAINT fk_omm_etl_runs_source FOREIGN KEY (source) REFERENCES omm_common_codes(code_id);
ALTER TABLE omm_etl_runs ADD CONSTRAINT fk_omm_etl_runs_status FOREIGN KEY (status) REFERENCES omm_common_codes(code_id);

-- 자주 조인 · 검색하는 컬럼 인덱스
CREATE INDEX ix_recipe_categories_category ON omm_recipe_categories(category_id);
CREATE INDEX ix_ingredient_aliases_ingredient ON omm_ingredient_aliases(ingredient_id);
CREATE INDEX ix_reviews_body_trgm ON omm_reviews USING gin (body gin_trgm_ops);
CREATE INDEX ix_recipes_title_trgm ON omm_recipes USING gin (title gin_trgm_ops);
CREATE INDEX ix_youtube_video_keywords_keyword ON omm_youtube_video_keywords(keyword_id);
CREATE INDEX ix_menu_interest_ym ON omm_menu_interest_monthly(ym);
CREATE INDEX ix_ingredient_interest_ym ON omm_ingredient_interest_monthly(ym);

COMMIT;
