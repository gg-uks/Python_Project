// 백엔드(FastAPI, /api/docs) 응답 → 화면이 쓰는 모양으로 바꾸기.
// 백엔드 이름(recipeId, kcalPerServing …)은 그대로 두고, 화면 이름(id, kcal …)을 덧붙임.
// 백엔드에 아직 없는 값은 비워 두고 화면은 '-' 로 보여줌 (README 의 '백엔드에 요청할 것' 참고).

const arr = x => (Array.isArray(x) ? x : x?.items || [])
const rel = g => (g && !String(g).startsWith('REL_') ? `REL_${g}` : g)

export function recipe(x) {
  if (!x) return x
  const mt = x.metrics || {}
  const cost = x.costPerServing ?? mt.costPerServing
  const priced = x.pricedRatio ?? mt.pricedRatio
  return {
    ...x,
    id: x.recipeId ?? x.id,
    costPerServing: cost,
    // 목록에는 pricedRatio 가 없어서, 1인분 1,000원 이상일 때만 재료비를 믿고 보여줌
    pricedRatio: priced ?? (cost >= 1000 ? 1 : 0),
    estCost: x.estCost ?? mt.estCostWon,
    reliability: rel(x.reliability ?? mt.reliability),
    kcal: x.kcal ?? x.kcalPerServing ?? x.nutrition?.kcal,
    proteinPer1000: x.proteinPer1000 ?? x.proteinPer1000won,
    reviewCount: x.reviewCount ?? 0,
  }
}

export function recipeDetail(x) {
  const r = recipe(x)
  const n = x.nutrition || {}
  return {
    ...r,
    nutrition: x.nutrition ? { ...n, kcal: n.kcal, protein: n.protein ?? n.proteinG, sodium: n.sodium ?? n.sodiumMg } : null,
    ingredients: (x.ingredients || []).map((l, i) => ({
      ...l,
      seq: l.seq ?? i,
      grp: l.group,
      raw: l.rawName ?? l.raw,
      amount: l.amount ?? l.raw,
      iid: l.iid ?? l.ingredientId ?? null,
      std: l.std ?? l.name,
      seas: l.seas ?? l.isSeasoning ?? /양념|소스|드레싱/.test(l.group || ''),
    })),
    tastes: x.tastes || [],
    reviews: x.reviews || [],
  }
}

export function menu(x) {
  if (!x) return x
  const n = x.nutrition || {}
  return {
    ...x,
    id: x.menuId ?? x.id,
    servingG: x.servingG ?? n.servingG,
    kcal: x.kcal ?? n.kcal,
    protein: x.protein ?? n.proteinG,
    sodium: x.sodium ?? n.sodiumMg,
    interestIndex: x.interestIndex ?? x.interest?.interestIndex,
    yoyPct: x.yoyPct ?? x.interest?.yoyPct,
    ytVideos: x.ytVideos ?? x.ytVideoCnt,
  }
}

const cluster = c => c && ({ ...c, id: c.clusterId ?? c.id, cookMin: c.cookMin ?? c.centerCookMin, costWon: c.costWon ?? c.centerCostWon })

export function menuDetail(x) {
  return {
    ...menu(x),
    cluster: cluster(x.cluster),
    repRecipe: x.repRecipe ? recipe(x.repRecipe) : x.repRecipeId ? { id: x.repRecipeId, title: x.repTitle } : null,
    recipes: (x.recipes || []).map(recipe),
  }
}

export const main = x => ({
  ...x,
  latestYm: x.latestYm ?? x.priceMonth ?? x.trendMonth,
  valueRecipes: arr(x.valueRecipes).map(recipe),
  popularRecipes: arr(x.popularRecipes).map(recipe),
  trendingMenus: arr(x.trendingMenus).map(menu),
  priceMovers: {
    up: arr(x.priceMovers?.up).map(mover),
    down: arr(x.priceMovers?.down).map(mover),
  },
  excluded: x.excluded || [],
})
// 백엔드는 평년 대비(vsNormalPct)로 오른 · 내린 재료를 고름
const mover = m => ({ ...m, changePct: m.changePct ?? m.vsNormalPct ?? m.yoyPct })

export const filterTags = x => (Array.isArray(x) ? { tags: x, situations: [] } : { tags: x.tags || [], situations: x.situations || [] })

export const recipes = x => ({ ...x, items: arr(x).map(recipe), excluded: x.excluded || [], total: x.total ?? arr(x).length, size: x.size || 20 })

export const byIngredients = x => arr(x).map(r => ({
  ...recipe(r),
  missing: (r.missing || []).map(m => (typeof m === 'string' ? { name: m } : { ...m, name: m.name, cost: m.cost ?? m.costWon })),
}))

export const ingredient = x => ({ ...x, id: x.ingredientId ?? x.id, seas: x.seas ?? x.isSeasoning ?? false })
export const ingredients = x => arr(x).map(ingredient)
export const interest = x => arr(x).map(p => ({ ...p, idx: p.idx ?? p.interestIndex }))
export const similar = x => arr(x).map(s => ({ ...s, id: s.menuId ?? s.id, menu: menu(s) }))
export const prices = x => arr(x).map(p => ({ ...p, p: p.p ?? p.pricePer100g, yoy: p.yoy ?? p.yoyPct }))
export const substitutes = x => arr(x).map(s => ({ ...s, id: s.ingredientId ?? s.id, dishType: s.dishType || s.basisName || '전체', n: s.n ?? s.evidenceCnt }))
export const pairings = x => arr(x).map(s => ({ ...s, id: s.ingredientId ?? s.id, n: s.n ?? s.coCount }))
export const trendMenus = x => arr(x).map(menu)
export const trendKeywords = x => ({
  keywords: arr(x.keywords ?? x).map(k => ({ ...k, views: k.views ?? k.ytViewSum, videos: k.videos ?? k.ytVideoCnt, recipes: k.recipes ?? k.recipeCnt })),
  videos: x.videos || [],
})

// 분석 탭: 백엔드 items → 각 탭 차트가 쓰는 모양
function groupTop(items, key, name, subName) {
  const g = new Map()
  for (const it of items) {
    if (!g.has(it[key])) g.set(it[key], { name: it[name], list: [] })
    g.get(it[key]).list.push({ name: it[subName], score: it.score })
  }
  return [...g.values()].map(v => ({ ...v, list: v.list.sort((a, b) => b.score - a.score) })).slice(0, 15)
}
export function analysis(type, x) {
  const items = x.items || []
  const map = {
    // 백엔드 분석 6 은 재료 기준 (재료 1,000원당 단백질)
    // 레시피 기준(recipes)이 있으면 그걸, 없으면 재료 기준(items) 을 막대로
    value: () => (x.recipes?.length ? x.recipes : items).map(v => (v.recipeId ? recipe(v) : { ...v, title: v.title ?? v.name, proteinPer1000: v.proteinPer1000 ?? v.proteinPer1000won })),
    clusters: () => items.map(cluster),
    network: () => {
      const nodes = [...items].sort((a, b) => (b.degree ?? 0) - (a.degree ?? 0)).slice(0, 60)
        .map(n => ({ ...n, name: n.name ?? n.label, community: n.community ?? n.communityId }))
      const ids = new Set(nodes.map(n => n.id))
      const edges = (x.edges || []).filter(e => ids.has(e.source) && ids.has(e.target))
        .map(e => ({ a: e.source, b: e.target, n: e.coCount })).sort((a, b) => b.n - a.n).slice(0, 160)
      return { nodes, edges }
    },
    similar: () => groupTop(items, 'menuId', 'name', 'similarName').map(v => ({ menu: v.name, list: v.list })),
    substitutes: () => groupTop(items, 'ingredientId', 'name', 'substituteName'),
    // 재료별 값(items)이 비면 전체 재료 시차 상관(lags)만
    // 백엔드 items 는 재료별 '평년 대비 가격 · 작년 대비 관심'이라 시차 상관이 없음 → 전체 재료 시차 상관(lags)을 막대로
    'price-interest': () => (items.length && items[0].corr !== undefined ? items : (x.lags || []).map(l => ({ ...l, name: '전체 재료' })))
      .map(c => ({ ...c, name: c.name ?? c.ingredientName, lag: c.lag ?? c.lagMonth, corr: c.corr ?? 0 })),
    // 백엔드 분석 5: 키워드별 최근 12개월 YouTube 영상 수 → 합계로 막대
    interest: () => items.map(k => ({
      ...k, name: k.name ?? k.keyword,
      interestIndex: k.interestIndex ?? (k.series || []).reduce((s, p) => s + (p.ytVideoCnt || 0), 0),
    })).sort((a, b) => b.interestIndex - a.interestIndex),
    measure: () => ({
      measure: items.map(m => ({ name: m.name ?? m.amountClass, n: m.n ?? m.cnt })),
      reliability: (x.grades || []).map(g => ({ name: g.grade, n: g.cnt })),
    }),
  }
  return { ...x, type, raw: x, items: map[type] ? map[type]() : items }   // raw: DataFrame 보기용 원본
}

export const login = x => ({
  ...x,
  accessToken: x.accessToken ?? x.access_token ?? x.token,
  admin: x.admin ?? x.isAdmin ?? (x.role ? /ADMIN/i.test(x.role) : undefined),
})
export const me = x => ({ wantTagIds: [], excludeTagIds: [], wantItems: [], excludeItems: [], ...x })
export const etlRuns = x => arr(x)
export const codes = x => arr(x).map(c => ({ ...c, group: c.group ?? c.groupCode, groupNm: c.groupNm ?? c.groupName ?? c.group, name: c.name ?? c.codeNm }))
export const users = x => arr(x)
