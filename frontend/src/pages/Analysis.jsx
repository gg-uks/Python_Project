// 데이터 분석 8가지 = 주피터 노트북 모양 (분석 요약 → In [n] 코드 → Out[n] pandas DataFrame · matplotlib 그림 → 분석 방법)
// 그림은 back1 이 report/charts_v4.py 의 chart1() ~ chart8() (pandas + matplotlib) 로 매일 그린 SVG · PNG
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State } from '../components/ui'
import DataFrame from '../components/DataFrame'
import { INSIGHT_TABS } from '../insights'

// 탭 정의는 보고서 차트와 같이 쓰려고 src/insights.js 로 옮김
const TABS = INSIGHT_TABS

// 탭마다 데이터 불러오기 (화면이 실제로 부르는 API) + 노트북에 보일 코드
const EXTRA = ['rating-cost', 'person', 'taste']
async function load(type) {
  if (EXTRA.includes(type)) return api.insightExtra()
  if (type === 'interest') {
    const [a, k] = await Promise.all([api.rawAnalysis('interest'), api.rawTrendKeywords().catch(() => ({ items: [] }))])
    return { ...a, keywords: k.items || [], keywordsYm: k.ym }
  }
  return api.rawAnalysis(type)
}
const URL_OF = { 'rating-cost': 'insight/extra', person: 'insight/extra', taste: 'insight/extra' }
const urlOf = t => URL_OF[t] || `analysis/${t}`

// [변수 이름, 행들, 불러오는 코드 한 줄, 설명]
function frames(type, r) {
  const L = {
    clusters: [['df', r.items, 'pd.DataFrame(res["items"])', '군집별 중심 조리시간 · 1인분 재료비 · 레시피 수'],
      ['df_points', r.points, 'pd.DataFrame(res["points"])', '군집에 쓴 레시피 표본 (조리시간 · 재료비 · 군집 번호)']],
    'rating-cost': [['df', r.ratingCost?.points, 'pd.DataFrame(res["ratingCost"]["points"])', '후기 3개 이상 · 가격 확인 60% 이상 레시피의 별점과 1인분 재료비']],
    person: [['df', r.person, 'pd.DataFrame(res["person"])', '사람 이름 포함 여부별 레시피 수 · 조회수 중앙값 · 평균 별점'],
      ['df_names', r.personNames, 'pd.DataFrame(res["personNames"])', '제목에 많이 나온 사람 이름']],
    taste: [['df', (r.taste || []).flatMap(t => t.items.map((name, k) => ({ taste: t.word, rank: k + 1, ingredient: name }))),
      'pd.DataFrame(res["taste"]).explode("items").rename(columns={"word": "taste", "items": "ingredient"})', '맛 표현별 특징 재료 (자주 쓰이는 정도 ÷ 전체 사용량^0.65 로 보정)']],
    interest: [['df', (r.items || []).flatMap(k => (k.series || []).map(s => ({ keyword: k.keyword, ...s }))),
      'pd.json_normalize(res["items"], record_path="series", meta=["keyword"])', '키워드별 월별 유튜브 영상 수 · 만개의레시피 레시피 수'],
      ['df_keywords', r.keywords, 'pd.DataFrame(requests.get(f"{API}/trends/keywords").json()["items"])', `이번 달(${r.keywordsYm || '-'}) 유튜브 쇼츠 키워드 (영상 수 · 조회수 합)`]],
    value: [['df', r.recipes?.length ? r.recipes : r.items, `pd.DataFrame(res["${r.recipes?.length ? 'recipes' : 'items'}"])`, '1,000원당 단백질 상위 레시피'],
      ['df_ingredients', r.recipes?.length ? r.items : null, 'pd.DataFrame(res["items"])', '재료별 1,000원당 단백질 · 열량']],
    network: [['df_nodes', r.items, 'pd.DataFrame(res["items"])', '노드 = 재료 (연결 수 · 매개 중심성 · 그룹)'],
      ['df_edges', r.edges, 'pd.DataFrame(res["edges"])', '엣지 = 같이 쓰인 재료 쌍 (공동 출현 수 · lift)']],
    measure: [['df', r.items, 'pd.DataFrame(res["items"])', '재료 줄 수량 표기 분류 (정량 · 개수 · 모호 · 없음)'],
      ['df_grades', r.grades, 'pd.DataFrame(res["grades"])', '신뢰도 등급별 레시피 수 · 평균 별점 · 평균 조회수'],
      ['df_vague', r.vague, 'pd.DataFrame(res["vague"])', '자주 쓰인 모호 표현']],
  }[type] || []
  return L.filter(([, rows]) => rows?.length)
}

const f1 = v => (v == null || Number.isNaN(+v) ? '-' : Number(v).toLocaleString(undefined, { maximumFractionDigits: 1 }))
const pct = (a, b) => (b ? `${((a / b) * 100).toFixed(1)}%` : '-')
const hasBatchim = w => { const c = (w || '').trim().slice(-1).charCodeAt(0); return c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 > 0 }
const PAIR = { '와': ['과', '와'], '과': ['과', '와'], '를': ['을', '를'], '을': ['을', '를'], '는': ['은', '는'], '은': ['은', '는'], '이': ['이', '가'], '가': ['이', '가'] }
const fixJosa = t => t.replace(/'([^']+)'(와|과|를|을|는|은|이|가)(?=[\s,.(])/g, (m, w, j) => `'${w}'${PAIR[j][hasBatchim(w) ? 0 : 1]}`)
const short = (t, n = 16) => { if (!t || t.length <= n) return t; const cut = t.slice(0, n); return cut.slice(0, cut.lastIndexOf(' ') > 6 ? cut.lastIndexOf(' ') : n) + '…' }
const strength = r => { const a = Math.abs(+r || 0); return a < 0.1 ? '거의 없는' : a < 0.3 ? '약한' : a < 0.5 ? '중간 정도의' : '강한' }
function corr(xs, ys) {
  const n = xs.length; if (n < 3) return null
  const mx = xs.reduce((a, b) => a + b, 0) / n, my = ys.reduce((a, b) => a + b, 0) / n
  let sxy = 0, sxx = 0, syy = 0
  for (let i = 0; i < n; i++) { sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; syy += (ys[i] - my) ** 2 }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : null
}

// 분석 요약 (데이터로 계산 · 보고서 말투)
function insights(type, r) {
  const L = []; let S = ''
  try {
    if (type === 'clusters') {
      const it = [...(r.items || [])].sort((a, b) => b.recipeCount - a.recipeCount)
      const tot = it.reduce((s, c) => s + c.recipeCount, 0)
      if (it[0]) S = `레시피는 조리시간과 1인분 재료비에 따라 4개 유형으로 구분되었으며, '${it[0].name}'이 ${pct(it[0].recipeCount, tot)}로 가장 많았습니다.`
      it.forEach(c => L.push(`${c.name}: 평균 ${f1(c.centerCookMin)}분 · 1인분 ${f1(c.centerCostWon)}원 (${f1(c.recipeCount)}개, ${pct(c.recipeCount, tot)})`))
      L.push('이 4개 유형을 메인 화면의 "지금 상황" 선택지(상황에 맞는 메뉴 추천 기준)로 사용했습니다.')
    } else if (type === 'rating-cost') {
      const rc = r.ratingCost || {}
      const pts = (rc.points || []).filter(p => p.costPerServing > 0 && p.rating != null)
      const rr = rc.r ?? corr(pts.map(p => Math.log(p.costPerServing)), pts.map(p => +p.rating))
      const costs = pts.map(p => p.costPerServing).sort((a, b) => a - b)
      const q1 = costs[Math.floor(costs.length * 0.25)]
      const cheapGood = pts.filter(p => p.costPerServing <= q1).sort((a, b) => b.rating - a.rating || b.reviewCount - a.reviewCount).slice(0, 3)
      if (rr == null) S = `분석 대상 ${f1(pts.length)}개의 별점이 대부분 같은 값(${pts[0]?.rating ?? '-'}점)이라 상관계수를 계산할 수 없었습니다. 후기가 더 쌓이면 다시 확인이 필요합니다.`
      else S = `별점과 1인분 재료비 사이에는 ${strength(rr)} 상관(r = ${rr.toFixed(2)})이 나타났습니다. ${Math.abs(rr) < 0.3 ? '재료비가 낮아도 별점이 높은 레시피가 많아, "저렴해도 만족도 높은 메뉴"를 추천할 근거가 됩니다.' : '재료비가 별점에 어느 정도 영향을 주는 것으로 판단됩니다.'}`
      L.push(`분석 대상: 후기 3개 이상 · 가격 확인 재료 60% 이상 레시피 ${f1(rc.n ?? pts.length)}개`)
      if (q1) L.push(`재료비 하위 25%(1인분 ${f1(q1)}원 이하) 레시피 중 별점 상위: ${cheapGood.map(p => `'${short(p.title, 12)}' ★${p.rating}`).join(', ')}`)
      L.push('이 결과를 근거로 "가성비" · "싼 재료 우선" 추천에서 별점이 높은 저렴한 레시피를 우선 보여 줬습니다.')
    } else if (type === 'person') {
      const y = (r.person || []).find(x => x.hasName), n = (r.person || []).find(x => !x.hasName)
      if (y && n) {
        const ratio = n.medianViews ? y.medianViews / n.medianViews : null
        S = `사람 이름이 포함된 레시피의 조회수 중앙값은 ${f1(y.medianViews)}회로, 이름이 없는 레시피(${f1(n.medianViews)}회)${ratio ? `의 ${ratio.toFixed(1)}배` : ''}였습니다. 평균 별점은 ${y.avgRating} vs ${n.avgRating}로 차이가 ${Math.abs(y.avgRating - n.avgRating) < 0.1 ? '거의 없었습니다' : '있었습니다'}.`
        L.push(`이름 포함 레시피 ${f1(y.n)}개 · 이름 없는 레시피 ${f1(n.n)}개를 비교했습니다.`)
      }
      if (r.personNames?.length) L.push(`제목에 많이 나온 이름: ${r.personNames.map(x => `${x.name}(${f1(x.n)})`).join(' · ')}`)
      if (y && n) {
        const more = y.medianViews > n.medianViews, d = y.avgRating - n.avgRating
        L.push(`${more ? '사람 이름은 조회수(관심)를 높이는 요인' : '사람 이름이 조회수를 높인다고 보기는 어려우며'}${Math.abs(d) < 0.1 ? ', 만족도(별점)와는 관계가 약한 것으로 판단됩니다.' : d < 0 ? ', 별점은 오히려 낮아 조회수와 만족도가 비례하지 않는 것으로 판단됩니다.' : ', 별점도 더 높게 나타났습니다.'}`)
      }
    } else if (type === 'taste') {
      const t = r.taste || []
      if (t.length) S = `맛 표현마다 특징 재료가 구분되었습니다 (${t.slice(0, 2).map(x => `${x.word}: ${x.items.slice(0, 2).join(' · ')}`).join(', ')}).`
      t.forEach(x => L.push(`${x.word}: ${x.items.join(', ')}`))
      L.push('"매콤한 거 먹고 싶어" 같은 문장이 들어오면 해당 맛 표현과 특징 재료가 들어간 메뉴를 추천하는 데 사용했습니다.')
    } else if (type === 'interest') {
      const tot = (r.items || []).map(k => ({ k: k.keyword, yt: (k.series || []).reduce((s, p) => s + (p.ytVideoCnt || 0), 0), rc: (k.series || []).reduce((s, p) => s + (p.recipeCnt || 0), 0), peak: [...(k.series || [])].sort((a, b) => b.ytVideoCnt - a.ytVideoCnt)[0] }))
        .sort((a, b) => b.yt - a.yt)
      const kw = [...(r.keywords || [])].sort((a, b) => (b.ytViewSum || 0) - (a.ytViewSum || 0))
      if (tot[0]) S = `최근 12개월 유튜브 쇼츠 영상 수는 '${tot[0].k}'${tot[1] ? ` · '${tot[1].k}'` : ''} 키워드가 가장 많았습니다.`
      if (tot[0]?.peak) L.push(`'${tot[0].k}'은 ${tot[0].peak.ym}에 ${f1(tot[0].peak.ytVideoCnt)}개로 가장 많았습니다.`)
      if (kw[0]) L.push(`이번 달 조회수 합 상위 키워드: ${kw.slice(0, 3).map(x => `'${x.keyword}' ${f1(Math.round((x.ytViewSum || 0) / 10000))}만 회`).join(', ')}`)
      const rc = [...tot].sort((a, b) => b.rc - a.rc)[0]
      if (rc) L.push(`만개의레시피 레시피 수는 '${rc.k}'이 ${f1(rc.rc)}개로 가장 많아, 영상 관심과 레시피 등록 순위가 일치하지 않았습니다.`)
      if (tot.length > 2 && tot[0].yt === tot[2].yt) L.push(`상위 키워드의 영상 수가 ${f1(tot[0].yt)}개로 같게 나타나, 수집 상한(키워드별 최대 건수)의 영향이 있는 것으로 보입니다.`)
    } else if (type === 'value') {
      const rs = r.recipes || []
      const costs = rs.map(x => x.costPerServing).filter(Boolean).sort((a, b) => a - b)
      if (rs[0]) S = `1,000원당 단백질은 ${rs.slice(0, 3).map(x => `'${short(x.title, 12)}'`).join(', ')} 순으로 높게 나타났습니다.`
      if (rs[0]) L.push(`1위는 '${short(rs[0].title, 22)}'로 1인분 ${f1(rs[0].costPerServing)}원, 1,000원당 단백질 ${f1(rs[0].proteinPer1000won)}g입니다.`)
      if (costs.length) L.push(`상위 ${rs.length}개 레시피의 1인분 재료비 중앙값은 ${f1(costs[Math.floor(costs.length / 2)])}원입니다.`)
      L.push(`가격은 공공데이터(KAMIS 소매 → 참가격 → KAMIS 도매 순), 영양은 식약처 식품영양성분 DB 기준이며 ${r.ym || '최근'} 시세라 매달 순위가 달라질 수 있습니다.`)
    } else if (type === 'network') {
      const n = [...(r.items || [])].sort((a, b) => b.degree - a.degree)
      const bt = [...(r.items || [])].sort((a, b) => b.betweenness - a.betweenness)
      const e = [...(r.edges || [])].sort((a, b) => b.coCount - a.coCount)[0]
      const byId = Object.fromEntries((r.items || []).map(x => [x.id, x.label]))
      const groups = new Set((r.items || []).map(x => x.communityId)).size
      if (n[0]) S = bt[0]?.id === n[0].id
        ? `'${n[0].label}'은 연결 중심성과 매개 중심성 모두 1위로, 대부분의 레시피에 공통으로 쓰이는 기본 재료로 확인되었습니다.`
        : `연결 중심성은 '${n[0].label}', 매개 중심성은 '${bt[0]?.label}'이 가장 높아, 두 재료가 레시피 전반에 공통으로 쓰이는 것으로 확인되었습니다.`
      if (n[0]) L.push(`'${n[0].label}'은 ${f1(n[0].degree)}개 재료와 함께 사용되었습니다${n[1] ? ` (2위 '${n[1].label}' ${f1(n[1].degree)}개)` : ''}.`)
      if (e) L.push(`가장 자주 함께 쓰인 조합은 '${byId[e.source]}' + '${byId[e.target]}'로 ${f1(e.coCount)}개 레시피, lift ${e.lift}입니다.`)
      L.push(`재료는 ${groups}개 그룹으로 나뉘었으며, 같은 그룹 재료끼리 한 레시피에 자주 함께 쓰였습니다.`)
    } else if (type === 'measure') {
      const it = r.items || []
      const vague = it.find(x => /VAGUE/.test(x.amountClass))
      const meas = it.find(x => /MEASURED/.test(x.amountClass))
      const g = Object.fromEntries((r.grades || []).map(x => [x.grade, x]))
      const totG = (r.grades || []).reduce((s, x) => s + x.cnt, 0)
      if (meas) S = `재료 줄의 ${meas.pct}%만 단위(g · ml · 큰술 · 컵)로 기재되어 있었고, "넉넉히 · 약간" 같은 모호 표현은 ${vague ? vague.pct : '-'}%였습니다.`
      if (g.A) L.push(`단위로 적힌 비율 90% 이상(A등급, 그대로 구현 가능한 레시피)은 ${f1(g.A.cnt)}개(${pct(g.A.cnt, totG)})입니다.`)
      if (g.D) L.push(`50% 미만(D등급, 신뢰도 낮음)은 ${f1(g.D.cnt)}개(${pct(g.D.cnt, totG)})입니다.`)
      if (r.vague?.[0]) L.push(`가장 많이 쓰인 모호 표현은 '${r.vague[0].expression}'(${f1(r.vague[0].cnt)}회)${r.vague[1] ? `, '${r.vague[1].expression}'(${f1(r.vague[1].cnt)}회)` : ''} 순입니다.`)
      if (g.A && g.D) L.push(`평균 별점은 A등급 ${g.A.avgRating}, D등급 ${g.D.avgRating}로 별점으로는 정확도를 구분하기 어려워, 레시피 상세에 신뢰도 등급을 따로 표시했습니다.`)
    }
  } catch (e) { L.push(`(요약 생성 오류: ${e.message})`) }
  return { summary: fixJosa(S), items: L.map(fixJosa) }
}

const METHOD = {
  clusters: ['조리시간과 1인분 재료비를 로그 변환 후 표준화하여 두 변수의 단위 차이를 맞췄습니다.',
    'K-means(k=4)로 군집화하고, 군집 중심의 조리시간 · 재료비를 기준으로 자취형 · 간편 고급형 · 주말 요리형 · 대접형으로 명명했습니다.'],
  'rating-cost': ['후기 3개 이상 · 가격이 확인된 재료 60% 이상 · 1인분 300원 이상인 레시피만 대상으로 했습니다.',
    '1인분 재료비(로그)와 평균 별점의 피어슨 상관계수를 구하고, 재료비 하위 25% 중 별점이 높은 레시피를 뽑았습니다.'],
  person: ['레시피 제목에서 사람 이름 사전(백종원 · 류수영 등)에 있는 이름을 찾아 포함 여부를 표시했습니다.',
    '포함 여부별로 조회수 중앙값(조회수는 치우침이 커서 평균 대신 중앙값)과 평균 별점을 비교했습니다.'],
  taste: ['레시피 제목 · 소개 · 후기에서 맛 표현(매콤 · 얼큰 · 칼칼 → 매운맛 등)을 찾아 맛 그룹으로 묶었습니다.',
    '맛 그룹별로 레시피에 들어간 재료를 집계하고, 마늘 · 대파처럼 어디에나 들어가는 재료가 상위에 오지 않도록 (그 맛에서의 사용 수 ÷ 전체 사용 수^0.65)로 보정했습니다.'],
  interest: ['YouTube Data API 로 음식 키워드 검색 결과의 쇼츠 영상 수 · 조회수를 월별로 수집했습니다.',
    '같은 키워드가 들어간 만개의레시피 월별 레시피 수와 비교하고, 최근 12개월 영상 수 합계로 순위를 매겼습니다.'],
  value: ['레시피 재료 사용량(g)에 공공데이터 가격(KAMIS 소매 · 참가격 · KAMIS 도매)을 곱해 1인분 재료비를 산출했습니다.',
    '식약처 식품영양성분 DB로 1인분 단백질 · 열량을 계산하고, 1,000원당 단백질 · 열량을 구해 분포를 비교했습니다.',
    '가격이 확인된 재료가 60% 미만이거나 1인분 1,000원 미만인 레시피는 값이 과대 추정될 수 있어 제외했습니다.'],
  network: ['같은 레시피에 함께 사용된 재료 쌍의 공동 출현 횟수와 lift(실제 공동 출현 ÷ 기대값)를 계산했습니다.',
    '사용 빈도 상위 150개 재료로 네트워크를 구성하고 연결 중심성(degree) · 매개 중심성(betweenness)을 산출, 커뮤니티 탐지로 재료 그룹을 나눴습니다.'],
  measure: ['레시피 재료 줄의 수량 표기를 정량(g · ml · 큰술 · 컵), 개수, 모호 표현(넉넉히 · 약간 · 적당히), 미기재로 분류했습니다.',
    '레시피별 정량 · 개수 비율로 A(90% 이상) ~ D(50% 미만) 신뢰도 등급을 부여하고, 등급별 레시피 수 · 평균 별점 · 조회수를 비교했습니다.'],
}
const SOURCE = {
  clusters: '데이터: 만개의레시피 레시피 · KAMIS 소매가', 'rating-cost': '데이터: 만개의레시피 별점 · 후기 · KAMIS 소매가',
  person: '데이터: 만개의레시피 제목 · 조회수 · 별점', taste: '데이터: 만개의레시피 제목 · 소개 · 후기 · 재료',
  interest: '데이터: YouTube Data API v3 · 만개의레시피', value: '데이터: KAMIS 소매 · 도매, 한국소비자원 참가격, 식약처 식품영양성분 DB',
  network: '데이터: 만개의레시피 레시피 재료', measure: '데이터: 만개의레시피 레시피 재료 수량 표기',
}

const KW = /^(def|for|in|if|elif|else|return|import|from|as|lambda|with|not|and|or|try|except|None|True|False|while|is)$/
function Py({ code }) {
  const out = []
  const re = /(#[^\n]*)|([rf]?"""[\s\S]*?"""|[rf]?'[^'\n]*'|[rf]?"[^"\n]*")|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)/g
  let last = 0, m, k = 0
  while ((m = re.exec(code))) {
    if (m.index > last) out.push(code.slice(last, m.index))
    const [t] = m
    if (m[1]) out.push(<span key={k++} className="py-c">{t}</span>)
    else if (m[2]) out.push(<span key={k++} className="py-s">{t}</span>)
    else if (m[3]) out.push(<span key={k++} className="py-n">{t}</span>)
    else if (KW.test(t)) out.push(<span key={k++} className="py-k">{t}</span>)
    else if (code[re.lastIndex] === '(') out.push(<span key={k++} className="py-f">{t}</span>)
    else out.push(t)
    last = re.lastIndex
  }
  out.push(code.slice(last))
  return <code>{out}</code>
}

function Cell({ n, code, children, md, collapsed }) {
  const [open, setOpen] = useState(!collapsed)
  if (md) return <div className="nb-cell nb-md"><div className="nb-prompt" /><div className="nb-body">{md}</div></div>
  const lines = code.split('\n')
  return (
    <div className="nb-cell">
      <div className="nb-in">
        <div className="nb-prompt in">In [{n}]:</div>
        <div className="nb-body">
          <pre className={`nb-code ${open ? '' : 'short'}`}><Py code={open ? code : lines.slice(0, 6).join('\n')} /></pre>
          {lines.length > 6 && <button type="button" className="nb-more" onClick={() => setOpen(!open)}>{open ? '코드 접기 ▲' : `코드 ${lines.length}줄 모두 보기 ▼`}</button>}
        </div>
      </div>
      {children && (
        <div className="nb-out">
          <div className="nb-prompt out">Out[{n}]:</div>
          <div className="nb-body">{children}</div>
        </div>
      )}
    </div>
  )
}

function Figures({ files, report }) {
  if (!report) return null
  if (!report.charts.length) return <div className="nb-note">아직 그린 그림이 없어요. 관리자 › 보고서 차트 탭에서 ‘다시 그리기’를 눌러 주세요.</div>
  const list = report.charts.filter(c => files.includes(c.file))
  if (!list.length) return <div className="nb-note">이 분석 그림이 아직 없어요. 보고서 차트 탭에서 ‘다시 그리기’를 한 번 눌러 주세요 (새 그림 추가됨).</div>
  return list.map(c => {
    const svg = api.reportUrl(c.svg || c.file.replace(/\.png$/, '.svg'), report.generatedAt)
    const png = api.reportUrl(c.file, report.generatedAt)
    return (
      <figure key={c.file} className="nb-fig">
        <img src={c.svg ? svg : png} alt={c.title} loading="lazy" onError={e => { if (e.currentTarget.src !== png) e.currentTarget.src = png }} />
        <figcaption>
          <span>{c.title} · {c.note}</span>
          <span className="nb-links">
            <a href={png} download={c.file}>PNG 저장</a>
            <a href={c.svg ? svg : png} target="_blank" rel="noreferrer">크게 보기</a>
            {c.file === '7_네트워크.png' && <a href={api.reportUrl('7_네트워크.html', report.generatedAt)} target="_blank" rel="noreferrer">마우스로 보는 네트워크</a>}
          </span>
        </figcaption>
      </figure>
    )
  })
}


export default function Analysis() {
  const [sp, setSp] = useSearchParams()
  const type = TABS.some(t => t[0] === sp.get('t')) ? sp.get('t') : 'clusters'
  const [run, setRun] = useState(0)
  const tab = TABS.find(t => t[0] === type)
  const { data, loading, error } = useApi(() => load(type), [type, run])
  const report = useApi(() => api.report().catch(() => null), [run])
  const src = useApi(() => api.reportSource(tab[3]).catch(() => null), [tab[3]])
  const fs = data ? frames(type, data) : []
  const ins = data ? insights(type, data) : { summary: '', items: [] }
  let n = 1
  return (
    <div className="nb">
      <div className="nb-top">
        <div className="nb-file" />
        <button type="button" className="nb-run" onClick={() => setRun(x => x + 1)}>▶ 모두 다시 실행</button>
      </div>
      <div className="nb-tabs" role="tablist">
        {TABS.map(([k, l]) => <button key={k} role="tab" aria-selected={k === type} className={k === type ? 'on' : ''} onClick={() => setSp({ ...Object.fromEntries(sp), t: k })}>{l}</button>)}
      </div>
      <div className="nb-sheet">
        <Cell md={<>
          <h2>{tab[1]}</h2><p>{tab[2]}</p>
          {(ins.summary || ins.items.length > 0) && (
            <div className="an-sec an-in-md">
              <h3>분석 요약</h3>
              {ins.summary && <p className="an-sum">{ins.summary}</p>}
              <ul className="an-ins">{ins.items.map(x => <li key={x}>{x}</li>)}</ul>
            </div>
          )}
        </>} />

        <Cell n={n++} code={`import pandas as pd\nimport numpy as np\nimport requests\nimport matplotlib.pyplot as plt\n\n# [0단계] 시각화 환경 및 한글 폰트 설정\n# ==============================================================================\nplt.rcParams["font.family"] = ["Noto Sans CJK KR", "Malgun Gothic"]\nplt.rcParams["axes.unicode_minus"] = False      # 음수 기호 깨짐 방지\n\nAPI = "http://192.168.0.224/api"      # OMM API (back1)`} />

        <State loading={loading} error={error}>
          {data && (fs.length ? fs.map(([name, rows, how, note], i) => (
            <Cell key={name} n={n++} code={`${i === 0 ? `# [1단계] 데이터 불러오기\n# ==============================================================================\nres = requests.get(f"{API}/${urlOf(type)}").json()\n` : ''}# ${note}\n${name} = ${how}\n${name}`}>
              <DataFrame rows={rows} />
            </Cell>
          )) : <Cell n={n++} code={`res = requests.get(f"{API}/${urlOf(type)}").json()`}><div className="df-empty">Empty DataFrame</div></Cell>)}
        </State>

        <Cell n={n++} collapsed code={`# [2단계] 분석 코드 — ${src.data?.file || 'report/analyses/'} (back1 에서 매일 18:30 자동 실행)\n# ==============================================================================\n${src.data?.code || ''}\n\n${tab[3]}()`}>
          <State loading={report.loading}><Figures files={tab[4]} report={report.data} /></State>
        </Cell>

        <Cell md={<div className="an-how">
          <b>분석 방법</b>
          <ol>{(METHOD[type] || []).map(x => <li key={x}>{x}</li>)}</ol>
          <p className="an-src">{SOURCE[type]}</p>
        </div>} />
        {report.data?.generatedAt && <p className="nb-foot">그림 그린 시각 {report.data.generatedAt}</p>}
      </div>
    </div>
  )
}
