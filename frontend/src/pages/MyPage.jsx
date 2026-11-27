import { useEffect, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, auth, localDay } from '../api'
import { useApi, State } from '../components/ui'
import { Panel, Kpi, BarList } from '../components/v3'
import { TagPicker } from './Auth'
import Analysis from './Analysis'
import { ReportGallery } from '../components/Report'

export default function MyPage() {
  const [sp, setSp] = useSearchParams()
  if (!auth.token()) return <div className="state">로그인이 필요해요. <Link to="/login?next=/mypage">로그인</Link></div>
  // 데이터 분석 · 보고서 차트 탭은 관리자만
  const tabs = [['meals', '먹은 기록'], ['prefs', '내 정보 · 취향'], ...(auth.isAdmin() ? [['analysis', '데이터 분석'], ['report', '보고서 차트']] : [])]
  const tab = tabs.some(t => t[0] === sp.get('tab')) ? sp.get('tab') : 'meals'
  return (
    <div className="v3-page mypage">
      <div className="seg mypage-tabs" role="tablist">
        {tabs.map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={`${tab === k ? 'on' : ''} ${k === 'analysis' || k === 'report' ? 'admin-only' : ''}`} onClick={() => setSp({ tab: k })}>{l}</button>)}
      </div>
      {tab === 'meals' && <MealLog />}
      {tab === 'prefs' && <Prefs />}
      {tab === 'analysis' && <div className="mypage-admin"><p className="v3-sub">관리자에게만 보이는 탭이에요.</p><Analysis /></div>}
      {tab === 'report' && <div className="mypage-admin"><p className="v3-sub">관리자에게만 보이는 탭이에요.</p><ReportGallery /></div>}
    </div>
  )
}

// ── 먹은 기록 · 주간 요약 ──
const addDays = (iso, n) => { const d = new Date(iso + 'T00:00'); d.setDate(d.getDate() + n); return localDay(d) }
const WD = ['월', '화', '수', '목', '금', '토', '일']
const md = iso => { const [, m, d] = iso.split('-'); return `${+m}/${+d}` }
const n0 = v => (v == null ? '–' : Math.round(v).toLocaleString())

function MealLog() {
  const [week, setWeek] = useState(localDay())
  const [ver, setVer] = useState(0)
  const sum = useApi(() => api.mealSummary(week), [week, ver])
  const s = sum.data
  const list = useApi(() => (s ? api.meals(s.weekStart, s.weekEnd) : Promise.resolve(null)), [s?.weekStart, ver])
  const thisWeek = s && s.weekEnd >= localDay()
  const del = async m => {
    if (!window.confirm(`${md(m.eatenOn)} ${m.menuName || m.recipeTitle} 기록을 지울까요?`)) return
    await api.deleteMeal(m.mealId); setVer(v => v + 1)
  }
  const byDay = {}
  ;(list.data?.items || []).forEach(m => { (byDay[m.eatenOn] ||= []).push(m) })
  const maxK = Math.max(1, ...(s?.days || []).map(d => d.kcal || 0))
  const partial = k => !s || !s.count || s.known[k] >= s.count ? null : s.known[k] === 0 ? '계산할 수 있는 기록이 아직 없어요' : `${s.count}끼 중 ${s.known[k]}끼만 더했어요`
  return (
    <State loading={sum.loading} error={sum.error}>
      {s && (
        <>
          <div className="v3-title-row">
            <div><h1>먹은 기록</h1><span className="v3-sub">메뉴·레시피 화면의 ‘먹었어요’로 남긴 기록이에요</span></div>
            <div className="v3-tools week-nav">
              <button type="button" className="v3-btn" aria-label="지난주" onClick={() => setWeek(addDays(s.weekStart, -7))}>‹</button>
              <b>{md(s.weekStart)} – {md(s.weekEnd)}{thisWeek ? ' (이번 주)' : ''}</b>
              <button type="button" className="v3-btn" aria-label="다음 주" disabled={thisWeek} onClick={() => setWeek(addDays(s.weekStart, 7))}>›</button>
            </div>
          </div>
          {s.count === 0 ? (
            <div className="state">이 주에는 기록이 없어요. <Link to="/">메뉴 추천</Link>에서 메뉴를 골라 ‘먹었어요’를 눌러 보세요.</div>
          ) : (
            <>
              <div className="v3-kpis">
                <Kpi label="기록" value={`${s.count}끼`} note={`${s.eatenDays}일 동안`} />
                <Kpi label="열량" value={`${n0(s.total.kcal)} kcal`} note={partial('kcal') || `하루 평균 ${n0(s.dailyAvg.kcal)} kcal`} />
                <Kpi label="단백질" value={`${n0(s.total.proteinG)} g`} note={partial('proteinG') || `하루 평균 ${n0(s.dailyAvg.proteinG)} g`} />
                <Kpi label="나트륨" value={`${n0(s.total.sodiumMg)} mg`} note={partial('sodiumMg') || `하루 평균 ${n0(s.dailyAvg.sodiumMg)} mg`} />
                <Kpi label="재료비" value={s.total.costWon != null ? `${n0(s.total.costWon)}원` : '–'} note={partial('costWon') || '1인분 재료비 × 먹은 양'} />
              </div>
              <div className="v3-grid2">
                <Panel title="요일별 열량" sub="kcal · 레시피 1인분 영양 × 먹은 양">
                  <div className="week-bars" role="img" aria-label={s.days.map((d, i) => `${WD[i]} ${n0(d.kcal)}kcal`).join(', ')}>
                    {s.days.map((d, i) => (
                      <div key={d.date} className={`wb ${d.date === localDay() ? 'today' : ''}`} title={`${md(d.date)} · ${d.count}끼 · ${n0(d.kcal)} kcal`}>
                        <span className="wb-v">{d.kcal ? n0(d.kcal) : ''}</span>
                        <span className="wb-track"><span className="wb-fill" style={{ height: `${((d.kcal || 0) / maxK) * 100}%` }} /></span>
                        <span className="wb-l">{WD[i]}<small>{d.count ? `${d.count}끼` : ''}</small></span>
                      </div>
                    ))}
                  </div>
                </Panel>
                <Panel title="요리 종류" sub="이번 주 먹은 끼니 비율">
                  <BarList items={s.dishMix} label="dishType" value="pct" max={100} fmt={v => `${Math.round(v)}%`} />
                  {s.dishMix[0]?.pct >= 50 && s.count >= 4 && <p className="v3-sub">{s.dishMix[0].dishType} 비중이 높아요. 다른 종류도 골라 보세요.</p>}
                </Panel>
              </div>
              <Panel title="기록" sub="최근 날짜부터">
                <State loading={list.loading} error={list.error}>
                  <div className="meal-days">
                    {Object.entries(byDay).map(([day, ms]) => (
                      <div key={day} className="meal-day">
                        <h3 className="v3-h3">{md(day)} ({WD[(new Date(day + 'T00:00').getDay() + 6) % 7]})</h3>
                        {ms.map(m => (
                          <div key={m.mealId} className="meal-row">
                            {m.imageUrl ? <img src={m.imageUrl} alt="" loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.visibility = 'hidden' }} /> : <span className="meal-noimg" />}
                            <div className="meal-main">
                              <div>
                                {m.mealTypeName && <span className="v3-tag plain">{m.mealTypeName}</span>}
                                {m.menuId ? <Link to={`/menus/${m.menuId}`}><b>{m.menuName}</b></Link> : <b>{m.menuName || '지워진 메뉴'}</b>}
                                {m.servings !== 1 && <span className="muted"> · {m.servings}인분</span>}
                              </div>
                              {m.recipeId && <Link className="muted small" to={`/recipes/${m.recipeId}`}>{m.recipeTitle}</Link>}
                              {m.memo && <span className="muted small">“{m.memo}”</span>}
                            </div>
                            <span className="meal-n">{m.kcal != null ? `${n0(m.kcal)} kcal` : ''}{m.costWon != null ? ` · ${n0(m.costWon)}원` : ''}</span>
                            <button type="button" className="btn text" aria-label="기록 지우기" onClick={() => del(m)}>삭제</button>
                          </div>
                        ))}
                      </div>
                    ))}
                  </div>
                </State>
              </Panel>
            </>
          )}
          <p className="v3-sub">영양·재료비는 고른 레시피(없으면 그 메뉴 대표 레시피)의 1인분 값이에요. 재료 가격이 60% 넘게 확인된 레시피만 재료비를 더해요. 최근 3일 안에 먹은 메뉴는 메뉴 추천에서 뒤로 보내요.</p>
        </>
      )}
    </State>
  )
}

// ── 내 정보 · 취향 ──
function Prefs() {
  const nav = useNavigate()
  const me = useApi(() => api.me())
  const tags = useApi(() => api.filterTags())
  const [f, setF] = useState(null)
  const [saved, setSaved] = useState('')
  useEffect(() => { if (me.data) setF(me.data) }, [me.data])
  const save = async () => { await api.updateMe(f); setSaved('저장했어요') }
  const withdraw = async () => {
    if (!window.confirm('탈퇴하면 취향 설정이 사라져요. 탈퇴할까요?')) return
    await api.withdraw(); await api.logout(); nav('/')
  }
  return (
    <State loading={me.loading || !f} error={me.error}>
      {f && (
        <div className="auth wide">
          <h1>내 정보 · 취향</h1>
          <p className="muted">{f.email}</p>
          <input className="input" value={f.nickname} onChange={e => setF({ ...f, nickname: e.target.value })} placeholder="닉네임" />
          <div className="filter-row"><span>가구원 수</span><div className="chips">{[1, 2, 3, 4, 5, 6].map(n =>
            <button key={n} className={f.householdSize === n ? 'on' : ''} onClick={() => setF({ ...f, householdSize: n })}>{n}명</button>)}</div></div>
          {tags.data && <TagPicker tags={tags.data.tags} want={f.wantTagIds || []} exclude={f.excludeTagIds || []} onChange={(w, x) => setF({ ...f, wantTagIds: w, excludeTagIds: x })}
            wantItems={f.wantItems || []} excludeItems={f.excludeItems || []} onItems={(w, x) => setF({ ...f, wantItems: w, excludeItems: x })} />}
          <button className="btn primary wide" onClick={save}>저장</button>
          {saved && <p className="muted">{saved}</p>}
          <button className="btn text" onClick={withdraw}>회원 탈퇴</button>
        </div>
      )}
    </State>
  )
}
