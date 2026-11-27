// 검색 결과: 상황 문장 추천 (POST /api/recommend/es → 실패 시 /text) + 엘라스틱서치 레시피 검색 (GET /api/search/recipes)
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, won } from '../components/ui'
import { Thumb, RecipeRow, Pager } from '../components/dn'

const SIZE = 10

export default function Search() {
  const [sp, setSp] = useSearchParams()
  const q = (sp.get('q') || '').trim()
  const page = +sp.get('page') || 1
  const [shown, setShown] = useState([])            // '다른 메뉴 보기'로 이미 본 메뉴
  const rec = useApi(() => (q ? api.situation(q, shown) : Promise.resolve(null)), [q, shown.join(',')])
  const R = rec.data, A = R?.analysis
  // 문장 그대로 레시피를 못 찾으면 문장에서 찾은 메뉴 · 재료 → 추천 1위 메뉴 이름으로 다시 찾음
  const alt = A ? (A.wantMenus[0] || A.wantIngredients[0] || R.items[0]?.name || '') : ''
  const rs = useApi(async () => {
    if (!q) return null
    const r = await api.searchRecipes({ q, page, size: SIZE })
    if (r.total || !alt || alt === q) return r
    return { ...(await api.searchRecipes({ q: alt, page, size: SIZE })), usedQ: alt }
  }, [q, page, alt])
  const pages = rs.data ? Math.min(30, Math.ceil(rs.data.total / SIZE)) : 0
  if (!q) return <div className="v3-page"><h1>검색</h1><p className="v3-help">위 검색창에 메뉴 이름이나 "비 오는 날 얼큰한 거" 같은 문장을 입력해 보세요.</p></div>
  return (
    <div className="v3-page">
      <div className="v3-title-row"><div><h1>‘{q}’ 검색 결과</h1><span className="v3-sub">입력한 말에 맞는 메뉴와 레시피를 찾았어요</span></div></div>

      <section className="dn-sec sr-rec">
        <div className="dn-sec-head">
          <h2>{R?.title || '이 말에 맞는 메뉴'} <small>{R?.personalized ? '내 취향 반영' : ''}</small></h2>
          {R?.items?.length > 0 && <button type="button" className="dn-btn line" onClick={() => setShown(s => [...new Set([...s, ...R.items.map(i => i.menuId)])])}>다른 메뉴 보기 ↻</button>}
        </div>
        {A && (
          <div className="sr-ana">
            {A.tags.map(t => <span key={t.name} className="v3-tag">#{t.name}<small> ‘{t.keyword}’</small></span>)}
            {A.wantMenus.map(m => <span key={m} className="v3-tag">메뉴 · {m}</span>)}
            {A.wantIngredients.map(m => <span key={m} className="v3-tag">재료 · {m}</span>)}
            {[...A.avoidIngredients, ...A.avoidTags.map(t => t.name)].map(m => <span key={m} className="v3-tag avoid">빼기 · {m}</span>)}
            {A.recentMenus?.length > 0 && <span className="v3-tag plain">최근 먹은 {A.recentMenus.join(' · ')} 비슷한 메뉴 뺌</span>}
            {!A.tags.length && !A.wantMenus.length && !A.wantIngredients.length && !A.avoidIngredients.length && <span className="v3-help">문장에서 상황을 찾지 못해 많이 찾는 메뉴를 보여 드려요</span>}
          </div>
        )}
        <State loading={rec.loading} error={rec.error} empty={R && !R.items.length && '맞는 메뉴를 못 찾았어요. 다르게 말해 보세요.'}>
          <div className="dn-pcards">
            {R?.items.map(m => (
              <Link key={m.menuId} to={`/menus/${m.menuId}`} className="dn-pcard">
                <Thumb src={m.imageUrl} alt={m.name} />
                <small>{m.dishType}{m.cookMin ? ` · ${m.cookMin}분` : ''}{m.costPerServing ? ` · 1인분 ${won(m.costPerServing)}` : ''}</small>
                <b>{m.name}</b>
                <span className="sr-why">{m.reasons.slice(0, 2).join(' · ')}</span>
              </Link>
            ))}
          </div>
        </State>
      </section>

      <section className="dn-sec">
        <div className="dn-sec-head">
          <h2>{rs.data?.usedQ ? `‘${rs.data.usedQ}’ 레시피` : '레시피'} <small>{rs.data ? `${rs.data.total.toLocaleString()}개${rs.data.usedQ ? ' · 문장과 똑같은 레시피가 없어 추천 메뉴로 찾았어요' : ''}` : ''}</small></h2>
          <Link to={`/recipes?q=${encodeURIComponent(q)}`}>조건으로 더 찾기 ›</Link>
        </div>
        <State loading={rs.loading} error={rs.error} empty={rs.data && !rs.data.items.length && '맞는 레시피가 없어요.'}>
          <ul className="dn-list">{rs.data?.items.map(r => <RecipeRow key={r.id} r={r} />)}</ul>
          <Pager page={page} pages={pages} onChange={n => setSp({ q, page: String(n) })} />
        </State>
      </section>
    </div>
  )
}
