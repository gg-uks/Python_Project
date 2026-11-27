-- OMM v4 화면 · 분석 쿼리. 예시 값(메뉴 1, 재료 7 배추, 2026-11)은 앱에서 파라미터로 바꿔 넣기
-- 실행: psql -d omm -f queries_v4.sql

-- ═════════════ 화면 쿼리 ═════════════

-- [화면 1] 취향 입력: 태그 칩 + 이번 주 재료 시세 (평년 대비 큰 순 4개)
SELECT kind, label FROM omm_filter_tags ORDER BY kind DESC, sort_order;

SELECT i.name, pm.vs_normal_pct
FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
ORDER BY abs(pm.vs_normal_pct) DESC NULLS LAST LIMIT 4;

-- [화면 2] 추천 메뉴: 원하는 태그(고기) 포함 · 제외 태그(오이 · 해산물) 빼기 · 균형 정렬
--   균형 점수 = 싼 재료 수 × 1 + 관심도 증가율 / 10  (추천 기준 버튼에 따라 가중치 변경)
WITH cur AS (SELECT max(ym) AS ym FROM omm_price_monthly),
rep AS (SELECT m.menu_id, m.name, m.rep_recipe_id FROM omm_menus m WHERE m.rep_recipe_id IS NOT NULL),
ing AS (
    SELECT rep.menu_id, i.ingredient_id, i.name, i.category_id, pm.vs_normal_pct
    FROM rep JOIN omm_recipe_ingredients ri ON ri.recipe_id = rep.rep_recipe_id
    JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
    LEFT JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT ym FROM cur)
),
excluded AS (   -- 제외 태그: 재료 / 재료 분류
    SELECT DISTINCT ing.menu_id FROM ing JOIN omm_filter_tags t ON t.kind = 'TAGKIND_EXCLUDE'
     AND ((t.rule_type = 'RULE_INGREDIENT' AND t.rule_ref_id = ing.ingredient_id)
       OR (t.rule_type = 'RULE_INGREDIENT_CATEGORY' AND t.rule_ref_id = ing.category_id))
),
wanted AS (     -- 원하는 태그 예: '고기' (재료 분류 2)
    SELECT DISTINCT ing.menu_id FROM ing JOIN omm_filter_tags t ON t.kind = 'TAGKIND_WANT' AND t.label IN ('고기')
     AND t.rule_type = 'RULE_INGREDIENT_CATEGORY' AND t.rule_ref_id = ing.category_id
)
SELECT r.name AS 메뉴, mi.yoy_pct AS 관심도_pct,
       string_agg(ing.name || ' ' || CASE WHEN ing.vs_normal_pct < 0 THEN '▼' ELSE '▲' END || abs(ing.vs_normal_pct) || '%', ', ')
           FILTER (WHERE abs(ing.vs_normal_pct) >= 5) AS 재료_배지,
       count(*) FILTER (WHERE ing.vs_normal_pct < 0) + coalesce(mi.yoy_pct, 0) / 10 AS 균형_점수
FROM rep r JOIN ing USING (menu_id)
LEFT JOIN omm_menu_interest_monthly mi ON mi.menu_id = r.menu_id AND mi.ym = (SELECT ym FROM cur)
WHERE r.menu_id IN (SELECT menu_id FROM wanted) AND r.menu_id NOT IN (SELECT menu_id FROM excluded)
GROUP BY r.menu_id, r.name, mi.yoy_pct
ORDER BY 균형_점수 DESC LIMIT 8;

-- [화면 3] 메뉴 상세 ① 대표 레시피
SELECT m.name AS 메뉴, r.title, r.servings, r.cook_time_min, r.difficulty, r.review_count, m.recipe_count,
       'https://www.10000recipe.com/recipe/' || r.recipe_id AS 원문_링크, mi.yoy_pct AS 관심도_pct
FROM omm_menus m JOIN omm_recipes r ON r.recipe_id = m.rep_recipe_id
LEFT JOIN omm_menu_interest_monthly mi ON mi.menu_id = m.menu_id AND mi.ym = date_trunc('month', current_date)
WHERE m.menu_id = 1;

-- [화면 3] ② 재료 · 오늘 시세 (양념은 칩으로 따로)
SELECT ri.group_name, ri.raw_name, ri.raw_amount, i.is_seasoning,
       pm.avg_price || '원 / ' || pm.unit_label AS 시세, pm.vs_normal_pct
FROM omm_menus m JOIN omm_recipe_ingredients ri ON ri.recipe_id = m.rep_recipe_id
LEFT JOIN omm_ingredients i USING (ingredient_id)
LEFT JOIN omm_price_monthly pm ON pm.ingredient_id = ri.ingredient_id AND pm.market_type = 'MARKET_RETAIL'
                          AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
WHERE m.menu_id = 1 ORDER BY ri.seq;

-- [화면 3] ③ 비싼 재료 대체 안내 (평년 +15% 이상 재료 → 대체 재료 중 지금 싼 것)
SELECT i.name AS 비싼_재료, pm.vs_normal_pct, s.name AS 대체, ps.vs_normal_pct AS 대체_등락, sub.basis
FROM omm_menus m JOIN omm_recipe_ingredients ri ON ri.recipe_id = m.rep_recipe_id
JOIN omm_ingredients i USING (ingredient_id)
JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
JOIN omm_ingredient_substitutes sub ON sub.ingredient_id = i.ingredient_id
JOIN omm_ingredients s ON s.ingredient_id = sub.substitute_id
LEFT JOIN omm_price_monthly ps ON ps.ingredient_id = s.ingredient_id AND ps.market_type = 'MARKET_RETAIL' AND ps.ym = pm.ym
WHERE m.menu_id = 1 AND pm.vs_normal_pct >= 15
ORDER BY pm.vs_normal_pct DESC, sub.score DESC;

-- [화면 3] ④ 비슷한 메뉴 · 같은 메뉴 다른 레시피 · 월별 차트
SELECT s.name FROM omm_menu_similarities ms JOIN omm_menus s ON s.menu_id = ms.similar_menu_id WHERE ms.menu_id = 1 ORDER BY ms.rank LIMIT 5;

SELECT r.title, rm.reviews_1y, r.cook_time_min
FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) JOIN omm_menus m USING (menu_id)
WHERE r.menu_id = 1 AND r.recipe_id <> m.rep_recipe_id ORDER BY rm.reviews_1y DESC LIMIT 4;

SELECT ym, interest_index, yt_index FROM omm_menu_interest_monthly
WHERE menu_id = 1 AND ym > date_trunc('month', current_date) - interval '12 month' ORDER BY ym;

-- [화면 4] 물가 × 요리 관심도: 산점도 (평년 대비 가격 vs 작년 대비 관심도) + 요약표
SELECT i.name, pm.avg_price, pm.unit_label, pm.vs_normal_pct AS 가격_평년대비, ii.yoy_pct AS 관심도_작년대비,
       (SELECT lag_month FROM omm_price_interest_corr c WHERE c.ingredient_id = i.ingredient_id ORDER BY c.corr LIMIT 1) AS 시차
FROM omm_price_monthly pm JOIN omm_ingredients i USING (ingredient_id)
LEFT JOIN omm_ingredient_interest_monthly ii ON ii.ingredient_id = pm.ingredient_id AND ii.ym = pm.ym
WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = '2026-11-01'
ORDER BY pm.vs_normal_pct DESC;

-- 전체 상관계수 r (화면 상단 카드)
SELECT round(corr(pm.vs_normal_pct, ii.yoy_pct)::numeric, 2) AS r, count(*) AS 재료_수
FROM omm_price_monthly pm JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
WHERE pm.market_type = 'MARKET_RETAIL' AND pm.ym = '2026-11-01';

-- [화면 5] 재료 탐색 (배추): 소매 · 도매 카드, 3년 흐름, 시차 상관, 들어가는 메뉴
SELECT market_type, avg_price, unit_label, vs_normal_pct FROM omm_price_monthly
WHERE ingredient_id = 7 AND ym = (SELECT max(ym) FROM omm_price_monthly);

SELECT pm.ym, pm.avg_price, ii.interest_cnt, ii.yt_video_cnt
FROM omm_price_monthly pm LEFT JOIN omm_ingredient_interest_monthly ii USING (ingredient_id, ym)
WHERE pm.ingredient_id = 7 AND pm.market_type = 'MARKET_RETAIL' AND pm.ym >= date_trunc('month', current_date) - interval '35 month'
ORDER BY pm.ym;

SELECT lag_month, corr FROM omm_price_interest_corr WHERE ingredient_id = 7 ORDER BY lag_month;

SELECT DISTINCT m.name, mi.yoy_pct
FROM omm_recipe_ingredients ri JOIN omm_menus m ON m.rep_recipe_id = ri.recipe_id
LEFT JOIN omm_menu_interest_monthly mi ON mi.menu_id = m.menu_id AND mi.ym = date_trunc('month', current_date)
WHERE ri.ingredient_id = 7 ORDER BY mi.yoy_pct;

-- [화면 6] 음식 트렌드: 뜨는 / 지는 메뉴 (작년 같은 달 대비), 계절 캘린더
SELECT m.name, m.dish_type, mi.yoy_pct, mi.yt_yoy_pct
FROM omm_menu_interest_monthly mi JOIN omm_menus m USING (menu_id)
WHERE mi.ym = date_trunc('month', current_date) AND mi.yoy_pct IS NOT NULL
ORDER BY mi.yoy_pct DESC;   -- 뜨는 메뉴 = 위에서, 지는 메뉴 = ASC

SELECT i.name, extract(month FROM ii.ym)::int AS 월, round(avg(ii.interest_index)) AS 지수,
       (SELECT extract(month FROM p.ym)::int FROM omm_price_monthly p WHERE p.ingredient_id = i.ingredient_id AND p.market_type = 'MARKET_RETAIL'
         GROUP BY 1 ORDER BY avg(p.normal_price) NULLS LAST, 1 LIMIT 1) AS 가장_싼_달
FROM omm_ingredient_interest_monthly ii JOIN omm_ingredients i USING (ingredient_id)
WHERE ii.ym >= date_trunc('month', current_date) - interval '36 month'
GROUP BY i.ingredient_id, i.name, 2 ORDER BY i.name, 2;


-- ═════════════ 분석 쿼리 (차트용 데이터) ═════════════

-- [분석 1] 군집: 조리시간 × 1인분 재료비 산점도 (cluster_id는 Python K-means 결과)
SELECT r.recipe_id, r.cook_time_min, rm.cost_per_serving, c.name AS 군집
FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) LEFT JOIN omm_menu_clusters c USING (cluster_id)
WHERE rm.priced_ratio >= 0.6;   -- 가격을 60% 이상 찾은 레시피만

-- [분석 2] 별점 vs 재료비 상관 + 저렴한데 만족도 높은 메뉴
SELECT round(corr(r.avg_rating, rm.cost_per_serving)::numeric, 3) AS r, count(*)
FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) WHERE r.review_count >= 5;

SELECT r.title, rm.cost_per_serving, r.avg_rating, r.review_count
FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id)
WHERE r.review_count >= 5
  AND rm.cost_per_serving <= (SELECT percentile_cont(0.25) WITHIN GROUP (ORDER BY cost_per_serving) FROM omm_recipe_metrics)
ORDER BY r.avg_rating DESC LIMIT 20;

-- [분석 3] 사람 이름 포함 여부별 조회수 · 별점
SELECT (rm.person_name IS NOT NULL) AS 사람이름, count(*), round(avg(r.view_count)) AS 평균_조회수,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY r.view_count) AS 중앙_조회수, round(avg(r.avg_rating), 2) AS 평균_별점
FROM omm_recipes r JOIN omm_recipe_metrics rm USING (recipe_id) GROUP BY 1;

-- [분석 4] 맛 묶음별 주요 재료 Top 10
SELECT t.taste_group, i.name, count(DISTINCT rt.recipe_id) AS 레시피_수
FROM omm_recipe_tastes rt JOIN omm_taste_words t USING (taste_id)
JOIN omm_recipe_ingredients ri USING (recipe_id) JOIN omm_ingredients i ON i.ingredient_id = ri.ingredient_id AND NOT i.is_seasoning
GROUP BY 1, 2 ORDER BY 1, 3 DESC;

-- [분석 5] 키워드 월별 YouTube 영상 수 vs 만개 레시피 수
SELECT k.keyword, kt.ym, kt.yt_video_cnt, kt.recipe_cnt, kt.yoy_pct
FROM omm_keyword_trend_monthly kt JOIN omm_trend_keywords k USING (keyword_id) ORDER BY k.keyword, kt.ym;

-- [분석 6] 재료 단위 영양 효율: 1,000원당 단백질 · 열량
SELECT i.name, pm.price_per_100g, nf.protein_g, nf.energy_kcal,
       round(nf.protein_g / pm.price_per_100g * 1000, 1) AS 단백질_g_per_1000원,
       round(nf.energy_kcal / pm.price_per_100g * 1000) AS kcal_per_1000원
FROM omm_ingredients i JOIN omm_nutrition_foods nf ON nf.food_cd = i.nutr_food_cd
JOIN omm_price_monthly pm ON pm.ingredient_id = i.ingredient_id AND pm.market_type = 'MARKET_RETAIL' AND pm.ym = (SELECT max(ym) FROM omm_price_monthly)
ORDER BY 5 DESC;

-- [분석 7] 네트워크: Gephi · pyvis로 내보낼 노드 / 엣지
SELECT n.ingredient_id AS id, i.name AS label, n.degree, n.betweenness, n.community_id
FROM omm_ingredient_network_nodes n JOIN omm_ingredients i USING (ingredient_id);
SELECT ingredient_a AS source, ingredient_b AS target, co_count, lift AS weight FROM omm_ingredient_network_edges WHERE lift > 1;

-- [분석 8] 수량 표기 신뢰도: 정량 / 개수 / 모호 / 없음 비율, 등급 분포, 등급별 별점
SELECT amount_class, count(*), round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct
FROM omm_recipe_ingredients GROUP BY 1 ORDER BY 2 DESC;

SELECT rm.reliability_grade, count(*), round(avg(r.avg_rating), 2) AS 평균_별점, round(avg(r.view_count)) AS 평균_조회수
FROM omm_recipe_metrics rm JOIN omm_recipes r USING (recipe_id) GROUP BY 1 ORDER BY 1;

SELECT unit AS 모호_표현, count(*) FROM omm_recipe_ingredients WHERE amount_class = 'AMOUNT_VAGUE' GROUP BY 1 ORDER BY 2 DESC;
