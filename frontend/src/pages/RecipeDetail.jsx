// 레시피 상세 (UI v3): 재료 · 양 · 오늘 시세 · 재료비 · 영양 · 후기. 조리 순서는 원문(만개의레시피)에서
import { Link, useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, won, num, costOk } from '../components/ui'
import { Panel, PriceBadge, Photo, Source, wonUnit, fmtPct } from '../components/v3'
import { AteButton } from '../components/Meal'
import { RecipeFacts, PairIngredients } from '../components/Facts'

const REL = { REL_A: ['A', '양이 거의 다 정량이에요 · 따라 하기 쉬움'], REL_B: ['B', '대부분 정량이에요'], REL_C: ['C', "'약간' 같은 표기가 섞여 있어요"], REL_D: ['D', '양 표기가 모호해요'] }
const views = n => (n == null ? '-' : n >= 10000 ? `${(n / 10000).toFixed(1)}만` : n.toLocaleString())

export default function RecipeDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: r, loading, error } = useApi(() => api.recipe(id), [id])
  const main = r?.ingredients.filter(l => !l.seas) || []
  const ids = main.filter(l => l.iid).map(l => l.iid)
  // 레시피를 쓴 사람이 나눈 묶음 순서 그대로 ([재료] · [양념] · [고사리 밑간 재료] …)
  const groups = []
  for (const l of r?.ingredients || []) { const g = l.grp || l.group || '[재료]'; const last = groups.at(-1); if (last && last[0] === g) last[1].push(l); else groups.push([g, [l]]) }
  const steps = useApi(() => api.recipeSteps(id), [id])
  const prices = useApi(() => (ids.length ? api.ingredientSummary(ids) : Promise.resolve({ items: [] })), [ids.join(',')])
  const by = Object.fromEntries((prices.data?.items || []).map(x => [x.ingredientId, x]))
  const rel = REL[r?.reliability]
  const total = (r?.ingredients || []).reduce((s, l) => s + (l.cost || 0), 0)
  return (
    <div className="v3-page">
      <button type="button" className="v3-back" onClick={() => (window.history.length > 1 ? nav(-1) : nav('/recipes'))}>
        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5L8 12L15 19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>이전 화면으로
      </button>
      <State loading={loading} error={error}>
        {r && (
          <div className="v3-detail">
            <div className="v3-detail-left">
              <Photo src={r.imageUrl} alt={r.title} className="big" label="레시피 사진 (만개의레시피)" />
              <div>
                <span className="v3-kicker">{r.menuId ? <Link to={`/menus/${r.menuId}`}>{r.menu}</Link> : '메뉴 미분류'} · {r.dishType || '기타'}</span>
                <h1 className="v3-h1">{r.title}</h1>
              </div>
              {r.intro && <p className="v3-say v3-intro">{r.intro}</p>}
              <div className="v3-chips">
                {r.servings && <span className="v3-tag plain">{r.servings}인분</span>}
                {r.cookMin && <span className="v3-tag plain">{r.cookMin}분 이내</span>}
                {r.difficulty && <span className="v3-tag plain">{r.difficulty}</span>}
                <span className="v3-tag plain">조회 {views(r.views)}</span>
                <span className="v3-tag plain">★ {r.rating ?? '-'} · 후기 {num(r.reviewCount)}개</span>
                {rel && <span className="v3-tag">신뢰도 {rel[0]} · {rel[1]}</span>}
              </div>
              {r.tastes.length > 0 && <div className="v3-chips">{r.tastes.slice(0, 6).map(t => <span key={t} className="v3-tag plain">#{t}</span>)}</div>}
              <a className="v3-cta" href="#steps" onClick={e => { e.preventDefault(); document.querySelector('.v3-steps, #steps')?.scrollIntoView({ behavior: 'smooth' }) }}>조리 순서 보기</a>
              <AteButton recipeId={r.id} name={r.title} />
              <a className="v3-more" href={r.sourceUrl} target="_blank" rel="noreferrer">만개의레시피 원문 열기 ↗</a>
            </div>

            <div className="v3-detail-right">
              <RecipeFacts r={r} />
              <Panel title="재료" sub={`${r.ingredients.length}가지 · 레시피에 적힌 그대로 · 시세는 KAMIS 소매가${prices.data?.ym ? ` (${prices.data.ym})` : ''}`}>
                {groups.map(([g, lines]) => (
                  <div key={g} className="v3-ing-group">
                    <h3 className="v3-h3">{g.replace(/^\[|\]$/g, '') || '재료'}</h3>
                    <ul className="v3-ing">
                      {lines.map(l => {
                        const p = by[l.iid]
                        return (
                          <li key={l.seq}>
                            <span className="v3-ing-name">{l.rawName || l.raw}{l.seas && <em>양념</em>}</span>
                            <span className="v3-ing-amt">{l.amount || '-'}{l.grams && !/^\s*[\d.]+\s*g\s*$/i.test(l.amount || '') ? <small> ≈{num(l.grams)}g</small> : null}</span>
                            <span className="v3-ing-std">{l.iid ? <Link to={`/explore?id=${l.iid}`}>{l.std}</Link> : <span className="muted">사전 없음</span>}</span>
                            <span className="v3-ing-price">{!l.seas && p?.avgPrice != null ? <><PriceBadge pct={p.vsNormalPct} /><small>{wonUnit(p.avgPrice, p.unitLabel)}</small></> : null}</span>
                            <span className="v3-ing-cost">{l.cost ? won(l.cost) : ''}</span>
                          </li>
                        )
                      })}
                    </ul>
                  </div>
                ))}
                <PairIngredients names={[...new Set(main.filter(l => l.iid).map(l => l.std))]} title="이 레시피 재료와 자주 같이 쓰는 재료" />
                <div className="v3-cost">
                  <div><span>1인분 재료비</span><b>{costOk(r) ? won(r.costPerServing) : '–'}</b></div>
                  <div><span>재료비 합 (값이 붙은 재료)</span><b>{total ? won(total) : '–'}</b></div>
                  <div><span>가격이 붙은 재료</span><b>{r.pricedRatio != null ? `${Math.round(r.pricedRatio * 100)}%` : '–'}</b></div>
                </div>
                <Source>오른쪽 초록 글자 = OMM 재료 사전의 표준 이름 (누르면 재료 시세). 재료비 = 양(g) × 그 달 100g당 소매가. 가격이 붙은 재료가 60% 미만이거나 1인분 500원 미만이면 ‘–’로 보여 줘요.</Source>
              </Panel>

              <Panel title="조리 순서" sub="만개의레시피 원문 · 작성자 저작물">
                <State loading={steps.loading} error={steps.error}>
                  {steps.data?.steps?.length > 0 ? (
                    <ol className="v3-steps">
                      {steps.data.steps.map(st => (
                        <li key={st.no}>
                          <span className="v3-step-no">{st.no}</span>
                          <div className="v3-step-body">
                            <p>{st.text}</p>
                            {st.imageUrl && <img src={st.imageUrl} alt={`${st.no}단계`} loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none' }} />}
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : <p className="v3-help">{steps.data?.error || '조리 순서를 불러오지 못했어요.'} <a href={r.sourceUrl} target="_blank" rel="noreferrer">원문에서 보기 ↗</a></p>}
                  {steps.data?.tips?.length > 0 && <div className="v3-tip green">{steps.data.tips.map((t, i) => <span key={i}>{t}</span>)}</div>}
                </State>
                <Source>조리 순서와 사진은 만개의레시피 작성자의 저작물이에요. OMM 은 저장하지 않고 볼 때마다 원문에서 읽어 와요 (수업용 · 내부망). <a href={r.sourceUrl} target="_blank" rel="noreferrer">원문 보기 ↗</a></Source>
              </Panel>

              <Panel title="영양 · 1인분" sub={r.nutrition?.basis === 'recipe' ? '레시피 재료로 계산' : `메뉴 ‘${r.menu || '-'}’ 기준 · 식약처`}>
                {r.nutrition?.kcal ? (
                  <div className="v3-nutri three">
                    <div><span>열량</span><b>{num(r.nutrition.kcal)}kcal</b></div>
                    <div><span>단백질</span><b>{num(r.nutrition.protein, 1)}g</b></div>
                    <div><span>나트륨</span><b>{num(r.nutrition.sodium)}mg</b></div>
                  </div>
                ) : <p className="v3-help">영양 정보 준비 중이에요.</p>}
              </Panel>

              <Panel title="후기" sub={`${r.reviews.length}개 · 최근 순`}>
                {r.reviews.length ? r.reviews.slice(0, 5).map((v, i) => (
                  <div className="v3-review" key={i}><span className="v3-stars">{'★'.repeat(v.stars || 0)}</span><p>{v.text}</p><small>{v.writtenAt}</small></div>
                )) : <p className="v3-help">아직 후기가 없어요.</p>}
              </Panel>
            </div>
          </div>
        )}
      </State>
    </div>
  )
}
