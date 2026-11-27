import { Component, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

// deps 가 바뀌면 (탭 · 주소 이동) 새 데이터가 올 때까지 이전 데이터를 쓰지 않음.
// 이전 탭 데이터를 새 탭 모양으로 그리다 화면 전체가 멈추던 문제 방지
export function useApi(fn, deps = []) {
  const key = JSON.stringify(deps)
  const [s, set] = useState({ data: null, error: null, loading: true, key: null })
  useEffect(() => {
    let alive = true
    set({ data: null, error: null, loading: true, key })
    fn().then(d => alive && set({ data: d, error: null, loading: false, key }), e => alive && set({ data: null, error: e.message, loading: false, key }))
    return () => { alive = false }
  }, deps) // eslint-disable-line
  return s.key === key ? s : { data: null, error: null, loading: true }
}

// 한 화면에서 오류가 나도 앱 전체가 하얗게 되지 않게
export class ErrorBoundary extends Component {
  state = { error: null }
  static getDerivedStateFromError(error) { return { error } }
  componentDidUpdate(prev) { if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null }) }
  render() {
    if (this.state.error) return <div className="state error">이 화면을 그리다 문제가 생겼어요: {String(this.state.error.message || this.state.error)}</div>
    return this.props.children
  }
}

// 재료비는 가격 붙은 재료 60% 이상 · 1인분 500원 이상일 때만 믿고 보여줌 (그 아래는 단위 환산 · 시세 누락으로 3원 · 48원처럼 나옴)
export const costOk = r => r?.pricedRatio >= 0.6 && r?.costPerServing >= 500
export const won = n => (n == null ? '-' : `${Math.round(n).toLocaleString()}원`)
export const num = (n, d = 0) => (n == null ? '-' : Number(n).toLocaleString(undefined, { maximumFractionDigits: d }))
export const pct = n => (n == null ? '-' : `${n > 0 ? '+' : ''}${Number(n).toFixed(1)}%`)

export const DISH = {
  '국·찌개': ['🍲', '#FFE3D3'], '밥·죽': ['🍚', '#FFF1CC'], '면·분식': ['🍜', '#FFE0E0'], '반찬·메인': ['🍖', '#F3E3D3'],
  '디저트·음료': ['🍰', '#FBE2F0'], '샐러드': ['🥗', '#DDF3E0'], '전·튀김': ['🍤', '#FFF0D6'], '김치': ['🥬', '#E1F2DD'], '기타': ['🍽️', '#ECEEF2'],
}
export const dishOf = t => DISH[t] || DISH['기타']

const dishImages = {
  '국·찌개': 'stew', '밥·죽': 'rice', '면·분식': 'snack',
  '반찬·메인': 'main', '디저트·음료': 'dessert', '샐러드': 'salad',
  '전·튀김': 'pancake', '김치': 'kimchi', '기타': 'sides',
}

export const dishPhoto = type => `${import.meta.env.BASE_URL}food/${dishImages[type] ?? dishImages['기타']}.webp`

// src 가 있으면 만개의레시피 원본 사진, 없거나 못 불러오면 요리 종류 예시 사진
export function Thumb({ dishType, badge, badgeTone = 'brand', src }) {
  const [, background] = dishOf(dishType)
  const [broken, setBroken] = useState(false)
  const real = src && !broken
  return (
    <div className="thumb" style={{ background }}>
      <img src={real ? src : dishPhoto(dishType)} alt="" loading="lazy" referrerPolicy="no-referrer"
        onError={() => setBroken(true)} style={real ? { objectFit: 'cover' } : undefined} />
      {badge && <span className={`ribbon ${badgeTone}`}>{badge}</span>}
      <span className="thumb-label">{real ? '사진 · 만개의레시피' : '요리 종류 예시'}</span>
    </div>
  )
}

export function RecipeCard({ r, badge, badgeTone, extra }) {
  return (
    <Link to={`/recipes/${r.id}`} className="card">
      <div className="card-frame">
        <Thumb dishType={r.dishType} badge={badge} badgeTone={badgeTone} src={r.imageUrl} />
        <div className="card-stats">
          <span>{r.cookMin == null ? '시간 정보 없음' : `${r.cookMin}분`}</span>
          <span className="sep" />
          <span>1인분 <b>{costOk(r) ? won(r.costPerServing) : '-'}</b></span>
        </div>
      </div>
      <div className="card-type">{r.dishType || '기타'}{r.servings ? ` · ${r.servings}인분` : ''}</div>
      <div className="card-title">{r.title}</div>
      <div className="card-sub">조회 {num(r.views)} · 후기 {r.reviewCount ?? 0}{r.rating ? ` · ★ ${r.rating}` : ''}</div>
      {extra ?? (r.proteinPer1000 && costOk(r) && r.costPerServing >= 1000 ? <span className="chip-point">천원당 단백질 {num(r.proteinPer1000, 1)}g</span> : null)}
    </Link>
  )
}

export function MenuCard({ m, badge }) {
  return (
    <Link to={`/menus/${m.id}`} className="card">
      <div className="card-frame">
        <Thumb dishType={m.dishType} badge={badge} badgeTone="hot" src={m.imageUrl} />
        <div className="card-stats">
          <span>레시피 <b>{num(m.recipeCount)}</b></span>
          <span className="sep" />
          {m.interestIndex != null ? <span>관심도 <b>{num(m.interestIndex, 0)}</b></span> : <span>{m.kcal ? <>1인분 <b>{num(m.kcal)}</b>kcal</> : '영양 정보 없음'}</span>}
        </div>
      </div>
      <div className="card-type">{m.dishType || '기타'}</div>
      <div className="card-title">{m.name}</div>
      <div className="card-sub">{m.kcal ? `1인분 ${num(m.kcal)}kcal` : '영양 정보 없음'}{m.ytVideos ? ` · 영상 ${m.ytVideos}개` : ''}</div>
    </Link>
  )
}

export function Section({ title, more, children, desc }) {
  return (
    <section className="section">
      <div className="section-head">
        <h2>{title}{desc && <small>{desc}</small>}</h2>
        {more && <Link to={more} className="more">더보기</Link>}
      </div>
      {children}
    </section>
  )
}

export function Chips({ items, value, onChange, all = '전체' }) {
  return (
    <div className="chips">
      {all && <button className={!value ? 'on' : ''} onClick={() => onChange('')}>{all}</button>}
      {items.map(x => {
        const v = typeof x === 'string' ? x : x.value, l = typeof x === 'string' ? x : x.label
        return <button key={v} className={value === v ? 'on' : ''} onClick={() => onChange(value === v ? '' : v)}>{l}</button>
      })}
    </div>
  )
}

export function Select({ value, onChange, options, label }) {
  return (
    <label className="select">
      <select value={value} onChange={e => onChange(e.target.value)} aria-label={label}>
        {options.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
      </select>
    </label>
  )
}

export function State({ loading, error, empty, children }) {
  if (loading) return <div className="state"><span className="spinner" />불러오는 중…</div>
  if (error) return <div className="state error">문제가 생겼어요: {error}</div>
  if (empty) return <div className="state">{empty}</div>
  return children
}

export const Grid = ({ children, cols = 4 }) => <div className={`grid g${cols}`}>{children}</div>
