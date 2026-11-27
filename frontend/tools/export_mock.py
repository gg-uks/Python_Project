"""PostgreSQL(omm) → 프론트 예시 데이터 src/mock/data.json (백엔드 없이 화면 개발용)"""
import json, os, sys, decimal, datetime, psycopg2, psycopg2.extras
conn = psycopg2.connect(host='localhost', user='postgres', password=os.getenv('PGPASSWORD', 'test'), dbname=sys.argv[1] if len(sys.argv) > 1 else 'omm_team')
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
def q(sql, *a):
    cur.execute(sql, a); return [dict(r) for r in cur.fetchall()]
def conv(o):
    if isinstance(o, decimal.Decimal): return float(o)
    if isinstance(o, (datetime.date, datetime.datetime)): return o.isoformat()[:10]
    raise TypeError(type(o))
D = {}
LATEST = q("select max(ym) m from omm_price_monthly")[0]['m']
D['meta'] = {'latestYm': LATEST.isoformat()[:7], 'recipeTotal': q("select count(*) c from omm_recipes")[0]['c'], 'menuTotal': q("select count(*) c from omm_menus")[0]['c']}
D["filterTags"] = q("""select t.tag_id "tagId", t.label, t.kind, t.rule_type "ruleType", t.rule_ref_id "ruleRefId",
  case when t.rule_type='RULE_INGREDIENT_CATEGORY' then (select name from omm_ingredient_categories where category_id=t.rule_ref_id) end "categoryName"
  from omm_filter_tags t order by kind desc, sort_order""")
D['situations'] = q("select category_id id, name from omm_recipe_category_codes where cat_type='CATTYPE_SITUATION' order by name")
# 레시피 (조회수 상위 + 가성비 상위)
ids = [r['recipe_id'] for r in q("""(select recipe_id from omm_recipes order by view_count desc nulls last limit 360)
  union (select recipe_id from omm_recipe_metrics where priced_ratio>=0.6 and cost_per_serving>=300 order by protein_per_1000won desc nulls last limit 120)
  union (select recipe_id from omm_reviews group by 1 order by count(*) desc limit 60)""")]
D['recipes'] = q("""select r.recipe_id id, r.title, r.menu_id "menuId", m.name menu, m.dish_type "dishType", r.servings, r.cook_time_min "cookMin",
  r.difficulty, r.view_count views, r.avg_rating rating, r.review_count "reviewCount", r.registered_at "registeredAt",
  rm.cost_per_serving "costPerServing", rm.est_cost_won "estCost", rm.priced_ratio "pricedRatio", rm.kcal_per_serving kcal, rm.protein_per_serving protein,
  rm.sodium_per_serving sodium, rm.protein_per_1000won "proteinPer1000", rm.reliability_grade reliability, rm.cluster_id "clusterId",
  (select array_agg(c.name) from omm_recipe_categories rc join omm_recipe_category_codes c using(category_id) where rc.recipe_id=r.recipe_id) situations
  from omm_recipes r left join omm_menus m using(menu_id) left join omm_recipe_metrics rm using(recipe_id) where r.recipe_id = any(%s) order by r.view_count desc""", ids)
pm = {r['ingredient_id']: r for r in q("""select ingredient_id, price_per_100g from omm_price_monthly where market_type='MARKET_RETAIL' and ym=%s""", LATEST)}
lines = q("""select ri.recipe_id rid, ri.seq, ri.group_name grp, ri.raw_name raw, ri.raw_amount amount, ri.ingredient_id iid, i.name std, i.is_seasoning seas, ri.grams
  from omm_recipe_ingredients ri left join omm_ingredients i using(ingredient_id) where ri.recipe_id = any(%s) order by ri.recipe_id, ri.seq""", ids)
ING = {}
for l in lines:
    p = pm.get(l['iid'])
    l['wonPer100g'] = float(p['price_per_100g']) if p and p['price_per_100g'] else None
    l['cost'] = round(l['wonPer100g'] * float(l['grams']) / 100) if l['wonPer100g'] and l['grams'] else None
    ING.setdefault(l.pop('rid'), []).append(l)
D['recipeIngredients'] = ING
REV = {}
for r in q("select recipe_id rid, rating stars, written_at \"writtenAt\", body text from omm_reviews where recipe_id = any(%s) order by written_at desc", ids):
    REV.setdefault(r.pop('rid'), []).append(r)
D['reviews'] = REV
TASTE = {}
for r in q("select t.recipe_id rid, w.word, t.mention_count n from omm_recipe_tastes t join omm_taste_words w using(taste_id) where recipe_id = any(%s) order by n desc", ids):
    TASTE.setdefault(r.pop('rid'), []).append(r['word'])
D['tastes'] = TASTE
# 메뉴
D['menus'] = q("""select m.menu_id id, m.name, m.dish_type "dishType", m.recipe_count "recipeCount", m.rep_recipe_id "repRecipeId",
  n.serving_g "servingG", n.kcal_serving kcal, n.protein_g_serving protein, n.sodium_mg_serving sodium, n.value_kind "valueKind",
  mi.interest_index "interestIndex", mi.yoy_pct "yoyPct", mi.yt_video_cnt "ytVideos"
  from omm_menus m left join omm_menu_nutrition n using(menu_id)
  left join omm_menu_interest_monthly mi on mi.menu_id=m.menu_id and mi.ym=(select max(ym) from omm_menu_interest_monthly)
  order by m.recipe_count desc""")
top = [m['id'] for m in D['menus'][:150]]
INT = {}
for r in q("select menu_id mid, to_char(ym,'YYYY-MM') ym, interest_index idx, new_recipe_cnt recipes, yt_video_cnt yt from omm_menu_interest_monthly where menu_id=any(%s) order by ym", top):
    INT.setdefault(r.pop('mid'), []).append(r)
D['menuInterest'] = INT
SIM = {}
for r in q("select s.menu_id mid, s.similar_menu_id id, t.name, s.score from omm_menu_similarities s join omm_menus t on t.menu_id=s.similar_menu_id where s.rank<=6 order by s.menu_id, s.rank"):
    SIM.setdefault(r.pop('mid'), []).append(r)
D['similar'] = SIM
D['clusters'] = q("select cluster_id id, name, description, center_cook_min \"cookMin\", center_cost_won \"costWon\", recipe_count \"recipeCount\" from omm_menu_clusters order by cluster_id")
# 재료
D['ingredients'] = q("""select i.ingredient_id id, i.name, c.name category, i.is_seasoning seas, i.recipe_count "recipeCount",
  p.price_per_100g "pricePer100g", p.unit_label unit, p.avg_price "avgPrice"
  from omm_ingredients i left join omm_ingredient_categories c using(category_id)
  left join omm_price_monthly p on p.ingredient_id=i.ingredient_id and p.market_type='MARKET_RETAIL' and p.ym=%s
  where i.recipe_count>=5 or p.price_per_100g is not null order by i.recipe_count desc""", LATEST)
PR = {}
for r in q("select ingredient_id iid, to_char(ym,'YYYY-MM') ym, market_type m, price_per_100g p, avg_price a, unit_label u, yoy_pct yoy from omm_price_monthly order by ym"):
    PR.setdefault(r.pop('iid'), []).append(r)
D['prices'] = PR
SUB = {}
for r in q("select s.ingredient_id iid, s.substitute_id id, b.name, s.dish_type \"dishType\", s.score, s.evidence_cnt n from omm_ingredient_substitutes s join omm_ingredients b on b.ingredient_id=s.substitute_id order by s.score desc"):
    if len(SUB.setdefault(r['iid'], [])) < 8: SUB[r.pop('iid')].append(r)
D['substitutes'] = SUB
PAIR = {}
for r in q("""select e.ingredient_a a, e.ingredient_b b, e.co_count n, e.lift from omm_ingredient_network_edges e order by e.co_count desc"""):
    for x, y in ((r['a'], r['b']), (r['b'], r['a'])):
        if len(PAIR.setdefault(x, [])) < 10: PAIR[x].append({'id': y, 'n': r['n'], 'lift': r['lift']})
D['pairings'] = PAIR
D['nodes'] = q("select n.ingredient_id id, i.name, n.degree, n.community_name community from omm_ingredient_network_nodes n join omm_ingredients i using(ingredient_id) order by degree desc limit 60")
D['edges'] = q("select ingredient_a a, ingredient_b b, co_count n from omm_ingredient_network_edges where ingredient_a=any(%s) and ingredient_b=any(%s) order by co_count desc limit 160", [n['id'] for n in D['nodes']], [n['id'] for n in D['nodes']])
D['corr'] = q("select i.name, c.lag_month lag, c.corr, c.n_months n from omm_price_interest_corr c join omm_ingredients i using(ingredient_id) order by abs(c.corr) desc limit 20")
D['keywords'] = q("""select k.keyword, k.kind, t.yt_video_cnt videos, t.yt_view_sum views, t.recipe_cnt recipes from omm_keyword_trend_monthly t join omm_trend_keywords k using(keyword_id)
  where t.ym=(select max(ym) from omm_keyword_trend_monthly) order by t.yt_view_sum desc nulls last limit 30""")
D['videos'] = q("select video_id id, title, published_at \"publishedAt\", view_count views, like_count likes from omm_youtube_videos order by view_count desc nulls last limit 40")
D['measure'] = q("select c.code_nm name, count(*) n from omm_recipe_ingredients ri join omm_common_codes c on c.code_id=ri.amount_class group by c.code_nm, c.sort order by c.sort")
D['reliability'] = q("select c.code_nm name, count(*) n from omm_recipe_metrics m join omm_common_codes c on c.code_id=m.reliability_grade group by c.code_nm, c.sort order by c.sort")
D['etlRuns'] = q("select run_id \"runId\", source, job, started_at \"startedAt\", status, row_count \"rowCount\", message from omm_etl_runs order by started_at desc limit 20")
D['codes'] = q("select code_id \"codeId\", group_code \"group\", group_nm \"groupNm\", code_nm \"name\", use_yn \"useYn\", sort from omm_common_codes order by group_sort, sort")
out = sys.argv[2] if len(sys.argv) > 2 else 'data.json'
json.dump(D, open(out, 'w'), ensure_ascii=False, default=conv, separators=(',', ':'))
print({k: len(v) for k, v in D.items() if hasattr(v, '__len__')}, os.path.getsize(out) // 1024, 'KB')
