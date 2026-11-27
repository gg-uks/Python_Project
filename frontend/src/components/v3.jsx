// UI v3 공통 조각: 등락 배지 · 칩 · 카드 · 숫자 카드 · 막대 목록
import { Link } from 'react-router-dom'

export const fmtPct = (v, digits = 0) => (v == null ? '–' : `${v > 0 ? '▲' : v < 0 ? '▼' : ''} ${Math.abs(Number(v)).toFixed(digits)}%`)
export const signPct = (v, digits = 0) => (v == null ? '–' : `${v > 0 ? '+' : v < 0 ? '−' : ''}${Math.abs(Number(v)).toFixed(digits)}%`)
export const wonUnit = (price, unit) => (price == null ? '–' : `${Math.round(price).toLocaleString()}원${unit ? ` / ${unit}` : ''}`)

// 평년 대비 시세: 오르면 주황(비쌈) · 내리면 파랑(쌈)
export function PriceBadge({ pct, label, digits = 0 }) {
  if (pct == null) return <span className="v3-badge neutral">{label ? `${label} –` : '–'}</span>
  return <span className={`v3-badge ${pct > 0 ? 'up' : 'down'}`}>{label ? `${label} ` : ''}{fmtPct(pct, digits)}</span>
}

// 관심도: 오르면 초록 · 내리면 회색
export function HotBadge({ pct, prefix = '관심도' }) {
  if (pct == null) return <span className="v3-badge neutral">{prefix} –</span>
  return <span className={`v3-badge ${pct >= 0 ? 'hot' : 'cold'}`}>{prefix} {fmtPct(pct)}</span>
}

export function Chip({ on, onClick, children, tone }) {
  return <button type="button" className={`v3-chip ${on ? 'on' : ''} ${tone || ''}`} aria-pressed={on ? 'true' : 'false'} onClick={onClick}>{children}</button>
}

export function RemoveChip({ onRemove, children }) {
  return (
    <button type="button" className="v3-chip avoid" onClick={onRemove} aria-label={`${children} 제외 해제`}>
      {children}<svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true"><path d="M2 2L10 10M10 2L2 10" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" /></svg>
    </button>
  )
}

export function Panel({ title, sub, right, children, className = '' }) {
  return (
    <section className={`v3-panel ${className}`}>
      {(title || right) && <div className="v3-panel-head"><div>{title && <h2>{title}</h2>}{sub && <span className="v3-sub">{sub}</span>}</div>{right}</div>}
      {children}
    </section>
  )
}

export function Kpi({ label, value, note, tone }) {
  return <div className="v3-kpi"><span className="v3-kpi-l">{label}</span><span className={`v3-kpi-v ${tone || ''}`}>{value}</span>{note && <span className="v3-kpi-n">{note}</span>}</div>
}

// 가로 막대 목록 (이름 · 막대 · 값)
export function BarList({ items, label = 'label', value = 'value', fmt = v => v, max, tone }) {
  const m = max ?? Math.max(...items.map(i => Math.abs(+i[value] || 0)), 1e-9)
  return (
    <div className="v3-bars">
      {items.map((it, k) => {
        const v = +it[value] || 0
        return (
          <div className="v3-bar-row" key={k}>
            <span className="v3-bar-label" title={it[label]}>{it[label]}</span>
            <span className="v3-bar-track"><span className={`v3-bar-fill ${tone || (v < 0 ? 'neg' : '')}`} style={{ width: `${Math.min(100, (Math.abs(v) / m) * 100)}%` }} /></span>
            <span className="v3-bar-val">{fmt(v)}</span>
          </div>
        )
      })}
    </div>
  )
}

export function BackLink({ to, children }) {
  return (
    <Link to={to} className="v3-back">
      <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M15 5L8 12L15 19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>{children}
    </Link>
  )
}

export function Photo({ src, alt = '', label = '대표 레시피 사진 (만개의레시피)', className = '' }) {
  return (
    <div className={`v3-photo ${className}`}>
      {src ? <img src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none' }} /> : null}
      <span>{label}</span>
    </div>
  )
}

export const Source = ({ children }) => <p className="v3-source">{children}</p>
