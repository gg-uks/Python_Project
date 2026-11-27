-- OMM v4 마트 계산 (원본 → 분석 결과 테이블). 수집이 끝날 때마다 다시 실행해도 되게 DELETE 후 INSERT
-- 순서: ① 월별 시세 ② 레시피 분석값 ③ 대표 레시피 ④ 관심도 ⑤ 키워드 트렌드 ⑥ 맛 표현
-- 군집(분석 1) · 네트워크(분석 7) · 시차 상관 · 대체 재료는 Python(scikit-learn · networkx)으로 계산해서 넣음
BEGIN;
-- 적재가 매번 지우고 다시 넣어서 통계가 낡음 → 실행 계획이 틀어져 몇 분씩 걸리던 것 방지
SET LOCAL work_mem = '64MB';
ANALYZE omm_recipes, omm_recipe_ingredients, omm_reviews, omm_ingredients, omm_menus;

-- ① 재료 월별 시세: 대표 품종 일별 가격 → 월 평균, 평년(직전 5년 같은 달, 최고·최저 빼고 평균), 작년 대비
--   팀 공유 데이터로 넣은 시세(price_source 있음)는 그대로 두고, 자체 수집 KAMIS로 계산한 행(price_source NULL)만 다시 계산
DELETE FROM omm_price_monthly WHERE price_source IS NULL;
WITH m AS (
    SELECT k.ingredient_id, date_trunc('month', p.exmn_ymd)::date AS ym, p.se_cd,
           round(avg(p.price))::int AS avg_price, count(DISTINCT p.exmn_ymd) AS days,
           max(CASE WHEN k.unit_sz = 1 THEN k.unit ELSE trim_scale(k.unit_sz)::text || k.unit END) AS unit_label, max(k.grams_per_unit) AS gpu, max(k.unit_sz) AS usz
    FROM omm_kamis_prices p JOIN omm_kamis_items k USING (item_cd, vrty_cd)
    WHERE k.is_primary
    GROUP BY 1, 2, 3
), n AS (
    SELECT m.*,
           (SELECT CASE WHEN count(*) >= 5 THEN (sum(x.avg_price) - max(x.avg_price) - min(x.avg_price)) / (count(*) - 2)
                        ELSE avg(x.avg_price) END
            FROM m x WHERE x.ingredient_id = m.ingredient_id AND x.se_cd = m.se_cd
              AND extract(month FROM x.ym) = extract(month FROM m.ym)
              AND x.ym BETWEEN m.ym - interval '5 year' AND m.ym - interval '1 year') AS normal,
           (SELECT x.avg_price FROM m x WHERE x.ingredient_id = m.ingredient_id AND x.se_cd = m.se_cd
              AND x.ym = m.ym - interval '1 year') AS last_year
    FROM m
)
INSERT INTO omm_price_monthly (ingredient_id, ym, market_type, avg_price, unit_label, price_per_100g,
                           normal_price, vs_normal_pct, yoy_pct, day_count)
SELECT ingredient_id, ym, se_cd, avg_price, unit_label,
       round(avg_price / NULLIF(gpu, 0) * 100, 1),
       round(normal)::int,
       round((avg_price / NULLIF(normal, 0) - 1) * 100, 1),
       round((avg_price::numeric / NULLIF(last_year, 0) - 1) * 100, 1),
       days
FROM n
ON CONFLICT (ingredient_id, ym, market_type) DO NOTHING;

-- 4단계: 평년값이 빈 가격 행(몽고에서 온 KAMIS 등)에 평년값 · 평년 대비 채움
--   직전 1~5년 같은 달 중 있는 것만 평균 (PRICE_START=2019-11 + KAMIS --normal-years 5)
UPDATE omm_price_monthly p
   SET normal_price = n.np,
       vs_normal_pct = round((p.avg_price::numeric / NULLIF(n.np, 0) - 1) * 100, 1)
  FROM (SELECT c.ingredient_id, c.ym, c.market_type, round(avg(x.avg_price))::int AS np
          FROM omm_price_monthly c
          JOIN omm_price_monthly x
            ON x.ingredient_id = c.ingredient_id AND x.market_type = c.market_type AND x.unit_label = c.unit_label
           AND extract(month FROM x.ym) = extract(month FROM c.ym)
           AND x.ym BETWEEN c.ym - interval '5 year' AND c.ym - interval '1 year'
         WHERE c.normal_price IS NULL
         GROUP BY 1, 2, 3) n
 WHERE p.ingredient_id = n.ingredient_id AND p.ym = n.ym AND p.market_type = n.market_type;

-- 4단계: 밥 가격은 즉석밥이 아니라 집밥 기준(쌀 가격 × 0.43, 익히면 약 2.3배)
UPDATE omm_price_monthly b SET price_per_100g = round(s.price_per_100g * 0.43, 1)
  FROM omm_price_monthly s
 WHERE b.ingredient_id = (SELECT ingredient_id FROM omm_ingredients WHERE name = '밥')
   AND s.ingredient_id = (SELECT ingredient_id FROM omm_ingredients WHERE name = '쌀')
   AND s.ym = b.ym AND s.market_type = b.market_type AND s.price_per_100g IS NOT NULL;

-- 4단계: 가격을 빌려 쓰는 재료 (가격 출처에 이름이 없지만 같은 상품군인 것)
WITH b(dst, src) AS (VALUES ('묵은지', '김치'), ('참치캔', '참치'), ('대패삼겹살', '삼겹살'))
INSERT INTO omm_price_monthly (ingredient_id, ym, market_type, avg_price, unit_label, price_per_100g,
                               normal_price, vs_normal_pct, yoy_pct, day_count, price_source)
SELECT d.ingredient_id, p.ym, p.market_type, p.avg_price, p.unit_label, p.price_per_100g,
       p.normal_price, p.vs_normal_pct, p.yoy_pct, p.day_count, p.price_source
FROM b JOIN omm_ingredients d ON d.name = b.dst JOIN omm_ingredients s ON s.name = b.src
JOIN omm_price_monthly p ON p.ingredient_id = s.ingredient_id
ON CONFLICT (ingredient_id, ym, market_type) DO UPDATE SET
  avg_price = EXCLUDED.avg_price, unit_label = EXCLUDED.unit_label, price_per_100g = EXCLUDED.price_per_100g,
  normal_price = EXCLUDED.normal_price, vs_normal_pct = EXCLUDED.vs_normal_pct, yoy_pct = EXCLUDED.yoy_pct,
  day_count = EXCLUDED.day_count, price_source = EXCLUDED.price_source;

-- ② 레시피 분석값 (4단계: 인분당 주재료 1.5kg 넘으면 원문 인분 대신 주재료 ÷ 500g으로 나눔 — 원문 인분 오류 보정): 재료비 · 영양 · 신뢰도 · 사람 이름 · 최근 1년 후기
DELETE FROM omm_recipe_metrics WHERE true;
WITH base AS (SELECT max(ym) AS ym FROM omm_price_monthly WHERE market_type = 'MARKET_RETAIL'),
li AS (
    SELECT ri.recipe_id, ri.grams, ri.amount_class, i.is_seasoning, i.name AS ing_name, pm.price_per_100g, nf.*
    FROM omm_recipe_ingredients ri
    LEFT JOIN omm_ingredients i USING (ingredient_id)
    LEFT JOIN (SELECT DISTINCT ON (ingredient_id) ingredient_id, price_per_100g FROM omm_price_monthly   -- 4단계: 최근 3개월 중 가장 최근 가격
               WHERE market_type = 'MARKET_RETAIL' AND price_per_100g IS NOT NULL
                 AND ym BETWEEN (SELECT ym FROM base) - interval '3 months' AND (SELECT ym FROM base)
               ORDER BY ingredient_id, ym DESC) pm ON pm.ingredient_id = ri.ingredient_id
    LEFT JOIN omm_nutrition_foods nf ON nf.food_cd = i.nutr_food_cd
),
agg AS (
    SELECT recipe_id,
           round(sum(grams / 100 * price_per_100g) FILTER (WHERE NOT coalesce(is_seasoning, false)))::int AS cost,
           avg((price_per_100g IS NOT NULL AND grams IS NOT NULL)::int) FILTER (WHERE NOT coalesce(is_seasoning, false)) AS priced,
           sum(grams / 100 * energy_kcal) AS kcal, sum(grams / 100 * protein_g) AS protein, sum(grams / 100 * sodium_mg) AS sodium,
           avg((amount_class IN ('AMOUNT_MEASURED', 'AMOUNT_COUNTED'))::int) AS measured,
           count(*) FILTER (WHERE amount_class = 'AMOUNT_VAGUE') AS vague,
           sum(grams) FILTER (WHERE NOT coalesce(is_seasoning, false) AND ing_name NOT IN ('물', '얼음')) AS main_g   -- 4단계: 인분 추정용 주재료 총량
    FROM li GROUP BY recipe_id
),
names(person) AS (VALUES ('백종원'), ('류수영'), ('이연복'), ('김수미'), ('정호영'), ('최현석'), ('승우아빠'))   -- 실제로는 사람 이름 사전 테이블/파일로 관리
INSERT INTO omm_recipe_metrics (recipe_id, base_ym, est_cost_won, cost_per_serving, priced_ratio, kcal_per_serving,
                            protein_per_serving, sodium_per_serving, protein_per_1000won, kcal_per_1000won,
                            measured_ratio, vague_count, reliability_grade, person_name, reviews_1y)
SELECT r.recipe_id, (SELECT ym FROM base), a.cost,
       a.cost / NULLIF(CASE WHEN a.main_g / NULLIF(r.servings, 0) > 1500 THEN ceil(a.main_g / 500) ELSE r.servings END, 0), round(a.priced, 3),
       round(a.kcal / NULLIF(CASE WHEN a.main_g / NULLIF(r.servings, 0) > 1500 THEN ceil(a.main_g / 500) ELSE r.servings END, 0), 1), round(a.protein / NULLIF(CASE WHEN a.main_g / NULLIF(r.servings, 0) > 1500 THEN ceil(a.main_g / 500) ELSE r.servings END, 0), 1), round(a.sodium / NULLIF(CASE WHEN a.main_g / NULLIF(r.servings, 0) > 1500 THEN ceil(a.main_g / 500) ELSE r.servings END, 0), 1),
       CASE WHEN a.cost >= 100 THEN round(a.protein / a.cost * 1000, 2) END, CASE WHEN a.cost >= 100 THEN round(a.kcal / a.cost * 1000, 1) END,   -- 재료비 100원 미만은 효율이 튀어서 비움
       round(a.measured, 3), a.vague,
       CASE WHEN a.measured >= 0.9 THEN 'REL_A' WHEN a.measured >= 0.7 THEN 'REL_B' WHEN a.measured >= 0.5 THEN 'REL_C' ELSE 'REL_D' END,
       (SELECT person FROM names WHERE r.title LIKE '%' || person || '%' LIMIT 1),
       (SELECT count(*) FROM omm_reviews v WHERE v.recipe_id = r.recipe_id AND v.written_at > current_date - 365)
FROM omm_recipes r JOIN agg a USING (recipe_id);

-- ②-1 재료로 계산한 영양값이 없으면 메뉴 영양성분(식약처 음식 DB, 팀 공유 데이터)으로 채움
UPDATE omm_recipe_metrics rm SET
    kcal_per_serving = coalesce(rm.kcal_per_serving, mn.kcal_serving),
    protein_per_serving = coalesce(rm.protein_per_serving, mn.protein_g_serving),
    sodium_per_serving = coalesce(rm.sodium_per_serving, mn.sodium_mg_serving),
    protein_per_1000won = coalesce(rm.protein_per_1000won, CASE WHEN rm.cost_per_serving >= 100 THEN round(mn.protein_g_serving / rm.cost_per_serving * 1000, 2) END),
    kcal_per_1000won = coalesce(rm.kcal_per_1000won, CASE WHEN rm.cost_per_serving >= 100 THEN round(mn.kcal_serving / rm.cost_per_serving * 1000, 1) END)
FROM omm_recipes r JOIN omm_menu_nutrition mn USING (menu_id)
WHERE r.recipe_id = rm.recipe_id AND (rm.kcal_per_serving IS NULL OR rm.protein_per_serving IS NULL);

-- ③ 메뉴 대표 레시피 = 조회수 최다(동률: 후기 수 → 평점 → 최신 등록), 레시피 수
UPDATE omm_menus m SET recipe_count = s.cnt, rep_recipe_id = s.rep
FROM (SELECT r.menu_id, count(*) AS cnt,
             (array_agg(r.recipe_id ORDER BY r.view_count DESC NULLS LAST, r.review_count DESC NULLS LAST, r.avg_rating DESC NULLS LAST, r.registered_at DESC))[1] AS rep
      FROM omm_recipes r LEFT JOIN omm_recipe_metrics rm USING (recipe_id)
      WHERE r.menu_id IS NOT NULL GROUP BY r.menu_id) s
WHERE m.menu_id = s.menu_id;

-- ④ 관심도: 신규 레시피 + 후기 (재료 · 메뉴), YouTube 영상 수 (메뉴)
DELETE FROM omm_ingredient_interest_monthly;
WITH months AS (SELECT generate_series(date_trunc('month', (SELECT min(registered_at) FROM omm_recipes)),
                                       date_trunc('month', current_date), interval '1 month')::date AS ym),
ev AS (   -- 레시피 등록 1건, 후기 1건 = 관심 1
    SELECT recipe_id, date_trunc('month', registered_at)::date AS ym, 1 AS is_new, 0 AS is_rev FROM omm_recipes WHERE registered_at IS NOT NULL
    UNION ALL
    SELECT recipe_id, date_trunc('month', written_at)::date, 0, 1 FROM omm_reviews
),
c AS (
    SELECT ri.ingredient_id, ev.ym, sum(is_new) AS nr, sum(is_rev) AS rv
    FROM ev JOIN (SELECT DISTINCT recipe_id, ingredient_id FROM omm_recipe_ingredients WHERE ingredient_id IS NOT NULL) ri USING (recipe_id)
    GROUP BY 1, 2
),
g AS (
    SELECT i.ingredient_id, mo.ym, coalesce(c.nr, 0) AS nr, coalesce(c.rv, 0) AS rv
    FROM omm_ingredients i CROSS JOIN months mo LEFT JOIN c ON c.ingredient_id = i.ingredient_id AND c.ym = mo.ym
    WHERE NOT i.is_seasoning
)
INSERT INTO omm_ingredient_interest_monthly (ingredient_id, ym, new_recipe_cnt, review_cnt, interest_cnt, interest_index, yoy_pct)
SELECT ingredient_id, ym, nr, rv, nr + rv,
       round(100.0 * (nr + rv) / NULLIF(max(nr + rv) OVER w12, 0), 1),
       round(100.0 * ((nr + rv)::numeric / NULLIF(lag(nr + rv, 12) OVER (PARTITION BY ingredient_id ORDER BY ym), 0) - 1), 1)
FROM g
WINDOW w12 AS (PARTITION BY ingredient_id ORDER BY ym ROWS BETWEEN 11 PRECEDING AND CURRENT ROW);

DELETE FROM omm_menu_interest_monthly;
WITH months AS (SELECT generate_series(date_trunc('month', (SELECT min(registered_at) FROM omm_recipes)),
                                       date_trunc('month', current_date), interval '1 month')::date AS ym),
ev AS (
    SELECT r.menu_id, date_trunc('month', r.registered_at)::date AS ym, 1 AS is_new, 0 AS is_rev FROM omm_recipes r WHERE r.menu_id IS NOT NULL
    UNION ALL
    SELECT r.menu_id, date_trunc('month', v.written_at)::date, 0, 1 FROM omm_reviews v JOIN omm_recipes r USING (recipe_id) WHERE r.menu_id IS NOT NULL
),
yt AS (
    SELECT k.menu_id, date_trunc('month', y.published_at)::date AS ym, count(DISTINCT y.video_id) AS vc
    FROM omm_youtube_videos y JOIN omm_youtube_video_keywords vk USING (video_id) JOIN omm_trend_keywords k USING (keyword_id)
    WHERE k.menu_id IS NOT NULL GROUP BY 1, 2
),
c AS (   -- 메뉴 × 월 레시피 · 후기 수를 먼저 한 번만 집계 (예전: 칸마다 ev 전체를 두 번씩 다시 훑어서 데이터가 늘면 몇 분씩 걸림)
    SELECT menu_id, ym, sum(is_new) AS nr, sum(is_rev) AS rv FROM ev GROUP BY 1, 2
),
g AS (
    SELECT m.menu_id, mo.ym,
           coalesce(c.nr, 0) AS nr,
           coalesce(c.rv, 0) AS rv,
           coalesce(yt.vc, 0) AS vc
    FROM omm_menus m CROSS JOIN months mo
    LEFT JOIN c ON c.menu_id = m.menu_id AND c.ym = mo.ym
    LEFT JOIN yt ON yt.menu_id = m.menu_id AND yt.ym = mo.ym
)
INSERT INTO omm_menu_interest_monthly (menu_id, ym, new_recipe_cnt, review_cnt, yt_video_cnt, interest_cnt,
                                   interest_index, yt_index, yoy_pct, yt_yoy_pct)
SELECT menu_id, ym, nr, rv, vc, nr + rv,
       round(100.0 * (nr + rv) / NULLIF(max(nr + rv) OVER w12, 0), 1),
       round(100.0 * vc / NULLIF(max(vc) OVER w12, 0), 1),
       round(100.0 * ((nr + rv)::numeric / NULLIF(lag(nr + rv, 12) OVER p, 0) - 1), 1),
       round(100.0 * (vc::numeric / NULLIF(lag(vc, 12) OVER p, 0) - 1), 1)
FROM g
WINDOW w12 AS (PARTITION BY menu_id ORDER BY ym ROWS BETWEEN 11 PRECEDING AND CURRENT ROW),
       p AS (PARTITION BY menu_id ORDER BY ym);

-- ⑤ 키워드 트렌드 (분석 5)
DELETE FROM omm_keyword_trend_monthly;
WITH yt AS (
    SELECT vk.keyword_id, date_trunc('month', y.published_at)::date AS ym, count(*) AS vc, sum(coalesce(y.view_count, 0)) AS vs
    FROM omm_youtube_videos y JOIN omm_youtube_video_keywords vk USING (video_id) GROUP BY 1, 2
), rc AS (
    SELECT k.keyword_id, date_trunc('month', r.registered_at)::date AS ym, count(*) AS c
    FROM omm_trend_keywords k JOIN omm_recipes r ON replace(r.title, ' ', '') LIKE '%' || replace(k.keyword, ' ', '') || '%'
    WHERE r.registered_at IS NOT NULL GROUP BY 1, 2
), g AS (
    SELECT coalesce(yt.keyword_id, rc.keyword_id) AS keyword_id, coalesce(yt.ym, rc.ym) AS ym,
           coalesce(yt.vc, 0) AS vc, coalesce(yt.vs, 0) AS vs, coalesce(rc.c, 0) AS c
    FROM yt FULL JOIN rc ON rc.keyword_id = yt.keyword_id AND rc.ym = yt.ym
)
INSERT INTO omm_keyword_trend_monthly (keyword_id, ym, yt_video_cnt, yt_view_sum, recipe_cnt, yoy_pct)
SELECT g.keyword_id, g.ym, g.vc, g.vs, g.c,
       round(100.0 * (g.vc::numeric / NULLIF(p.vc, 0) - 1), 1)
FROM g LEFT JOIN g p ON p.keyword_id = g.keyword_id AND p.ym = g.ym - interval '1 year';

-- ⑥ 맛 표현 (분석 4): 제목 · 소개 · 후기에서 단순 포함 검색 (형태소 분석은 Python으로 바꿔도 됨)
DELETE FROM omm_recipe_tastes;
INSERT INTO omm_recipe_tastes (recipe_id, taste_id, source, mention_count)
SELECT r.recipe_id, t.taste_id, 'TSRC_TITLE', 1 FROM omm_recipes r JOIN omm_taste_words t ON r.title LIKE '%' || t.word || '%'
UNION ALL
SELECT r.recipe_id, t.taste_id, 'TSRC_INTRO', 1 FROM omm_recipes r JOIN omm_taste_words t ON r.intro LIKE '%' || t.word || '%'
UNION ALL
SELECT v.recipe_id, t.taste_id, 'TSRC_REVIEW', count(*) FROM omm_reviews v JOIN omm_taste_words t ON v.body LIKE '%' || t.word || '%'
GROUP BY 1, 2;

INSERT INTO omm_etl_runs (source, job, finished_at, status, message) VALUES ('SRC_MART', 'mart_build_v4', now(), 'ETL_OK', '마트 재계산');
COMMIT;
