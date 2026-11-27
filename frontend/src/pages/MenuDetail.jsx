// UI v3 ③ 메뉴 상세: 대표 레시피 · 재료 오늘 시세 · 영양 · 같은 메뉴 다른 레시피 · 관심도 추이
import { Link, useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, num } from '../components/ui'
import { MultiLine } from '../components/charts'
import { Panel, PriceBadge, Photo, Source, wonUnit, fmtPct } from '../components/v3'
import { AteButton } from '../components/Meal'

const REL = { REL_A: '정량 표기가 거의 다예요 · 따라 하기 쉬움', REL_B: '대부분 정량이에요', REL_C: "'약간' 같은 표기가 섞여 있어요", REL_D: '양 표기가 모호해요' }
const views = n => (n == null ? '-' : n >= 10000 ? `${(n / 10000).toFixed(1)}만` : n.toLocaleString())

export default function MenuDetail() {
  const { id } = useParams()
  const nav = useNavigate()
  const m = useApi(() => api.menu(id), [id])
  const repId = m.data?.repRecipe?.id
  const r = useApi(() => (repId ? api.recipe(repId) : Promise.resolve(null)), [repId])
  const mainIds = (r.data?.ingredients || []).filter(l => !l.seas && l.iid).map(l => l.iid)
  const prices = useApi(() => (mainIds.length ? api.ingredientSummary(mainIds) : Promise.resolve({ items: [] })), [mainIds.join(',')])
  const priceBy = Object.fromEntries((prices.data?.items || []).map(x => [x.ingredientId, x]))
  const worst = [...(prices.data?.items || [])].filter(x => x.vsNormalPct > 10).sort((a, b) => b.vsNormalPct - a.vsNormalPct)[0]
  // 대체 재료: 더 싼 후보 중 같은 분류(채소 · 고기 …)인 것만 (네트워크 기반이라 계란 → 마늘 같은 짝이 섞여 있어서)
  const subs = useApi(async () => {
    if (!worst) return null
    const [me, list] = await Promise.all([api.ingredient(worst.ingredientId), api.substitutes(worst.ingredientId)])
    const cands = list.filter(s => s.vsNormalPct == null || s.vsNormalPct < worst.vsNormalPct).slice(0, 5)
    const cats = await Promise.all(cands.map(c => api.ingredient(c.id).catch(() => null)))
    return cands.find((c, i) => cats[i]?.category && cats[i].category === me.category) || null
  }, [worst?.ingredientId])
  const alt = subs.data
  const it = useApi(() => api.menuInterest(id), [id])
  const sim = useApi(() => api.similar(id), [id])
  const d = m.data, rec = r.data
  const ser = it.data || []
  const last = ser.at(-1)
  return (
    <div className="v3-page">
      <button type="button" className="v3-back" onClick={() => (window.history.length > 1 ? nav(-1) : nav('/recommend'))}>
        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5L8 12L15 19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>이전 화면으로
      </button>
      <State loading={m.loading} error={m.error}>
        {d && (
          <div className="v3-detail">
            <div className="v3-detail-left">
              <Photo src={rec?.imageUrl || d.imageUrl} alt={d.name} className="big" />
              <div>
                <span className="v3-kicker">{d.name} · 조회수 1위 레시피</span>
                <h1 className="v3-h1">{rec?.title || d.repRecipe?.title || d.name}</h1>
              </div>
              {rec && (
                <div className="v3-chips">
                  {rec.servings && <span className="v3-tag plain">{rec.servings}인분</span>}
                  {rec.cookMin && <span className="v3-tag plain">{rec.cookMin}분 이내</span>}
                  {rec.difficulty && <span className="v3-tag plain">{rec.difficulty}</span>}
                  <span className="v3-tag plain">조회 {views(rec.views)}</span>
                  <span className="v3-tag plain">★ {rec.rating ?? '-'} · 후기 {num(rec.reviewCount)}개</span>
                  {REL[rec.reliability] && <span className="v3-tag">{REL[rec.reliability]}</span>}
                </div>
              )}
              {rec && <Link className="v3-cta" to={`/recipes/${rec.id}`}>재료 · 레시피 자세히 보기</Link>}
              <AteButton menuId={+id} name={d.name} />
              {rec && <a className="v3-more" href={rec.sourceUrl} target="_blank" rel="noreferrer">만개의레시피 원문에서 조리 순서 보기 ↗</a>}
              <Source>출처: 만개의레시피 · 조리 단계와 사진은 원문에서 확인해 주세요. 같은 메뉴 레시피 {num(d.recipeCount)}개 중 조회수가 가장 많은 레시피예요.</Source>
              {sim.data?.length > 0 && (
                <div>
                  <h2 className="v3-h2">비슷한 메뉴</h2>
                  <div className="v3-chips">{sim.data.slice(0, 6).map(s => <Link key={s.id} to={`/menus/${s.id}`} className="v3-chip">{s.name}</Link>)}</div>
                </div>
              )}
            </div>

            <div className="v3-detail-right">
              <Panel title="재료 · 오늘 시세" sub={`KAMIS 소매가${prices.data?.ym ? ` · ${prices.data.ym}` : ''}`}>
                <State loading={r.loading} error={r.error}>
                  {rec && (
                    <>
                      <table className="v3-table">
                        <caption>[주재료]</caption>
                        <thead><tr><th scope="col">재료</th><th scope="col">양</th><th scope="col">시세</th><th scope="col">전일 대비</th><th scope="col">평년 대비</th></tr></thead>
                        <tbody>
                          {rec.ingredients.filter(l => !l.seas).map(l => {
                            const p = priceBy[l.iid]
                            return (
                              <tr key={l.seq}>
                                <th scope="row">{l.iid ? <Link to={`/explore?id=${l.iid}`}>{l.std || l.raw}</Link> : (l.std || l.raw)}</th>
                                <td>{l.amount || '-'}</td>
                                <td>{p ? wonUnit(p.avgPrice, p.unitLabel) : '–'}</td>
                                <td>{p?.dayChangePct != null ? fmtPct(p.dayChangePct, 1) : '–'}</td>
                                <td><PriceBadge pct={p?.vsNormalPct} /></td>
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                      {rec.ingredients.some(l => l.seas) && (
                        <div className="v3-seas"><span>[양념] 시세에서 빼요</span>
                          <div className="v3-chips">{rec.ingredients.filter(l => l.seas).map(l => <span key={l.seq} className="v3-tag plain">{l.std || l.raw} <strong>{l.amount}</strong></span>)}</div>
                        </div>
                      )}
                      {worst && (
                        <div className="v3-tip">
                          <span><strong>{worst.name}</strong>이(가) 평년보다 {Math.round(worst.vsNormalPct)}% 비싸요.{alt ? <> <strong>{alt.name}</strong>{alt.vsNormalPct != null ? `(평년 대비 ${fmtPct(alt.vsNormalPct)})` : ''}로 바꿔 보세요.</> : ' 양을 조금 줄여 보세요.'}</span>
                          <Link to={`/explore?id=${worst.ingredientId}`}>{worst.name} 시세 보기</Link>
                        </div>
                      )}
                    </>
                  )}
                </State>
              </Panel>

              <Panel title="영양성분 · 1인분" sub={`식약처 식품영양성분DB · ${d.name}`}>
                {d.nutrition ? (
                  <div className="v3-nutri">
                    {[['열량', d.nutrition.kcal, 'kcal'], ['탄수화물', d.nutrition.carbG, 'g'], ['단백질', d.nutrition.proteinG, 'g'], ['지방', d.nutrition.fatG, 'g'], ['나트륨', d.nutrition.sodiumMg, 'mg']].map(([l, v, u]) => (
                      <div key={l}><span>{l}</span><b>{v == null ? '-' : `${num(v, 1)}${u}`}</b></div>
                    ))}
                  </div>
                ) : <p className="v3-help">영양 정보 준비 중이에요.</p>}
                <Source>재료를 더한 값이 아니라 메뉴 단위 값이에요. 식약처 '음식' 분류에 없는 메뉴는 "영양 정보 준비 중"으로 보여 줘요.</Source>
              </Panel>

              {d.recipes?.length > 1 && (
                <Panel title="같은 메뉴, 다른 레시피" sub="조회수 많은 순">
                  <div className="v3-others">
                    {d.recipes.filter(x => x.id !== repId).slice(0, 4).map(o => (
                      <Link key={o.id} to={`/recipes/${o.id}`} className="v3-other">
                        <Photo src={o.imageUrl} label="썸네일" className="thumb" />
                        <div><b>{o.title}</b><span>조회 {views(o.views)} · ★ {o.rating ?? '-'}{o.cookMin ? ` · ${o.cookMin}분 이내` : ''}</span></div>
                      </Link>
                    ))}
                  </div>
                </Panel>
              )}

              <Panel title="이 메뉴, 요즘 얼마나 만드나" sub="지수: 최근 13개월 중 가장 많은 달 = 100">
                <State loading={it.loading} error={it.error} empty={it.data && it.data.length < 2 && '관심도 기록이 부족한 메뉴예요.'}>
                  {ser.length > 1 && (
                    <>
                      <MultiLine xs={ser.map(x => x.ym)} height={230} yFmt={v => Math.round(v)}
                        series={[{ name: '레시피 등록·후기', color: '#1F3A5F', values: Object.fromEntries(ser.map(x => [x.ym, x.interestIndex])) },
                          ...(ser.some(x => x.ytIndex != null) ? [{ name: '유튜브 쇼츠 언급', color: '#8A93A0', dash: true, values: Object.fromEntries(ser.map(x => [x.ym, x.ytIndex])) }] : [])]} />
                      {last?.yoyPct != null && <p className="v3-say">이번 달은 작년 같은 달보다 <strong>{Math.abs(Math.round(last.yoyPct))}% {last.yoyPct >= 0 ? '더' : '덜'}</strong> 만들고 있어요.</p>}
                    </>
                  )}
                </State>
              </Panel>
            </div>
          </div>
        )}
      </State>
    </div>
  )
}
