-- 상황 문장 메뉴 추천 ("오늘 뭐 먹지" 워크북 방식을 OMM 데이터에 맞춤)
-- back1 에서 omm 계정으로 (또는 db1 에서 postgres 로) 한 번:
--   sudo bash -c 'set -a; . /opt/pipeline/normalizer/omm.env; set +a; psql -v ON_ERROR_STOP=1 -f recommend_schema.sql'
-- 여러 번 실행해도 안전 (IF NOT EXISTS · ON CONFLICT DO NOTHING). 만든 뒤 테이블 주인을 omm 으로 (다른 테이블과 같게).

BEGIN;

-- ── 1. 상황 태그: "해장", "매운맛", "국물" … ─────────────────────────────────
CREATE TABLE IF NOT EXISTS omm_situation_tags (
    sit_tag_id   SERIAL       PRIMARY KEY,
    name         VARCHAR(20)  NOT NULL UNIQUE,
    title        VARCHAR(50)  NOT NULL,
    avoid_share  NUMERIC(3,2) NOT NULL DEFAULT 0.50,
    sort_order   SMALLINT     NOT NULL DEFAULT 0,
    use_yn       CHAR(1)      NOT NULL DEFAULT 'Y' CHECK (use_yn IN ('Y', 'N'))
);
COMMENT ON TABLE  omm_situation_tags IS '상황 태그 - 문장에서 찾은 상황 · 맛 · 요리 형태 (해장, 매운맛, 국물 …)';
COMMENT ON COLUMN omm_situation_tags.title IS '추천 결과 제목 (속 풀어 주는 메뉴)';
COMMENT ON COLUMN omm_situation_tags.avoid_share IS '"싫어"로 피할 때: 메뉴 레시피 중 이 비율 이상이 태그에 맞으면 그 메뉴를 뺌';

-- ── 2. 태그 → 레시피 · 메뉴를 고르는 규칙 (태그 하나에 여러 줄, 하나라도 맞으면 그 태그) ──
CREATE TABLE IF NOT EXISTS omm_situation_targets (
    target_id    SERIAL       PRIMARY KEY,
    sit_tag_id   INT          NOT NULL REFERENCES omm_situation_tags (sit_tag_id) ON DELETE CASCADE,
    rule_type    VARCHAR(30)  NOT NULL CHECK (rule_type IN
                 ('RULE_RECIPE_CATEGORY', 'RULE_TASTE_GROUP', 'RULE_DISH_TYPE', 'RULE_INGREDIENT', 'RULE_TEXT', 'RULE_PROTEIN', 'RULE_COST')),
    ref_id       INT,
    ref_text     VARCHAR(200)
);
-- ref_id · ref_text 중 하나는 NULL 이라 보통 UNIQUE 로는 중복이 안 막힘 → NULL 을 값으로 바꿔 비교
CREATE UNIQUE INDEX IF NOT EXISTS uq_omm_situation_targets
    ON omm_situation_targets (sit_tag_id, rule_type, coalesce(ref_id, -1), coalesce(ref_text, ''));
COMMENT ON TABLE  omm_situation_targets IS '상황 태그 규칙 - 어떤 레시피가 이 태그인가';
COMMENT ON COLUMN omm_situation_targets.rule_type IS
  'RULE_RECIPE_CATEGORY 만개 상황 분류(ref_id) · RULE_TASTE_GROUP 후기 맛 묶음(ref_text) · RULE_DISH_TYPE 메뉴 요리 종류(ref_text) · '
  'RULE_INGREDIENT 재료(ref_id) · RULE_TEXT 제목·소개·해시태그 정규식(ref_text) · RULE_PROTEIN 1인분 단백질 g 이상(ref_id) · RULE_COST 1인분 재료비 원 이하(ref_id)';

-- ── 3. 키워드 → 태그 (문장에 이 말이 있으면 그 태그) ─────────────────────────────
CREATE TABLE IF NOT EXISTS omm_situation_keywords (
    keyword      VARCHAR(30)  NOT NULL,
    sit_tag_id   INT          NOT NULL REFERENCES omm_situation_tags (sit_tag_id) ON DELETE CASCADE,
    source       VARCHAR(10)  NOT NULL DEFAULT 'ADMIN' CHECK (source IN ('SEED', 'ADMIN')),
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT now(),
    PRIMARY KEY (keyword, sit_tag_id)
);
COMMENT ON TABLE  omm_situation_keywords IS '상황 키워드 사전 - 공백은 무시하고 비교 (술 마시 = 술마시). 관리자 API 로 추가 · 삭제';

-- ── 4. 식사 기록은 기존 omm_user_meals 를 씀 (주인 변경 · 권한은 user_meals_owner.sql, db1 postgres 로) ──

-- ── 5. 추천 기록 (관리자 통계: 많이 들어온 상황) ─────────────────────────────────
CREATE TABLE IF NOT EXISTS omm_recommend_logs (
    rec_log_id      BIGSERIAL    PRIMARY KEY,
    user_id         INT          REFERENCES omm_users (user_id),
    input_text      VARCHAR(300),
    tags            TEXT[]       NOT NULL DEFAULT '{}',
    avoid           TEXT[]       NOT NULL DEFAULT '{}',
    result_menu_ids INT[]        NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ  NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_omm_recommend_logs_created ON omm_recommend_logs (created_at);
COMMENT ON TABLE omm_recommend_logs IS '추천 기록 - 입력 문장, 찾은 태그, 피한 것, 보여 준 메뉴';

-- ── 6. 시작 사전 (워크북 태그 사전을 OMM 데이터에 맞춤) ─────────────────────────────
INSERT INTO omm_situation_tags (name, title, avoid_share, sort_order) VALUES
  ('해장',     '속 풀어 주는 메뉴',      0.50, 1),
  ('야식',     '출출한 밤에 좋은 메뉴',  0.20, 2),
  ('술안주',   '한잔할 때 좋은 안주',    0.30, 3),
  ('가볍게',   '가볍게 먹기 좋은 메뉴',  0.50, 4),
  ('손님상',   '손님상에 내기 좋은 메뉴', 0.50, 5),
  ('명절',     '명절에 어울리는 메뉴',   0.50, 6),
  ('도시락',   '도시락으로 싸기 좋은 메뉴', 0.50, 7),
  ('보양',     '기운 나는 보양 메뉴',    0.50, 8),
  ('간단하게', '금방 만드는 메뉴',       0.50, 9),
  ('간식',     '입이 심심할 때 간식',    0.50, 10),
  ('비오는날', '비 오는 날 생각나는 메뉴', 0.30, 11),
  ('따뜻하게', '몸 녹이는 따뜻한 메뉴',  0.50, 12),
  ('시원하게', '더위 식히는 시원한 메뉴', 0.50, 13),
  ('매운맛',   '매콤한 메뉴',           0.30, 20),
  ('국물',     '국물 있는 메뉴',        0.50, 21),
  ('담백',     '담백한 메뉴',           0.50, 22),
  ('달달',     '달달한 메뉴',           0.50, 23),
  ('고단백',   '단백질 든든한 메뉴',     0.50, 24),
  ('가성비',   '재료비 아끼는 메뉴',     0.50, 25)
ON CONFLICT (name) DO NOTHING;

-- 만개의레시피 "상황별" 분류 (이름이 데이터에 있는 것만 연결됨 → 맨 아래 확인 쿼리)
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_id)
SELECT t.sit_tag_id, 'RULE_RECIPE_CATEGORY', c.category_id
FROM (VALUES ('해장', '해장'), ('야식', '야식'), ('술안주', '술안주'), ('야식', '술안주'), ('가볍게', '다이어트'),
             ('손님상', '손님접대'), ('명절', '명절'), ('도시락', '도시락'), ('보양', '영양식'),
             ('간단하게', '초스피드'), ('간식', '간식')) v(tag, cat)
JOIN omm_situation_tags t ON t.name = v.tag
JOIN omm_recipe_category_codes c ON c.cat_type = 'CATTYPE_SITUATION' AND c.name = v.cat
ON CONFLICT DO NOTHING;

-- 후기 맛 묶음 (omm_taste_words.taste_group)
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_text)
SELECT t.sit_tag_id, 'RULE_TASTE_GROUP', v.g
FROM (VALUES ('매운맛', '매운맛'), ('담백', '담백함'), ('달달', '단맛'), ('국물', '국물'), ('해장', '국물')) v(tag, g)
JOIN omm_situation_tags t ON t.name = v.tag
ON CONFLICT DO NOTHING;

-- 메뉴 요리 종류 (omm_menus.dish_type)
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_text)
SELECT t.sit_tag_id, 'RULE_DISH_TYPE', v.d
FROM (VALUES ('국물', '국·찌개'), ('간식', '디저트·음료'), ('가볍게', '샐러드')) v(tag, d)
JOIN omm_situation_tags t ON t.name = v.tag
ON CONFLICT DO NOTHING;

-- 매운맛: 고추장 · 고춧가루 · 청양고추가 든 레시피 (워크북의 매운맛 비율과 같은 생각)
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_id)
SELECT t.sit_tag_id, 'RULE_INGREDIENT', i.ingredient_id
FROM omm_situation_tags t JOIN omm_ingredients i ON i.name IN ('고추장', '고춧가루', '청양고추')
WHERE t.name = '매운맛'
ON CONFLICT DO NOTHING;

-- 제목 · 소개 · 해시태그 글 (ES 없이 쓰는 대신 정규식)
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_text)
SELECT t.sit_tag_id, 'RULE_TEXT', v.re
FROM (VALUES ('비오는날', '비 ?오는 ?날|비 ?올 ?때|장마|비가 ?와'),
             ('따뜻하게', '따뜻한|뜨끈|겨울|추운 ?날|몸 ?녹'),
             ('시원하게', '시원한|여름|더운 ?날|냉국|차갑게'),
             ('보양',     '보양|몸보신|복날|기력'),
             ('해장',     '해장|숙취|속풀이')) v(tag, re)
JOIN omm_situation_tags t ON t.name = v.tag
ON CONFLICT DO NOTHING;

-- 영양 · 재료비 기준
INSERT INTO omm_situation_targets (sit_tag_id, rule_type, ref_id)
SELECT t.sit_tag_id, v.r, v.n
FROM (VALUES ('고단백', 'RULE_PROTEIN', 20), ('가성비', 'RULE_COST', 2000)) v(tag, r, n)
JOIN omm_situation_tags t ON t.name = v.tag
ON CONFLICT DO NOTHING;

-- 키워드 (공백 무시 비교. 레시피 글이 아니라 사용자 문장에서 찾음)
INSERT INTO omm_situation_keywords (keyword, sit_tag_id, source)
SELECT k, t.sit_tag_id, 'SEED'
FROM (VALUES
  ('해장', ARRAY['해장', '속풀이', '숙취', '속편한', '속이편', '회식', '술마신', '술마셔', '속이안좋', '속안좋', '속이불편', '속쓰', '더부룩', '과음', '전날술']),
  ('야식', ARRAY['야식', '출출', '밤에', '늦은밤', '새벽', '자기전']),
  ('술안주', ARRAY['안주', '술안주', '맥주', '소주', '술한잔', '와인', '막걸리', '혼술']),
  ('가볍게', ARRAY['다이어트', '저칼로리', '가볍게', '가벼운', '살빼', '살찔', '칼로리낮', '입맛없']),
  ('손님상', ARRAY['손님', '집들이', '홈파티', '파티', '기념일', '여럿이', '부모님', '초대']),
  ('명절', ARRAY['명절', '추석', '설날', '차례상', '제사']),
  ('도시락', ARRAY['도시락', '소풍', '나들이', '피크닉']),
  ('보양', ARRAY['보양', '몸보신', '복날', '초복', '중복', '말복', '기운없', '기운이없', '환절기', '감기', '으슬', '몸이안좋', '기력']),
  ('간단하게', ARRAY['간단', '간편', '빨리', '빠르게', '후다닥', '초간단', '귀찮', '시간없', '바빠']),
  ('간식', ARRAY['간식', '디저트', '입이심심', '주전부리', '군것질']),
  ('비오는날', ARRAY['비오는날', '비와', '비가와', '비가오', '비온', '장마']),
  ('따뜻하게', ARRAY['따뜻한', '따뜻하게', '뜨끈', '추워', '추운날', '쌀쌀', '으슬으슬', '겨울']),
  ('시원하게', ARRAY['시원한', '시원하게', '더워', '더운날', '더위', '여름']),
  ('매운맛', ARRAY['매운', '매콤', '맵', '화끈', '얼큰', '칼칼']),
  ('국물', ARRAY['국물', '찌개', '전골', '국밥', '탕']),
  ('담백', ARRAY['담백', '깔끔', '슴슴', '자극적이지']),
  ('달달', ARRAY['달달', '달콤', '단거', '단게', '당충전']),
  ('고단백', ARRAY['단백질', '고단백', '운동', '헬스', '벌크업']),
  ('가성비', ARRAY['가성비', '저렴', '알뜰', '싸게', '돈이없', '월급날', '아껴'])
) v(tag, ks)
CROSS JOIN LATERAL unnest(v.ks) AS k
JOIN omm_situation_tags t ON t.name = v.tag
ON CONFLICT DO NOTHING;

-- ── 7. API 계정 권한 ───────────────────────────────────────────────────────
GRANT SELECT ON omm_situation_tags, omm_situation_targets, omm_situation_keywords, omm_recommend_logs TO omm_api;
GRANT INSERT, DELETE ON omm_situation_keywords TO omm_api;
GRANT INSERT ON omm_recommend_logs TO omm_api;
GRANT USAGE ON SEQUENCE omm_recommend_logs_rec_log_id_seq TO omm_api;

-- 주인을 omm 으로 (omm 계정이 있을 때)
DO $$
DECLARE t text;
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omm') THEN
    FOREACH t IN ARRAY ARRAY['omm_situation_tags', 'omm_situation_targets', 'omm_situation_keywords', 'omm_recommend_logs'] LOOP
      EXECUTE format('ALTER TABLE %I OWNER TO omm', t);
    END LOOP;
  END IF;
END $$;

COMMIT;

-- 확인: 태그마다 규칙 · 키워드 수. 규칙 0 인 태그가 있으면 데이터에 그 분류 이름이 없는 것
SELECT t.name, count(DISTINCT g.target_id) AS rules, count(DISTINCT k.keyword) AS keywords
FROM omm_situation_tags t
LEFT JOIN omm_situation_targets g USING (sit_tag_id)
LEFT JOIN omm_situation_keywords k USING (sit_tag_id)
GROUP BY t.name, t.sort_order ORDER BY t.sort_order;

-- 데이터에 있는 만개 상황 분류 이름 (위 연결에 쓰인 이름과 다르면 알려 주세요)
SELECT c.name, count(*) AS recipes
FROM omm_recipe_category_codes c JOIN omm_recipe_categories rc USING (category_id)
WHERE c.cat_type = 'CATTYPE_SITUATION' GROUP BY c.name ORDER BY 2 DESC;
