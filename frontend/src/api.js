// API 명세서 경로 그대로. VITE_API_BASE 가 있으면 백엔드 호출, 없으면 public/mock-data.json 으로 같은 모양을 흉내 냄.
// VITE_API_BASE=/ 이면 같은 주소(vite 프록시 · HAProxy)로, http://… 이면 그 주소로 부름.
// 백엔드 응답은 adapt.js 에서 화면 모양으로 바꿈.
import * as A from './adapt'
const RAW_BASE = import.meta.env.VITE_API_BASE || ''
const USE_MOCK = !RAW_BASE
const BASE = RAW_BASE.replace(/\/+$/, '')

let tokenMemory = null
const store = {
  get(k) { try { return localStorage.getItem(k) } catch { return k === 'omm_token' ? tokenMemory : null } },
  set(k, v) { try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v) } catch { if (k === 'omm_token') tokenMemory = v } },
}
export const auth = {
  token: () => store.get('omm_token'),
  nickname: () => store.get('omm_nick'),
  isAdmin: () => store.get('omm_admin') === '1',
}

async function http(method, path, body) {
  const headers = { 'Content-Type': 'application/json' }
  const t = auth.token()
  if (t) headers.Authorization = `Bearer ${t}`
  const res = await fetch(BASE + path, { method, headers, body: body ? JSON.stringify(body) : undefined })
  if (!res.ok) {
    // FastAPI 에러는 {"detail": "메시지"} 또는 {"detail": [{msg, loc}, …]} (입력값 검사)
    const t = await res.text()
    let msg = t || res.statusText
    try { const d = JSON.parse(t).detail; msg = Array.isArray(d) ? d.map(e => e.msg).join(', ') : d || msg } catch {}
    if (res.status === 401 && t) store.set('omm_token', null)
    throw new Error(msg)
  }
  return res.status === 204 ? null : res.json()
}

// ───────── 예시 데이터 ─────────
let dataPromise
const data = () => (dataPromise ??= fetch('/mock-data.json').then(r => r.json()).then(prepare))
function prepare(D) {
  D.recipeById = Object.fromEntries(D.recipes.map(r => [r.id, r]))
  D.menuById = Object.fromEntries(D.menus.map(m => [m.id, m]))
  D.ingById = Object.fromEntries(D.ingredients.map(i => [i.id, i]))
  return D
}
const wait = v => new Promise(r => setTimeout(() => r(v), 120))
const latest = (D, id, market = 'MARKET_RETAIL') => (D.prices[id] || []).filter(p => p.m === market).at(-1)
function priceMove(D, id) {
  const ps = (D.prices[id] || []).filter(p => p.m === 'MARKET_RETAIL')
  if (ps.length < 2 || !ps.at(-2).p) return null
  return Math.round(((ps.at(-1).p - ps.at(-2).p) / ps.at(-2).p) * 1000) / 10
}
// 로그인한 사용자의 취향 (예시 데이터: 브라우저에 저장된 내 정보)
function myPrefs() {
  if (!auth.token()) return null
  try { return JSON.parse(store.get('omm_me') || 'null') } catch { return null }
}
// 빼고 싶은 재료가 들어간 레시피 거르기: 재료 번호가 같거나, 직접 입력한 글자가 재료 이름에 들어 있으면 제외
function excludeFilter(D, prefs) {
  const items = prefs?.excludeItems || []
  const tags = D.filterTags.filter(t => (prefs?.excludeTagIds || []).includes(t.tagId))
  if (!items.length && !tags.length) return null
  const ids = new Set([...items.filter(x => x.ingredientId).map(x => x.ingredientId), ...tags.filter(t => t.ruleType === 'RULE_INGREDIENT').map(t => t.ruleRefId)])
  const cats = new Set(tags.filter(t => t.ruleType === 'RULE_INGREDIENT_CATEGORY').map(t => t.categoryName))
  const words = items.map(x => x.name.replace(/\s/g, '')).filter(Boolean)
  const hit = l => ids.has(l.iid) || cats.has(D.ingById[l.iid]?.category) || words.some(w => (l.std || '').includes(w) || (l.raw || '').replace(/\s/g, '').includes(w))
  const test = r => !(D.recipeIngredients[r.id] || []).some(hit)
  return { test, names: [...tags.map(t => t.label), ...items.map(x => x.name)] }
}
const valueOk = r => r.pricedRatio >= 0.6 && r.costPerServing >= 1000   // 재료비가 너무 낮게 잡힌 레시피는 가성비 비교에서 뺌

const mock = {
  async 'GET /api/main'() {
    const D = await data()
    const ex = excludeFilter(D, myPrefs()), ok = r => !ex || ex.test(r)
    const moves = D.ingredients.filter(i => !i.seas && D.prices[i.id]).map(i => ({ ingredientId: i.id, name: i.name, pricePer100g: latest(D, i.id)?.p, changePct: priceMove(D, i.id) }))
      .filter(x => x.changePct != null && Math.abs(x.changePct) < 300)
      .filter((x, i, a) => a.findIndex(y => y.pricePer100g === x.pricePer100g && y.changePct === x.changePct) === i)   // 같은 시세를 쓰는 별칭 재료는 하나만
    return {
      latestYm: D.meta.latestYm, recipeTotal: D.meta.recipeTotal, menuTotal: D.meta.menuTotal,
      valueRecipes: D.recipes.filter(r => valueOk(r) && ok(r)).sort((a, b) => (b.proteinPer1000 ?? 0) - (a.proteinPer1000 ?? 0)).slice(0, 8),
      popularRecipes: D.recipes.filter(ok).slice(0, 8), excluded: ex?.names || [],
      trendingMenus: D.menus.filter(m => m.interestIndex != null && m.recipeCount >= 5).sort((a, b) => b.interestIndex - a.interestIndex || b.recipeCount - a.recipeCount).slice(0, 8),
      priceMovers: { up: [...moves].sort((a, b) => b.changePct - a.changePct).slice(0, 5), down: [...moves].sort((a, b) => a.changePct - b.changePct).slice(0, 5) },
    }
  },
  async 'GET /api/filter-tags'() { const D = await data(); return { tags: D.filterTags, situations: D.situations } },
  async 'GET /api/recipes'(p) {
    const D = await data()
    let rs = D.recipes
    const ex = p.prefs === 'off' ? null : excludeFilter(D, myPrefs())
    if (ex) rs = rs.filter(ex.test)
    if (p.q) { const q = p.q.trim(); rs = rs.filter(r => r.title.includes(q) || r.menu?.includes(q) || (D.recipeIngredients[r.id] || []).some(l => l.std === q)) }
    if (p.dishType) rs = rs.filter(r => r.dishType === p.dishType)
    if (p.situation) rs = rs.filter(r => (r.situations || []).includes(p.situation))
    if (p.maxMin) rs = rs.filter(r => r.cookMin && r.cookMin <= +p.maxMin)
    if (p.maxCost) rs = rs.filter(r => valueOk(r) && r.costPerServing <= +p.maxCost)
    const key = { views: r => -(r.views ?? 0), rating: r => -(r.rating ?? 0) * 1000 - r.reviewCount, cost: r => (valueOk(r) ? r.costPerServing : 1e9),
      value: r => (valueOk(r) ? -(r.proteinPer1000 ?? 0) : 1e9), time: r => r.cookMin ?? 1e9, recent: r => -new Date(r.registeredAt || 0) }[p.sort || 'views']
    rs = [...rs].sort((a, b) => key(a) - key(b))
    const size = +p.size || 20, page = +p.page || 1
    return { excluded: ex?.names || [], total: rs.length, page, size, items: rs.slice((page - 1) * size, page * size) }
  },
  async 'GET /api/recipes/:id'(_, id) {
    const D = await data(); const r = D.recipeById[id]; if (!r) throw new Error('레시피가 없어요')
    return { ...r, sourceUrl: `https://www.10000recipe.com/recipe/${id}`, ingredients: D.recipeIngredients[id] || [],
      nutrition: D.menuById[r.menuId] || null, tastes: D.tastes[id] || [], reviews: D.reviews[id] || [] }
  },
  async 'POST /api/recipes/by-ingredients'(_, __, body) {
    const D = await data(); const have = new Set(body.ingredientIds)
    return D.recipes.map(r => {
      const main = (D.recipeIngredients[r.id] || []).filter(l => l.iid && !l.seas)
      if (main.length < 2) return null
      const hit = main.filter(l => have.has(l.iid))
      return hit.length ? { ...r, haveRatio: hit.length / main.length, have: hit.map(l => l.std), missing: main.filter(l => !have.has(l.iid)).map(l => ({ name: l.std, cost: l.cost })) } : null
    }).filter(Boolean).sort((a, b) => b.haveRatio - a.haveRatio || a.missing.length - b.missing.length).slice(0, body.limit || 24)
  },
  async 'GET /api/menus/:id'(_, id) {
    const D = await data(); const m = D.menuById[id]; if (!m) throw new Error('메뉴가 없어요')
    const rs = D.recipes.filter(r => r.menuId === +id)
    const cl = rs.map(r => r.clusterId).filter(Boolean)
    const top = cl.sort((a, b) => cl.filter(x => x === b).length - cl.filter(x => x === a).length)[0]
    return { ...m, repRecipe: D.recipeById[m.repRecipeId] || rs[0] || null, recipes: rs.slice(0, 8), cluster: D.clusters.find(c => c.id === top) || null }
  },
  async 'GET /api/menus/:id/interest'(_, id) { const D = await data(); return D.menuInterest[id] || [] },
  async 'GET /api/menus/:id/similar'(_, id) { const D = await data(); return (D.similar[id] || []).map(s => ({ ...s, menu: D.menuById[s.id] })) },
  async 'GET /api/ingredients'(p) {
    const D = await data(); const q = (p.q || '').trim()
    return D.ingredients.filter(i => !q || i.name.includes(q)).slice(0, +p.limit || 30)
  },
  async 'GET /api/ingredients/:id'(_, id) { const D = await data(); const i = D.ingById[id]; if (!i) throw new Error('재료가 없어요'); return i },
  async 'GET /api/ingredients/:id/prices'(p, id) {
    const D = await data(); const m = p.market === 'wholesale' ? 'MARKET_WHOLESALE' : 'MARKET_RETAIL'
    return (D.prices[id] || []).filter(x => x.m === m).slice(-(+p.months || 15))
  },
  async 'GET /api/ingredients/:id/substitutes'(_, id) { const D = await data(); return (D.substitutes[id] || []).map(s => ({ ...s, pricePer100g: latest(D, s.id)?.p })) },
  async 'GET /api/ingredients/:id/pairings'(_, id) { const D = await data(); return (D.pairings[id] || []).map(s => ({ ...s, name: D.ingById[s.id]?.name || `#${s.id}` })) },
  async 'GET /api/trends/menus'() {
    const D = await data()
    return D.menus.filter(m => m.interestIndex != null && m.recipeCount >= 3).sort((a, b) => b.interestIndex - a.interestIndex).slice(0, 20)
  },
  async 'GET /api/trends/keywords'() { const D = await data(); return { keywords: D.keywords, videos: D.videos } },
  async 'GET /api/analysis/:type'(_, type) {
    const D = await data()
    const map = {
      value: () => D.recipes.filter(valueOk).sort((a, b) => (b.proteinPer1000 ?? 0) - (a.proteinPer1000 ?? 0)).slice(0, 15),
      clusters: () => D.clusters,
      network: () => ({ nodes: D.nodes, edges: D.edges }),
      similar: () => D.menus.slice(0, 12).map(m => ({ menu: m.name, list: (D.similar[m.id] || []).slice(0, 3) })),
      substitutes: () => Object.entries(D.substitutes).slice(0, 15).map(([id, l]) => ({ name: D.ingById[id]?.name, list: l.slice(0, 3) })).filter(x => x.name),
      'price-interest': () => D.corr,
      interest: () => D.menus.filter(m => m.interestIndex != null && m.recipeCount >= 5).sort((a, b) => b.interestIndex - a.interestIndex).slice(0, 15),
      measure: () => ({ measure: D.measure, reliability: D.reliability }),
    }
    return { type, items: map[type]?.() ?? [] }
  },
  async 'POST /api/auth/signup'(_, __, b) { if (!b.email || !b.password) throw new Error('이메일과 비밀번호를 넣어주세요'); return { userId: 1 } },
  async 'GET /api/auth/check-email'(p) { return { available: !!p.email && p.email !== 'admin@omm.kr' } },
  async 'POST /api/auth/login'(_, __, b) {
    if (!b.email || !b.password) throw new Error('이메일과 비밀번호를 넣어주세요')
    return { accessToken: 'mock-token', nickname: b.email.split('@')[0], admin: b.email.startsWith('admin') }
  },
  async 'POST /api/auth/logout'() { return null },
  async 'GET /api/users/me'() {
    let me = null; try { me = JSON.parse(store.get('omm_me') || 'null') } catch {}
    return me || { userId: 1, email: 'me@omm.kr', nickname: auth.nickname() || '옴뇸', householdSize: 2, wantTagIds: [], excludeTagIds: [], wantItems: [], excludeItems: [] }
  },
  async 'PUT /api/users/me'(_, __, b) { store.set('omm_me', JSON.stringify(b)); return b },
  async 'DELETE /api/users/me'() { store.set('omm_me', null); return null },
  // 먹은 기록 (예시 데이터: 이 브라우저에만 저장)
  async 'POST /api/users/me/meals'(_, __, b) {
    const D = await data(); const list = mockMeals(); const m = D.menus.find(x => x.id === b.menuId) || {}
    const row = { mealId: Date.now(), eatenOn: b.eatenOn || localDay(), mealType: b.mealType || null, mealTypeName: MEAL_NAMES[b.mealType] || null, servings: b.servings || 1, memo: b.memo || null,
      menuId: b.menuId ?? null, menuName: m.name || null, dishType: m.dishType || null, recipeId: b.recipeId ?? null, recipeTitle: null, imageUrl: null, kcal: m.kcal ?? null, proteinG: m.protein ?? null, sodiumMg: m.sodium ?? null, costWon: null }
    store.set('omm_meals', JSON.stringify([row, ...list])); return row
  },
  async 'GET /api/users/me/meals'() { const items = mockMeals(); return { total: items.length, items } },
  async 'DELETE /api/users/me/meals/:id'(_, id) { store.set('omm_meals', JSON.stringify(mockMeals().filter(m => String(m.mealId) !== id))); return null },
  async 'GET /api/users/me/meals/summary'(p) { return mockSummary(mockMeals(), p.week) },
  async 'GET /api/users/me/meals/recent-menus'() { return { days: 3, menuIds: [], items: [] } },
  async 'GET /api/admin/etl-runs'() { const D = await data(); return D.etlRuns },
  async 'GET /api/admin/codes'() { const D = await data(); return D.codes },
  async 'GET /api/admin/users'() {
    return [{ userId: 1, email: 'me@omm.kr', nickname: '옴뇸', status: 'USER_ACTIVE' }, { userId: 2, email: 'kim@omm.kr', nickname: '김요리', status: 'USER_ACTIVE' },
      { userId: 3, email: 'old@omm.kr', nickname: '휴면회원', status: 'USER_DORMANT' }]
  },
}

export const MEAL_NAMES = { MEAL_BREAKFAST: '아침', MEAL_LUNCH: '점심', MEAL_DINNER: '저녁', MEAL_SNACK: '간식' }
// 한국 날짜 (YYYY-MM-DD). toISOString 은 UTC 라 밤 9시 전에는 하루 밀림
export const localDay = (d = new Date()) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
function mockMeals() { try { return JSON.parse(store.get('omm_meals') || '[]') } catch { return [] } }
function mockSummary(rows, week) {
  const d = week ? new Date(week + 'T00:00') : new Date(); const st = new Date(d); st.setDate(d.getDate() - ((d.getDay() + 6) % 7))
  const days = [...Array(7)].map((_, i) => { const x = new Date(st); x.setDate(st.getDate() + i); return localDay(x) })
  const inWeek = rows.filter(r => days.includes(r.eatenOn)); const K = ['kcal', 'proteinG', 'sodiumMg', 'costWon']
  const sum = (it, k) => { const v = it.map(r => r[k] == null ? null : r[k] * r.servings).filter(v => v != null); return v.length ? Math.round(v.reduce((a, b) => a + b, 0)) : null }
  const total = Object.fromEntries(K.map(k => [k, sum(inWeek, k)])); const eaten = days.filter(x => inWeek.some(r => r.eatenOn === x)).length
  const mix = {}; inWeek.forEach(r => { mix[r.dishType || '기타'] = (mix[r.dishType || '기타'] || 0) + 1 })
  return { weekStart: days[0], weekEnd: days[6], count: inWeek.length, eatenDays: eaten, total, known: Object.fromEntries(K.map(k => [k, inWeek.filter(r => r[k] != null).length])),
    dailyAvg: Object.fromEntries(K.map(k => [k, total[k] != null && eaten ? total[k] / eaten : null])),
    days: days.map(x => { const it = inWeek.filter(r => r.eatenOn === x); return { date: x, count: it.length, ...Object.fromEntries(K.map(k => [k, sum(it, k)])) } }),
    dishMix: Object.entries(mix).sort((a, b) => b[1] - a[1]).map(([dishType, count]) => ({ dishType, count, pct: Math.round(1000 * count / inWeek.length) / 10 })), topMenus: [] }
}

// 최근 3일 안에 먹은 메뉴 (추천에서 맨 뒤로). 1분 동안 재사용, 기록을 바꾸면 비움
let recentCache = null
async function recentEaten() {
  if (USE_MOCK || !auth.token()) return ''
  if (!recentCache || Date.now() - recentCache.t > 60000)
    recentCache = { t: Date.now(), p: call('GET', '/api/users/me/meals/recent-menus', { days: 3 }).then(r => r.menuIds.join(','), () => '') }
  return recentCache.p
}

async function call(method, path, params = {}, body, adapt) {
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== '' && v != null)).toString()
  if (!USE_MOCK) {
    const res = await http(method, path + (qs ? `?${qs}` : ''), body)
    return adapt && res != null ? adapt(res) : res
  }
  for (const [k, fn] of Object.entries(mock)) {
    const [m, pat] = k.split(' ')
    if (m !== method) continue
    const re = new RegExp('^' + pat.replace(/:\w+/g, '([^/]+)') + '$')
    const hit = path.match(re)
    if (hit) return wait(await fn(params, hit[1], body))
  }
  throw new Error(`예시 데이터에 없는 API: ${method} ${path}`)
}

// 백엔드에서 받을 수 있는 레시피 조건만 넘김 (situation · recent 정렬은 아직 백엔드에 없음)
const SORTS = ['views', 'rating', 'cost', 'value', 'time']
const recipeParams = p => USE_MOCK ? p : { q: p.q, tags: p.tags, dishType: p.dishType, maxMin: p.maxMin, maxCost: p.maxCost, sort: SORTS.includes(p.sort) ? p.sort : undefined, page: p.page, size: p.size, prefs: p.prefs === 'off' ? 'off' : undefined }

// 로그인한 회원의 '빼고 싶은' 태그를 레시피 검색 tags 로 넘김 (백엔드 tag_conditions 가 제외 태그는 NOT 으로 처리)
let tagCache
async function excludeTags() {
  if (USE_MOCK || !auth.token()) return []
  try {
    const me = await api.me()
    if (!me.excludeTagIds?.length) return []
    tagCache ??= api.filterTags()
    const all = (await tagCache).tags
    return all.filter(t => me.excludeTagIds.includes(t.tagId))
  } catch { return [] }
}

export const api = {
  async main() {
    const d = await call('GET', '/api/main', {}, undefined, A.main)
    if (!USE_MOCK && d.popularRecipes.length < 9) {
      // 메인 응답에 인기 레시피가 없어서: 실시간 인기(Redis) → 모자라면 조회수 순으로 9개 채움
      const live = (await call('GET', '/api/popular/recipes', { days: 7, limit: 9 }, undefined, x => x.map(A.recipe)).catch(() => [])) || []
      const views = live.length < 9 ? (await api.recipes({ sort: 'views', size: 9, prefs: 'off' }).catch(() => ({ items: [] }))).items : []
      const seen = new Set()
      d.popularRecipes = [...live, ...views].filter(r => !seen.has(r.id) && seen.add(r.id)).slice(0, 9)
    }
    return d
  },
  filterTags: () => call('GET', '/api/filter-tags', {}, undefined, A.filterTags),
  async recipes(p) {
    if (USE_MOCK) return call('GET', '/api/recipes', p)
    const ex = p.prefs === 'off' ? [] : await excludeTags()
    const tags = [...(p.tags ? String(p.tags).split(',') : []), ...ex.map(t => t.tagId)].join(',')
    const r = await call('GET', '/api/recipes', { ...recipeParams(p), tags }, undefined, A.recipes)
    return { ...r, excluded: [...ex.map(t => t.label), ...(r.excluded || [])] }   // 칩 태그 + 백엔드가 뺀 직접 입력 재료
  },
  recipe: id => call('GET', `/api/recipes/${id}`, {}, undefined, A.recipeDetail),
  // 상황 문장 추천 (팀 POST /api/recommend/es = /text 문장 분석 + 엘라스틱서치 점수). ES 경로가 없거나 실패하면 /text
  async situation(text, excludeMenuIds = [], limit = 6) {
    const body = { text, excludeMenuIds, limit }
    try { return await call('POST', '/api/recommend/es', {}, body) } catch { return call('POST', '/api/recommend/text', {}, body) }
  },
  // 먹은 기록 기반 비슷한 메뉴 (로그인 · GET /api/recommend/similar)
  similarMenus: (limit = 6) => call('GET', '/api/recommend/similar', { limit }),
  // 엘라스틱서치 레시피 검색 · 메뉴 자동완성 (ES 가 멈추면 백엔드가 PostgreSQL 로 대신 찾음, engine = 'pg')
  searchRecipes: p => call('GET', '/api/search/recipes', { q: p.q, page: p.page, size: p.size }, undefined, A.recipes),
  suggest: q => call('GET', '/api/search/suggest', { q, limit: 8 }),
  byIngredients: (ingredientIds, limit = 24) => call('POST', '/api/recipes/by-ingredients', {}, { ingredientIds, limit }, A.byIngredients),
  async menu(id) {
    const m = await call('GET', `/api/menus/${id}`, {}, undefined, A.menuDetail)
    if (!USE_MOCK && !m.recipes.length && m.name) m.recipes = (await api.recipes({ q: m.name, size: 8 }).catch(() => ({ items: [] }))).items
    return m
  },
  menuInterest: id => call('GET', `/api/menus/${id}/interest`, { months: 12 }, undefined, A.interest),
  similar: id => call('GET', `/api/menus/${id}/similar`, { limit: 6 }, undefined, A.similar),
  // q 가 없으면 많이 쓰는 재료 (백엔드 v45c). 예전 백엔드면 422 → 빈 목록
  ingredients: (q, limit) => call('GET', '/api/ingredients', USE_MOCK ? { q, limit } : { q: q?.trim() || undefined }, undefined, A.ingredients).catch(e => (q?.trim() ? Promise.reject(e) : [])),
  async ingredient(id) {
    if (USE_MOCK) return call('GET', `/api/ingredients/${id}`)
    // 백엔드에 재료 1건 조회 API 가 아직 없어서, 없으면 번호만으로 화면을 그림
    return call('GET', `/api/ingredients/${id}`, {}, undefined, A.ingredient).catch(() => ({ id: +id, name: `재료 #${id}` }))
  },
  prices: (id, market) => call('GET', `/api/ingredients/${id}/prices`, { market, months: 15 }, undefined, A.prices),
  substitutes: id => call('GET', `/api/ingredients/${id}/substitutes`, {}, undefined, A.substitutes),
  pairings: id => call('GET', `/api/ingredients/${id}/pairings`, { limit: 10 }, undefined, A.pairings),
  trendMenus: () => call('GET', '/api/trends/menus', { limit: 12 }, undefined, A.trendMenus),
  trendKeywords: () => call('GET', '/api/trends/keywords', {}, undefined, A.trendKeywords),
  analysis: type => call('GET', `/api/analysis/${type}`, {}, undefined, x => A.analysis(type, x)),
  checkEmail: email => call('GET', '/api/auth/check-email', { email }),
  signup: b => call('POST', '/api/auth/signup', {}, b),
  async login(b) {
    const r = await call('POST', '/api/auth/login', {}, b, A.login)
    store.set('omm_token', r.accessToken); store.set('omm_nick', r.nickname)
    // 백엔드 로그인 응답에는 관리자 여부가 없어서, 관리자 API 를 한 번 불러 보고 판단 (403 이면 일반 회원)
    if (!USE_MOCK && r.admin == null) r.admin = await http('GET', '/api/admin/etl-runs?page=1').then(() => true, () => false)
    store.set('omm_admin', r.admin ? '1' : null)
    return r
  },
  async logout() { await call('POST', '/api/auth/logout').catch(() => {}); ['omm_token', 'omm_nick', 'omm_admin'].forEach(k => store.set(k, null)) },
  me: () => call('GET', '/api/users/me', {}, undefined, A.me),
  updateMe: b => call('PUT', '/api/users/me', {}, b),
  withdraw: () => call('DELETE', '/api/users/me'),
  etlRuns: () => call('GET', '/api/admin/etl-runs', {}, undefined, A.etlRuns),
  codes: () => call('GET', '/api/admin/codes', {}, undefined, A.codes),
  users: () => call('GET', '/api/admin/users', {}, undefined, A.users),
  // 적재 직후 · 코드 수정 뒤 화면에 예전 값이 남아 있을 때 (Redis 응답 캐시 삭제)
  // ── UI v3 (메뉴 추천 · 인사이트 · 재료 탐색 · 트렌드) ──
  situations: () => call('GET', '/api/situations'),
  recommend: async p => call('GET', '/api/recommend', { ...p, eaten: (await recentEaten()) || undefined }, undefined, x => ({ ...x, items: x.items.map(A.menu) })),
  // ── 먹은 기록 (v4.7) ──
  addMeal: b => { recentCache = null; return call('POST', '/api/users/me/meals', {}, b) },
  meals: (from, to) => call('GET', '/api/users/me/meals', { from, to }),
  deleteMeal: id => { recentCache = null; return call('DELETE', `/api/users/me/meals/${id}`) },
  mealSummary: week => call('GET', '/api/users/me/meals/summary', { week }),
  insight: () => call('GET', '/api/insight'),
  insightExtra: () => call('GET', '/api/insight/extra'),
  ingredientInsight: id => call('GET', `/api/ingredients/${id}/insight`),
  ingredientSummary: ids => call('GET', '/api/ingredients-summary', { ids: ids?.length ? ids.join(',') : undefined }),
  trendMenusBy: (order, limit = 6) => call('GET', '/api/trends/menus', { order, limit }, undefined, A.trendMenus),
  calendar: ids => call('GET', '/api/trends/calendar', { ids: ids?.length ? ids.join(',') : undefined }),
  recipeSteps: id => call('GET', `/api/recipes/${id}/steps`),
  rawAnalysis: type => call('GET', `/api/analysis/${type}`),
  rawTrendKeywords: () => call('GET', '/api/trends/keywords'),
  // matplotlib 보고서 차트 (back1 /api/report). 예시 데이터에서는 빈 목록
  report: () => (USE_MOCK ? Promise.resolve({ charts: [], generatedAt: null, running: false }) : call('GET', '/api/report')),
  reportUrl: (file, v) => `${BASE}/api/report/files/${encodeURIComponent(file)}${v ? `?v=${encodeURIComponent(v)}` : ''}`,
  refreshReport: () => call('POST', '/api/admin/report/refresh'),
  // 그 그림을 그린 실제 파이썬 코드 (report/charts_v4.py 의 함수 하나)
  reportSource: fn => (USE_MOCK ? Promise.resolve({ code: '# 예시 데이터에서는 코드를 볼 수 없어요' }) : call('GET', '/api/report/source', { fn })),
  clearCache: () => (USE_MOCK ? Promise.resolve(null) : call('DELETE', '/api/admin/cache')),
}
export const isMock = USE_MOCK
