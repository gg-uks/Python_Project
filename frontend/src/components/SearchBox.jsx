// 헤더 검색창: 메뉴 이름 자동완성 (GET /api/search/suggest · 엘라스틱서치) + 검색 → /search (상황 문장 추천 + ES 레시피 검색)
import { useEffect, useRef, useState } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { api } from '../api'

const EXAMPLES = ['비 오는 날 얼큰한 거', '오이 빼고 싼 고기 요리', '어제 회식해서 속이 안 좋아', '김치찌개']

export default function SearchBox() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [q, setQ] = useState('')
  const [sug, setSug] = useState([])
  const [open, setOpen] = useState(false)
  const [hi, setHi] = useState(-1)
  const box = useRef(null)
  useEffect(() => { setOpen(false) }, [pathname])
  useEffect(() => {
    const v = q.trim()
    if (v.length < 1 || /\s/.test(v) && v.length > 12) { setSug([]); return }      // 긴 문장은 자동완성 안 함
    let on = true
    const t = setTimeout(() => api.suggest(v).then(r => on && setSug((r.items || []).slice(0, 8)), () => on && setSug([])), 180)
    return () => { on = false; clearTimeout(t) }
  }, [q])
  useEffect(() => {
    const off = e => { if (box.current && !box.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', off); return () => document.removeEventListener('mousedown', off)
  }, [])
  const go = text => { const v = (text ?? q).trim(); setOpen(false); setHi(-1); if (v) { nav(`/search?q=${encodeURIComponent(v)}`); setQ('') } }
  const pick = m => { setOpen(false); setQ(''); nav(`/menus/${m.menuId}`) }
  const key = e => {
    if (!open || !sug.length) return
    if (e.key === 'ArrowDown') { e.preventDefault(); setHi(h => (h + 1) % sug.length) }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => (h <= 0 ? sug.length - 1 : h - 1)) }
    else if (e.key === 'Enter' && hi >= 0) { e.preventDefault(); pick(sug[hi]) }
    else if (e.key === 'Escape') setOpen(false)
  }
  return (
    <div className="dn-search-wrap" ref={box}>
      <form className="dn-search" role="search" onSubmit={e => { e.preventDefault(); go() }}>
        <input type="search" value={q} onChange={e => { setQ(e.target.value); setOpen(true); setHi(-1) }} onFocus={() => setOpen(true)} onKeyDown={key}
          placeholder="예: 비 오는 날 얼큰한 거" aria-label="메뉴 · 레시피 · 상황 검색" autoComplete="off"
          role="combobox" aria-expanded={open} aria-controls="dn-sug" />
        <button type="submit" aria-label="검색"><svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="7" fill="none" stroke="currentColor" strokeWidth="2.2" /><path d="M20 20L16.5 16.5" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /></svg></button>
      </form>
      {open && (
        <div className="dn-sug" id="dn-sug" role="listbox">
          {q.trim() && sug.length > 0 && <>
            <div className="dn-sug-h">메뉴 바로 가기</div>
            {sug.map((m, i) => (
              <button key={m.menuId} type="button" role="option" aria-selected={i === hi} className={i === hi ? 'on' : ''} onMouseDown={e => e.preventDefault()} onClick={() => pick(m)}>
                <b>{m.name}</b><small>{m.dishType}{m.recipeCount ? ` · 레시피 ${m.recipeCount.toLocaleString()}개` : ''}</small>
              </button>
            ))}
          </>}
          {q.trim()
            ? <button type="button" className="dn-sug-all" onMouseDown={e => e.preventDefault()} onClick={() => go()}>‘{q.trim()}’ 로 메뉴 추천 · 레시피 검색 ›</button>
            : <>
              <div className="dn-sug-h">이렇게 물어봐도 돼요</div>
              {EXAMPLES.map(x => <button key={x} type="button" onMouseDown={e => e.preventDefault()} onClick={() => go(x)}><b>{x}</b></button>)}
            </>}
        </div>
      )}
    </div>
  )
}
