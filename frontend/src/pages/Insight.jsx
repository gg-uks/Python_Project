// UI v3 ④ 물가·요리 인사이트
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, num } from '../components/ui'
import { Scatter, Network } from '../components/charts'
import { Panel, Kpi, BarList, Source, wonUnit, signPct } from '../components/v3'

const won0 = v => `${Math.round(v).toLocaleString()}원`

function Card({ no, title, children, note }) {
  return (
    <section className="v3-insight">
      <span className="v3-kicker">{no}</span>
      <h3>{title}</h3>
      {children}
      {note && <p className="v3-help">{note}</p>}
    </section>
  )
}


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

export default function Insight() {
  const k = useApi(() => api.insight())
  const pi = useApi(() => api.rawAnalysis('price-interest'))
  const cl = useApi(() => api.rawAnalysis('clusters'))
  const ex = useApi(() => api.insightExtra())
  const kw = useApi(() => api.trendKeywords())
  const val = useApi(() => api.rawAnalysis('value'))
  const net = useApi(() => api.analysis('network'))
  const me = useApi(() => api.rawAnalysis('measure'))
  const K = k.data
  const PI = priceInterest(pi.data?.items)
  const grades = me.data?.grades || []
  const gTot = grades.reduce((a, g) => a + g.cnt, 0) || 1
  const person = ex.data?.person || []
  const named = person.find(p => p.hasName), plain = person.find(p => !p.hasName)
  const kws = (kw.data?.keywords || []).filter(x => x.yoyPct != null).slice(0, 5)
  const kwsByViews = (kw.data?.keywords || []).slice(0, 5)
  return (
    <div className="v3-page">
      <div className="v3-title-row">
        <div>
          <h1>물가·요리 인사이트</h1>
          <p className="v3-lead">만개의레시피 레시피·후기, KAMIS 시세, 식약처 영양성분, 유튜브 쇼츠를 메뉴 사전 기준으로 묶어서 봐요.</p>
        </div>
        <span className="v3-tag plain">기간: {K?.ym || '-'}</span>
      </div>

      <State loading={k.loading} error={k.error}>
        {K && (
          <div className="v3-kpis">
            <Kpi label="분석한 레시피" value={`${num(K.recipeTotal)}개`} note="만개의레시피 · 계속 수집 중" />
            <Kpi label="평년보다 가장 오른 재료" tone="up" value={K.topUp ? `${K.topUp.name} ${signPct(K.topUp.vsNormalPct)}` : '–'} note={K.topUp ? `소매 ${wonUnit(K.topUp.avgPrice, K.topUp.unitLabel)}` : ''} />
            <Kpi label="평년보다 가장 내린 재료" tone="down" value={K.topDown ? `${K.topDown.name} ${signPct(K.topDown.vsNormalPct)}` : '–'} note={K.topDown ? `소매 ${wonUnit(K.topDown.avgPrice, K.topDown.unitLabel)}` : ''} />
            <Kpi label="가격과 관심도의 관계" value={PI.r != null ? `r = ${PI.r}` : '–'} note={`재료 ${PI.pts.length}개 · ${PI.r == null ? '' : PI.r < -0.2 ? '비쌀수록 덜 만들어요' : PI.r > 0.2 ? '비쌀 때도 더 만들어요' : '뚜렷한 관계는 없어요'}`} />
          </div>
        )}
      </State>

      <Panel title="평년보다 비싼 재료는 덜 만들까" sub="가로: KAMIS 평년 대비 소매가 · 세로: 전체 평균보다 관심이 얼마나 더 늘었나 (작년 같은 달 대비)">
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

      <h2 className="v3-h2 big">인사이트 8개</h2>
      <div className="v3-insights">
        <Card no="① 메뉴 군집화" title="조리시간·재료비로 나눈 메뉴 4유형" note="메뉴 추천의 '지금 상황' 버튼이 이 4유형을 그대로 써요. (K-means, k=4)">
          <State loading={cl.loading} error={cl.error}>
            {cl.data?.points?.length > 0 && (
              <Scatter height={260} xLog yLog points={cl.data.points.slice(0, 600).map(p => ({ x: p.cookMin, y: p.costPerServing, g: p.clusterId }))}
                groups={(cl.data.items || []).map(c => ({ id: c.clusterId, name: c.name }))} xTitle="조리시간" yTitle="1인분 재료비" xFmt={v => `${v}분`} yFmt={won0} />
            )}
          </State>
        </Card>
        <Card no="② 별점 × 예상 재료비" title="싸도 만족도 높은 메뉴가 있어요" note={ex.data?.ratingCost?.r != null ? `상관 r = ${ex.data.ratingCost.r} (레시피 ${num(ex.data.ratingCost.n)}개 · 후기 3개 이상)` : '후기 3개 이상 레시피'}>
          <State loading={ex.loading} error={ex.error}>
            {ex.data?.ratingCost?.points?.length > 1 && (
              <Scatter height={260} xLog points={ex.data.ratingCost.points.map(p => ({ x: +p.costPerServing, y: +p.rating, name: p.title }))} color="#1F3A5F"
                xTitle="1인분 재료비" yTitle="별점" xFmt={won0} yFmt={v => v.toFixed(1)} tip={p => [p.name.slice(0, 22), `${won0(p.x)} · ★ ${p.y}`]} />
            )}
          </State>
        </Card>
        <Card no="③ 사람 이름이 들어간 레시피" title='"○○○ 레시피"는 조회수가 더 많을까' note={ex.data?.personNames?.length ? `많이 나온 이름: ${ex.data.personNames.map(n => `${n.name} ${n.n}개`).join(' · ')}` : ''}>
          {named && plain && (
            <>
              <BarList items={[{ label: `이름 포함 (${num(named.n)}개)`, value: +named.medianViews }, { label: `이름 없음 (${num(plain.n)}개)`, value: +plain.medianViews }]} fmt={v => `조회 ${num(v)}`} />
              <p className="v3-say">평균 별점 · 이름 포함 ★ {named.avgRating} · 없음 ★ {plain.avgRating} <small className="muted">(조회수는 중앙값)</small></p>
            </>
          )}
        </Card>
        <Card no="④ 맛 표현별 주요 재료" title='"얼큰한 거" 하면 어떤 재료가 들어갈까' note="제목·소개·후기의 맛 표현과 같이 나오는 재료를 셌어요 (어디에나 들어가는 재료는 덜 세요).">
          <ul className="v3-taste">
            {(ex.data?.taste || []).slice(0, 6).map(t => <li key={t.word}><b>{t.word}</b>{t.items.map(i => <span key={i} className="v3-tag plain">{i}</span>)}</li>)}
          </ul>
        </Card>
        <Card no="⑤ 최근 트렌드 키워드" title="유튜브 쇼츠에서 뜨는 음식 키워드">
          {kws.length > 0
            ? <BarList items={kws.map(x => ({ label: x.keyword, value: +x.yoyPct }))} fmt={v => signPct(v)} />
            : <BarList items={kwsByViews.map(x => ({ label: x.keyword, value: +x.views }))} fmt={v => `${num(v / 10000)}만`} />}
          <Link to="/trends" className="v3-more">음식 트렌드에서 자세히 보기</Link>
        </Card>
        <Card no="⑥ 재료비 대비 영양 효율" title="1,000원당 단백질이 많은 레시피" note="1인분 재료비 1,000원 이상 · 가격이 붙은 재료 60% 이상 레시피만 봐요.">
          <BarList items={(val.data?.recipes || []).slice(0, 5).map(r => ({ label: r.title.slice(0, 16), value: +r.proteinPer1000won }))} fmt={v => `${v.toFixed(1)}g`} />
        </Card>
        <Card no="⑦ 식재료 공유 네트워크" title="같이 쓰이는 재료끼리 연결하면" note="원 크기 = 연결 수. 가운데 허브 재료의 시세가 메뉴 전체 재료비를 가장 크게 흔들어요.">
          {net.data?.items?.nodes?.length > 0 && <Network nodes={net.data.items.nodes.slice(0, 24)} edges={net.data.items.edges.filter(e => net.data.items.nodes.slice(0, 24).some(n => n.id === e.a) && net.data.items.nodes.slice(0, 24).some(n => n.id === e.b)).slice(0, 60)} />}
        </Card>
        <Card no="⑧ 레시피 신뢰도" title="'약간·넉넉히' 대충 표기 비율로 나누면" note="상세 화면의 신뢰도 배지로 보여 줘요.">
          {grades.length > 0 && (
            <>
              <div className="v3-stack">{grades.map((g, i) => <div key={g.grade} style={{ flex: g.cnt, background: ['#142842', '#3D7758', '#9BC9AA', '#DCE5F0'][i] || '#DCE5F0', color: i < 2 ? '#fff' : '#1B2330' }}>{g.grade} {Math.round((g.cnt / gTot) * 100)}%</div>)}</div>
              <div className="v3-chips small">{grades.map(g => <span key={g.grade}>{g.grade}: 평균 ★{g.avgRating ?? '-'} · 조회 {num(g.avgViews)}</span>)}</div>
            </>
          )}
        </Card>
      </div>
      <Source>출처: 만개의레시피 레시피·후기·조회수 · KAMIS 소매가(전국 평균, 평년가) · 식약처 식품영양성분DB · YouTube Data API. 매일 적재 뒤 다시 계산해요.</Source>
    </div>
  )
}
