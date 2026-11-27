// 먹었어요 버튼 (메뉴 상세 · 레시피 상세). 누르면 날짜 · 끼니 · 인분 · 메모를 골라 기록
import { useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { api, auth, localDay, MEAL_NAMES } from '../api'

// 지금 시각으로 끼니 미리 고르기
const guessMeal = (h = new Date().getHours()) => (h < 10 ? 'MEAL_BREAKFAST' : h < 15 ? 'MEAL_LUNCH' : h < 21 ? 'MEAL_DINNER' : 'MEAL_SNACK')
const shiftDay = n => { const d = new Date(); d.setDate(d.getDate() + n); return localDay(d) }

export function AteButton({ menuId, recipeId, name, className = '' }) {
  const loc = useLocation()
  const [open, setOpen] = useState(false)
  const [f, setF] = useState(() => ({ eatenOn: localDay(), mealType: guessMeal(), servings: 1, memo: '' }))
  const [busy, setBusy] = useState(false)
  const [done, setDone] = useState(null)
  const [err, setErr] = useState('')

  if (!auth.token()) {
    return <Link className={`v3-btn ate-btn ${className}`} to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`}>로그인하고 먹은 기록 남기기</Link>
  }
  const save = async () => {
    setBusy(true); setErr('')
    try {
      const r = await api.addMeal({ menuId: menuId ?? undefined, recipeId: recipeId ?? undefined, ...f, memo: f.memo.trim() || undefined })
      setDone(r); setOpen(false)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const dayLabel = d => (d === localDay() ? '오늘' : d === shiftDay(-1) ? '어제' : d === shiftDay(-2) ? '그저께' : d)

  return (
    <div className={`ate ${className}`}>
      {done && !open ? (
        <div className="ate-done" role="status">
          <span>✓ {dayLabel(done.eatenOn)} {done.mealTypeName || ''} 기록했어요</span>
          <Link to="/mypage?tab=meals">먹은 기록 보기</Link>
          <button type="button" className="btn text" onClick={() => { setDone(null); setOpen(true) }}>한 번 더</button>
        </div>
      ) : (
        <button type="button" className="v3-btn ate-btn" aria-expanded={open} onClick={() => setOpen(!open)}>
          <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5L10 17.5L19 7" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" /></svg>
          먹었어요
        </button>
      )}
      {open && (
        <div className="ate-form">
          <p className="ate-what">{name}</p>
          <div className="ate-row"><span>날짜</span>
            <div className="ate-chips">
              {[0, -1, -2].map(n => <button type="button" key={n} className={f.eatenOn === shiftDay(n) ? 'on' : ''} onClick={() => setF({ ...f, eatenOn: shiftDay(n) })}>{dayLabel(shiftDay(n))}</button>)}
              <input type="date" aria-label="다른 날짜" value={f.eatenOn} max={localDay()} min={shiftDay(-365)} onChange={e => e.target.value && setF({ ...f, eatenOn: e.target.value })} />
            </div>
          </div>
          <div className="ate-row"><span>끼니</span>
            <div className="ate-chips">{Object.entries(MEAL_NAMES).map(([k, v]) =>
              <button type="button" key={k} className={f.mealType === k ? 'on' : ''} onClick={() => setF({ ...f, mealType: k })}>{v}</button>)}</div>
          </div>
          <div className="ate-row"><span>양</span>
            <div className="ate-step">
              <button type="button" aria-label="반 인분 줄이기" disabled={f.servings <= 0.5} onClick={() => setF({ ...f, servings: Math.max(0.5, f.servings - 0.5) })}>−</button>
              <b>{f.servings}인분</b>
              <button type="button" aria-label="반 인분 늘리기" disabled={f.servings >= 10} onClick={() => setF({ ...f, servings: Math.min(10, f.servings + 0.5) })}>+</button>
            </div>
          </div>
          <input className="input" maxLength={200} placeholder="한 줄 메모 (선택)" value={f.memo} onChange={e => setF({ ...f, memo: e.target.value })} />
          {err && <p className="err">{err}</p>}
          <div className="ate-actions">
            <button type="button" className="btn text" onClick={() => setOpen(false)}>취소</button>
            <button type="button" className="btn primary" disabled={busy} onClick={save}>{busy ? '기록 중…' : '기록하기'}</button>
          </div>
        </div>
      )}
    </div>
  )
}
