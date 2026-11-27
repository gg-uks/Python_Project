// UI v3 ⑤ 재료 탐색
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, num } from '../components/ui'
import { MultiLine, Scatter } from '../components/charts'
import { Panel, Kpi, BarList, Chip, PriceBadge, HotBadge, Source, wonUnit, fmtPct, signPct } from '../components/v3'

// 가격 × 관심: 작은 표본(10건 미만) 제외, 전체 증가 중앙값을 빼서 0 = 평균만큼 증가
function priceInterest(items = []) {
  const s = items.filter(i => +i.interestCnt >= 10 && i.priceVsNormalPct != null && i.interestYoyPct != null)
  if (!s.length) return { pts: [], r: null, med: null }
  const ys = s.map(i => +i.interestYoyPct).sort((a, b) => a - b), med = ys[Math.floor(ys.length / 2)]
  const pts = s.map(i => ({ x: +i.priceVsNormalPct, raw: +i.interestYoyPct, y: Math.max(-150, Math.min(150, +i.interestYoyPct - med)), name: i.name }))
  const n = pts.length, mx = pts.reduce((a, p) => a + p.x, 0) / n, my = pts.reduce((a, p) => a + p.y, 0) / n
  let sxy = 0, sxx = 0, syy = 0
  pts.forEach(p => { sxy += (p.x - mx) * (p.y - my); sxx += (p.x - mx) ** 2; syy += (p.y - my) ** 2 })
  return { pts, med, r: sxx && syy && n >= 5 ? +(sxy / Math.sqrt(sxx * syy)).toFixed(2) : null }
}

export default function Explore() {
  const [sp, setSp] = useSearchParams()
  const [q, setQ] = useState('')
  const sum = useApi(() => api.ingredientSummary())
  const found = useApi(() => (q.trim() ? api.ingredients(q.trim(), 8) : Promise.resolve([])), [q])
  const list = sum.data?.items || []
  const id = sp.get('id') || list[0]?.ingredientId
  const d = useApi(() => (id ? api.ingredientInsight(id) : Promise.resolve(null)), [id])
  const pick = i => { setSp({ id: String(i) }); setQ('') }
  const X = d.data
  const ser = X?.series || []
  const xs = ser.map(s => s.ym)
  const cur = ser.at(-1), lastYear = ser[0]
  const bestLag = [...(X?.lags || [])].sort((a, b) => Math.abs(b.corr ?? 0) - Math.abs(a.corr ?? 0))[0]
  const inList = list.some(x => String(x.ingredientId) === String(id))
  const extra = useApi(() => (id && !inList && sum.data ? api.ingredientSummary([id]) : Promise.resolve({ items: [] })), [id, inList, Boolean(sum.data)])
  const rows = [...list, ...(extra.data?.items || [])]
  const pi = useApi(() => api.rawAnalysis('price-interest'))
  const PI = priceInterest(pi.data?.items)
  return (
    <div className="v3-page">
      <div className="v3-title-row">
        <h1>재료 탐색{X ? ` · ${X.name}` : ''}</h1>
        <div className="v3-search">
          <input className="v3-input" value={q} onChange={e => setQ(e.target.value)} placeholder="다른 재료 찾기 (예: 배추, 굴)" aria-label="재료 찾기" />
          {found.data?.length > 0 && <div className="v3-sug">{found.data.filter(x => !x.seas).map(x => <button key={x.id} type="button" onClick={() => pick(x.id)}>{x.name}<small>{x.category}</small></button>)}</div>}
        </div>
      </div>
      <div className="v3-chips" role="group" aria-label="재료 고르기">
        {list.map(x => <Chip key={x.ingredientId} on={String(x.ingredientId) === String(id)} onClick={() => pick(x.ingredientId)}>{x.name}</Chip>)}
      </div>

      <State loading={d.loading} error={d.error}>
        {X && (
          <>
            <div className="v3-kpis">
              <Kpi label={`소매가${X.retail?.unitLabel ? ` (${X.retail.unitLabel})` : ''}`} value={X.retail ? `${num(X.retail.avgPrice)}원` : '–'}
                note={<><PriceBadge label="평년" pct={X.retail?.vsNormalPct} /> <small>전일 {X.dayChangePct != null ? fmtPct(X.dayChangePct, 1) : '–'}</small></>} />
              <Kpi label={`도매가${X.wholesale?.unitLabel ? ` (${X.wholesale.unitLabel})` : ''}`} value={X.wholesale ? `${num(X.wholesale.avgPrice)}원` : '–'}
                note={<PriceBadge label="평년" pct={X.wholesale?.vsNormalPct} />} />
              <Kpi label="이번 달 레시피 등록·후기" value={X.interestCnt != null ? `${num(X.interestCnt)}건` : '–'} note={`작년 같은 달 대비 ${fmtPct(X.interestYoyPct)}`} />
              <Kpi label="유튜브 쇼츠 언급 (이번 달)" value={X.ytVideoCnt != null ? `${num(X.ytVideoCnt)}건` : '–'} note="'먹방' 쇼츠 제목 기준" />
            </div>

            <Panel title="최근 13개월 · 시세와 레시피" sub={`${xs[0] || ''} ~ ${xs.at(-1) || ''}`}>
              <h3 className="v3-h3">KAMIS 소매가 ({X.retail?.unitLabel || '단위'}) · 올해 vs 평년</h3>
              {ser.filter(s => s.retailPrice != null).length > 1
                ? <MultiLine xs={xs} height={220} zero={false} yFmt={v => `${Math.round(v).toLocaleString()}원`}
                    series={[{ name: '올해 소매가', color: '#1F3A5F', values: Object.fromEntries(ser.map(s => [s.ym, s.retailPrice])) },
                      { name: '평년', color: '#8A93A0', dash: true, values: Object.fromEntries(ser.map(s => [s.ym, s.normalPrice])) }]} />
                : <p className="v3-help">시세 기록이 부족해요.</p>}
              <h3 className="v3-h3">만개의레시피 {X.name} 레시피 등록·후기 (건/월)</h3>
              {ser.filter(s => s.interestCnt != null).length > 1
                ? <MultiLine xs={xs} height={200} hideLegend yFmt={v => Math.round(v).toLocaleString()}
                    series={[{ name: '레시피 등록·후기', color: '#3D7758', values: Object.fromEntries(ser.map(s => [s.ym, s.interestCnt])) }]} />
                : <p className="v3-help">관심도 기록이 부족해요.</p>}
              {cur && lastYear && cur.vsNormalPct != null && cur.interestCnt != null && lastYear.interestCnt != null && (
                <p className="v3-say">이번 달 소매가는 평년보다 <strong>{Math.abs(Math.round(cur.vsNormalPct))}% {cur.vsNormalPct >= 0 ? '비싸고' : '싸고'}</strong>,
                  레시피 등록·후기는 작년 같은 달 {num(lastYear.interestCnt)}건 → 올해 {num(cur.interestCnt)}건이에요.</p>
              )}
            </Panel>

            <div className="v3-two">
              <Panel title="가격이 오르고 언제 덜 만드나" sub="평년 대비 가격 등락과 몇 달 뒤 레시피 관심도 변화의 상관계수">
                {X.lags.length
                  ? <><BarList items={X.lags.map(l => ({ label: `${l.lagMonth}개월 뒤`, value: +l.corr }))} fmt={v => v.toFixed(2)} max={1} />
                      {bestLag && <p className="v3-say">값이 바뀌고 <strong>{bestLag.lagMonth}개월 뒤</strong>에 관심도가 가장 크게 {bestLag.corr < 0 ? '줄어요' : '움직여요'} (r = {bestLag.corr}).</p>}</>
                  : <p className="v3-help">시차 상관을 계산할 만큼 기록이 쌓이지 않았어요.</p>}
                <Source>월 단위라 표본이 작아요 (최대 13개월). 데이터가 쌓이면 매일 적재 때 다시 계산해요.</Source>
              </Panel>
              <Panel title="이 재료가 들어가는 메뉴" sub={`${X.name} · 작년 같은 달 대비 관심도`}>
                <ul className="v3-menu-list">
                  {X.menus.map(m => <li key={m.menuId}><Link to={`/menus/${m.menuId}`}><span>{m.name}<small> 레시피 {num(m.n)}개</small></span><HotBadge pct={m.interestYoyPct} /></Link></li>)}
                </ul>
              </Panel>
            </div>
          </>
        )}
      </State>

      <div id="price-interest" /><Panel title="평년보다 비싼 재료는 덜 만들까 (재료 전체)" sub="가로: KAMIS 평년 대비 소매가 · 세로: 전체 평균보다 관심이 얼마나 더 늘었나 (작년 같은 달 대비)">
        <State loading={pi.loading} error={pi.error} empty={pi.data && !pi.data.items?.length && '이번 달 재료별 값이 아직 없어요.'}>
          {PI.pts.length > 0 && (
            <>
              <Scatter points={PI.pts} zeroLines fit color="#1F3A5F" labels={PI.pts.length <= 45}
                xTitle="평년 대비 가격 %" yTitle="평균 대비 관심 %p" xFmt={v => `${Math.round(v)}%`} yFmt={v => `${v > 0 ? '+' : ''}${Math.round(v)}`}
                tip={p => [p.name, `가격 ${signPct(p.x)} · 관심 ${signPct(p.raw)} (평균보다 ${p.y > 0 ? '+' : ''}${Math.round(p.y)}%p)`]} />
              <p className="v3-say">재료 {PI.pts.length}개 · 상관 r = {PI.r ?? '-'} · {PI.r == null ? '' : PI.r < -0.2 ? '비싼 재료일수록 관심이 덜 늘었어요' : PI.r > 0.2 ? '비싼 재료도 관심이 더 늘었어요' : '가격과 관심 사이에 뚜렷한 관계는 없어요'}</p>
            </>
          )}
        </State>
        <Source>관심도 = 만개의레시피 월별 신규 레시피 + 후기 수. 사이트 전체 레시피가 계속 늘어서 거의 모든 재료가 +로 나오기 때문에, 재료별 증가율에서 전체 중앙값({PI.med != null ? signPct(PI.med) : '-'})을 빼서 0을 "평균만큼 늘었다"로 맞췄어요. 표본이 작아 값이 튀는 재료(한 달 10건 미만)는 뺐어요. 점선은 추세선이에요.</Source>
      </Panel>

      <Panel title="재료별 요약" sub={`평년 대비 등락이 큰 재료 · 시차 = 가격이 바뀐 뒤 관심도가 가장 크게 반응한 달${sum.data?.ym ? ` · ${sum.data.ym}` : ''}`}>
        <State loading={sum.loading} error={sum.error}>
          <div className="v3-table-wrap">
            <table className="v3-table">
              <thead><tr><th scope="col">재료</th><th scope="col">소매가</th><th scope="col">전일 대비</th><th scope="col">평년 대비</th><th scope="col">레시피 관심도</th><th scope="col">시차</th></tr></thead>
              <tbody>{rows.map(r => (
                <tr key={r.ingredientId} className={String(r.ingredientId) === String(id) ? 'on' : ''}>
                  <th scope="row"><button type="button" className="v3-link" onClick={() => pick(r.ingredientId)}>{r.name}</button></th>
                  <td>{wonUnit(r.avgPrice, r.unitLabel)}</td>
                  <td>{r.dayChangePct != null ? fmtPct(r.dayChangePct, 1) : '–'}</td>
                  <td><PriceBadge pct={r.vsNormalPct} /></td>
                  <td>{signPct(r.interestYoyPct)}</td>
                  <td>{r.bestLag != null ? `${r.bestLag}개월` : '–'}</td>
                </tr>))}</tbody>
            </table>
          </div>
        </State>
      </Panel>
      <Source>출처: KAMIS 소매·도매가격(월평균 + 평년) · 만개의레시피 · YouTube Data API. 전일 대비는 KAMIS 일별 가격이 적재돼 있을 때만 보여요.</Source>
    </div>
  )
}
