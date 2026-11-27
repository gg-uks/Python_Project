// 목록형(가격 비교 사이트식) 공통 부품: 조건표 · 정렬 탭 · 목록 한 줄 · 가격 칸 · 쪽 번호 · 비교 담기
import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { PriceBadge, HotBadge } from './v3'
import { won, num, costOk } from './ui'
import { FactBadges } from './Facts'

// ── 조건표: 왼쪽 회색 칸 = 조건 이름, 오른쪽 = 고르는 칸 ──
export function FilterTable({ title, right, children, className = '' }) {
  return (
    <section className={`dn-ftable ${className}`}>
      {(title || right) && <div className="dn-ftable-head"><h2>{title}</h2>{right}</div>}
      <div className="dn-frows">{children}</div>
    </section>
  )
}
export function FRow({ label, help, children }) {
  return (
    <div className="dn-frow">
      <div className="dn-fth">{label}</div>
      <div className="dn-ftd">{children}{help && <p className="dn-fhelp">{help}</p>}</div>
    </div>
  )
}
// 체크박스처럼 보이는 선택 칩 (여러 개 · 하나 모두)
export function Opt({ on, onClick, children, tone }) {
  return (
    <button type="button" className={`dn-opt ${on ? 'on' : ''} ${tone || ''}`} aria-pressed={on ? 'true' : 'false'} onClick={onClick}>
      <span className="dn-cb" aria-hidden="true">{on && <svg width="10" height="10" viewBox="0 0 12 12"><path d="M2 6.5L5 9L10 3" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>}</span>
      {children}
    </button>
  )
}

// ── 정렬 탭 + 왼쪽 총 개수 + 오른쪽 보기 방식 ──
export function SortTabs({ items, value, onChange, total, unit = '개', right }) {
  return (
    <div className="dn-sortbar">
      <div className="dn-sorts" role="tablist">
        {items.map(([k, l]) => <button key={k} type="button" role="tab" aria-selected={value === k} className={value === k ? 'on' : ''} onClick={() => onChange(k)}>{l}</button>)}
      </div>
      <div className="dn-sortbar-r">
        {total != null && <span className="dn-total">총 <b>{num(total)}</b>{unit}</span>}
        {right}
      </div>
    </div>
  )
}

export function Pager({ page, pages, onChange, max = 10 }) {
  if (pages <= 1) return null
  const start = Math.max(1, Math.min(page - Math.floor(max / 2), pages - max + 1))
  const list = Array.from({ length: Math.min(max, pages) }, (_, i) => start + i)
  const go = n => { onChange(n); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  return (
    <nav className="dn-pager" aria-label="쪽 번호">
      <button type="button" disabled={page <= 1} onClick={() => go(page - 1)} aria-label="이전 쪽">‹</button>
      {list.map(n => <button key={n} type="button" className={n === page ? 'on' : ''} aria-current={n === page ? 'page' : undefined} onClick={() => go(n)}>{n}</button>)}
      <button type="button" disabled={page >= pages} onClick={() => go(page + 1)} aria-label="다음 쪽">›</button>
    </nav>
  )
}

// ── 목록 한 줄: 사진 | 이름 · 정보 · 배지 | 가격 칸 ──
export function Thumb({ src, alt = '', rank }) {
  const [bad, setBad] = useState(false)
  return (
    <div className="dn-thumb">
      {src && !bad ? <img src={src} alt={alt} loading="lazy" referrerPolicy="no-referrer" onError={() => setBad(true)} /> : <span className="dn-thumb-empty">사진 없음</span>}
      {rank != null && <span className="dn-rank">{rank}</span>}
    </div>
  )
}
export function Spec({ items }) {
  const list = items.filter(Boolean)
  return <p className="dn-spec">{list.map((x, i) => <span key={i}>{x}</span>)}</p>
}
export function Row({ to, thumb, title, kicker, spec, badges, side, check, rank }) {
  return (
    <li className={`dn-row ${check ? '' : 'nocheck'}`}>
      {check}
      <Link to={to} className="dn-row-thumb" tabIndex={-1} aria-hidden="true">{thumb}</Link>
      <div className="dn-row-main">
        {kicker && <span className="dn-kicker">{kicker}</span>}
        <Link to={to} className="dn-title">{rank != null && <em>{rank}</em>}{title}</Link>
        {spec}
        {badges && <div className="dn-badges">{badges}</div>}
      </div>
      <div className="dn-row-side">{side}</div>
    </li>
  )
}
// 오른쪽 가격 칸
export function PriceCell({ label, value, unit, note, tone, to, cta = '자세히' }) {
  return (
    <div className="dn-pricecell">
      <span className="dn-pl">{label}</span>
      <b className={`dn-pv ${tone || ''}`}>{value}{unit && <small>{unit}</small>}</b>
      {note && <span className="dn-pn">{note}</span>}
      {to && <Link to={to} className="dn-go">{cta}</Link>}
    </div>
  )
}

// 추천 메뉴 한 줄 (메뉴 추천 결과 · 메인 · 챗봇에서 같이 씀)
export function MenuRow({ m, rank }) {
  const pv = m.priceVsNormalPct
  return (
    <Row to={`/menus/${m.id}`} rank={rank}
      check={<CompareCheck item={{ id: m.id, name: m.name }} />}
      thumb={<Thumb src={m.imageUrl} alt={m.name} />}
      kicker={m.dishType}
      title={m.name}
      spec={<Spec items={[m.repTitle && `대표 레시피 · ${m.repTitle}`, m.cookMin && `${m.cookMin}분`, m.rating != null && `★ ${Number(m.rating).toFixed(1)} (후기 ${num(m.reviewCount)})`, m.recipeCount && `레시피 ${num(m.recipeCount)}개`]} />}
      badges={<>
        {m.recentlyEaten && <span className="v3-badge neutral">최근에 먹었어요</span>}
        <HotBadge pct={m.interestYoyPct} />
        {(m.ingredients || []).map(i => <PriceBadge key={i.ingredientId} label={i.name} pct={i.vsNormalPct} />)}
      </>}
      side={<PriceCell label="주재료 시세 · 평년 대비" value={pv == null ? '–' : `${pv > 0 ? '+' : pv < 0 ? '−' : ''}${Math.abs(pv).toFixed(0)}%`}
        tone={pv == null ? '' : pv > 0 ? 'up' : 'down'} note={pv == null ? '시세 정보 없음' : pv < 0 ? '평소보다 싸요' : pv > 0 ? '평소보다 비싸요' : '평소와 같아요'} to={`/menus/${m.id}`} cta="메뉴 보기" />} />
  )
}

// 레시피 한 줄 (레시피 검색 · 냉장고 털기)
export function RecipeRow({ r, extraBadges, side }) {
  const ok = costOk(r)
  return (
    <Row to={`/recipes/${r.id}`}
      thumb={<Thumb src={r.imageUrl} alt={r.title} />}
      kicker={r.dishType || '기타'}
      title={r.title}
      spec={<Spec items={[r.cookMin != null && `${r.cookMin}분`, r.servings && `${r.servings}인분`, `조회 ${num(r.views)}`, `후기 ${num(r.reviewCount)}`, r.rating && `★ ${r.rating}`]} />}
      badges={<>
        {r.reliability === 'REL_A' && <span className="v3-badge hot">정량 레시피</span>}
        {r.proteinPer1000 && ok && r.costPerServing >= 1000 ? <span className="v3-badge down">천원당 단백질 {num(r.proteinPer1000, 1)}g</span> : null}
        <FactBadges r={r} />
        {extraBadges}
      </>}
      side={side ?? <PriceCell label="1인분 재료비" value={ok ? won(r.costPerServing) : '–'} note={ok ? 'KAMIS 소매가 기준' : '가격 확인 재료 부족'} to={`/recipes/${r.id}`} cta="레시피 보기" />} />
  )
}

// ── 메뉴 비교 담기 (이 브라우저에만 저장, 최대 4개) ──
const KEY = 'omm_compare'
const read = () => { try { return JSON.parse(localStorage.getItem(KEY) || '[]') } catch { return [] } }
const listeners = new Set()
function write(v) { try { localStorage.setItem(KEY, JSON.stringify(v)) } catch {} listeners.forEach(f => f(v)) }
export function useCompare() {
  const [list, setList] = useState(read)
  useEffect(() => { listeners.add(setList); return () => listeners.delete(setList) }, [])
  return {
    list,
    has: id => list.some(x => x.id === id),
    toggle: item => write(list.some(x => x.id === item.id) ? list.filter(x => x.id !== item.id) : [...list, item].slice(-4)),
    clear: () => write([]),
    remove: id => write(list.filter(x => x.id !== id)),
  }
}
export function CompareCheck({ item }) {
  const c = useCompare()
  const on = c.has(item.id)
  return (
    <label className={`dn-check ${on ? 'on' : ''}`} title="비교에 담기">
      <input type="checkbox" checked={on} onChange={() => c.toggle(item)} aria-label={`${item.name} 비교에 담기`} />
      <span>비교</span>
    </label>
  )
}
export function CompareBar() {
  const c = useCompare()
  const nav = useNavigate()
  if (!c.list.length) return null
  return (
    <div className="dn-comparebar" role="region" aria-label="비교함">
      <b>비교함 {c.list.length}/4</b>
      <div className="dn-compare-items">{c.list.map(x => <span key={x.id}>{x.name}<button type="button" aria-label={`${x.name} 빼기`} onClick={() => c.remove(x.id)}>✕</button></span>)}</div>
      <button type="button" className="dn-btn line" onClick={c.clear}>비우기</button>
      <button type="button" className="dn-btn" disabled={c.list.length < 2} onClick={() => nav(`/compare?ids=${c.list.map(x => x.id).join(',')}`)}>{c.list.length < 2 ? '2개 이상 담아 주세요' : '비교하기'}</button>
    </div>
  )
}
