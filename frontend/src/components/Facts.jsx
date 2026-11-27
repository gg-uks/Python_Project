// 분석 결과를 화면 곳곳에 자연스럽게 (잡코리아의 "이 공고 지원자 통계" 박스처럼)
// 8가지 분석 → 레시피 상세 · 레시피 목록 · 메인 · 냉장고 털기 · 재료 탐색에 나눠서 보여 줌
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { num, won, costOk } from './ui'

// 한 번만 불러서 모든 화면이 같이 씀
let cache = null
function loadFacts() {
  if (!cache) {
    const safe = p => p.catch(() => null)
    cache = Promise.all([safe(api.insightExtra()), safe(api.rawAnalysis('clusters')), safe(api.rawAnalysis('network')), safe(api.rawAnalysis('measure'))])
      .then(([extra, clusters, network, measure]) => {
        const pts = (extra?.ratingCost?.points || []).map(p => +p.costPerServing).filter(x => x > 0).sort((a, b) => a - b)
        const person = extra?.person || []
        const named = person.find(p => p.hasName), plain = person.find(p => !p.hasName)
        const grades = measure?.grades || []
        const gTot = grades.reduce((s, g) => s + g.cnt, 0)
        const label = Object.fromEntries((network?.items || []).map(n => [n.id, n.label]))
        return {
          taste: extra?.taste || [],
          names: (extra?.personNames || []).map(x => x.name),
          viewsRatio: named && plain && plain.medianViews ? named.medianViews / plain.medianViews : null,
          named, plain,
          // 표본이 30개 미만이면 하위 25% 값이 불안정 → 1,000원으로
          cheapLine: pts.length >= 30 ? pts[Math.floor(pts.length * 0.25)] : 1000,
          clusters: clusters?.items || [],
          edges: (network?.edges || []).map(e => ({ ...e, a: label[e.source], b: label[e.target] })),
          gradeShare: Object.fromEntries(grades.map(g => [g.grade, gTot ? g.cnt / gTot : null])),
        }
      })
      .catch(() => { cache = null; return null })
  }
  return cache
}
export function useFacts() {
  const [f, setF] = useState(null)
  useEffect(() => { let on = true; loadFacts().then(x => on && setF(x)); return () => { on = false } }, [])
  return f
}

// ① 조리시간 · 재료비로 가장 가까운 군집 (로그 거리)
export function clusterOf(f, r) {
  if (!f?.clusters.length || !r?.cookMin || !(r.costPerServing > 0)) return null
  const d = c => (Math.log(r.cookMin) - Math.log(c.centerCookMin || 1)) ** 2 + (Math.log(r.costPerServing) - Math.log(c.centerCostWon || 1)) ** 2
  return [...f.clusters].sort((a, b) => d(a) - d(b))[0]
}
export const personIn = (f, title) => (f?.names || []).find(n => (title || '').includes(n))
// ② 재료비 하위 25%(표본 적으면 1,000원 이하) + 별점 4.8 이상 + 후기 2개 이상
export const cheapGood = (f, r) => Boolean(f && r?.costPerServing > 0 && costOk(r) && r.costPerServing <= f.cheapLine && r.rating >= 4.8 && r.reviewCount >= 2)

// 레시피 목록 줄에 붙는 배지
export function FactBadges({ r }) {
  const f = useFacts()
  const who = personIn(f, r.title)
  return <>
    {cheapGood(f, r) && <span className="v3-badge down" title={`1인분 ${won(f.cheapLine)} 이하인데 별점 4.8 이상`}>싸도 만족도 높음</span>}
    {who && <span className="v3-badge neutral">{who} 레시피</span>}
  </>
}

// 레시피 상세 오른쪽 위 "이 레시피 데이터" 박스
export function RecipeFacts({ r }) {
  const f = useFacts()
  if (!f || !r) return null
  const c = clusterOf(f, r)
  const who = personIn(f, r.title)
  const grade = (r.reliability || '').replace('REL_', '')
  const share = f.gradeShare[grade]
  const prot = r.nutrition?.protein && r.costPerServing >= 1000 && r.pricedRatio >= 0.6 ? (r.nutrition.protein / r.costPerServing) * 1000 : null
  const rows = []
  if (c) rows.push(['유형', <><b>{c.name}</b> · 이 유형은 평균 {num(c.centerCookMin)}분, 1인분 {won(c.centerCostWon)}</>])
  if (cheapGood(f, r)) rows.push(['가성비', <>1인분 재료비가 <b>{won(f.cheapLine)} 이하</b>인데 별점 ★{r.rating} — 싸도 만족도가 높은 레시피예요</>])
  if (prot) rows.push(['영양 효율', <>1,000원당 단백질 <b>{num(prot, 1)}g</b>{prot >= 15 ? ' · 가성비 단백질 레시피' : ''}</>])
  if (grade) rows.push(['계량', <><b>{grade}등급</b>{share != null ? ` · 전체 레시피 중 ${grade}등급은 ${Math.round(share * 100)}%` : ''}{grade === 'A' ? ' · 적힌 양대로 따라 하면 돼요' : grade === 'D' ? " · '약간 · 넉넉히' 같은 표기가 많아요" : ''}</>])
  if (who && f.viewsRatio) rows.push(['제목', <>'{who}' 이름이 붙은 레시피예요. 이런 레시피는 조회수가 평균 <b>{f.viewsRatio.toFixed(1)}배</b>지만, 별점은 {f.named.avgRating < f.plain.avgRating ? '오히려 조금 낮아요' : '비슷해요'}</>])
  if (!rows.length) return null
  return (
    <div className="dn-box fact-box">
      <div className="dn-box-head">이 레시피, 데이터로 보면</div>
      <dl className="fact-dl">{rows.map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
    </div>
  )
}

// ⑦ 고른 재료와 자주 같이 쓰는 재료 (lift 높은 순, 이미 있는 재료 제외)
export function PairIngredients({ names = [], title = '이 재료와 자주 같이 써요', limit = 6, onPick }) {
  const f = useFacts()
  if (!f || !names.length) return null
  const have = new Set(names)
  const score = {}
  f.edges.forEach(e => {
    const [x, y] = have.has(e.a) ? [e.a, e.b] : have.has(e.b) ? [e.b, e.a] : []
    if (!x || have.has(y)) return
    if (!score[y] || score[y].n < e.coCount) score[y] = { name: y, with: x, lift: e.lift, n: e.coCount }
  })
  const list = Object.values(score).filter(x => x.lift >= 1.2).sort((a, b) => b.n - a.n).slice(0, limit)
  if (!list.length) return null
  return (
    <div className="fact-pair">
      <b>{title}</b>
      <div className="fact-chips">
        {list.map(x => onPick
          ? <button key={x.name} type="button" onClick={() => onPick(x.name)} title={`${x.with} + ${x.name} · ${num(x.n)}개 레시피`}>{x.name}<small>+{x.with}</small></button>
          : <Link key={x.name} to={`/recipes?q=${encodeURIComponent(x.name)}`} title={`${x.with} + ${x.name} · ${num(x.n)}개 레시피`}>{x.name}<small>+{x.with}</small></Link>)}
      </div>
      <span className="fact-note">같은 레시피에 함께 들어간 횟수로 계산했어요 (재료 네트워크 분석)</span>
    </div>
  )
}

// ④ 메인: 맛으로 고르기
const TASTE_WANT = { 매운맛: '매콤한', 국물: '얼큰한 국물' }
export function TasteBox() {
  const f = useFacts()
  if (!f?.taste.length) return null
  return (
    <div className="dn-box">
      <div className="dn-box-head">맛으로 고르기 <span className="fact-head-note">맛 표현별로 자주 들어가는 재료</span></div>
      <div className="dn-box-body fact-taste">
        {f.taste.slice(0, 6).map(t => (
          <Link key={t.word} to={`/recommend?want=${encodeURIComponent(TASTE_WANT[t.word] || t.items.slice(0, 2).join(','))}&mode=balance`}>
            <b>{t.word}</b><span>{t.items.join(' · ')}</span>
          </Link>
        ))}
      </div>
    </div>
  )
}
