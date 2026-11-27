import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi } from '../components/ui'

export function Login() {
  const nav = useNavigate()
  const [sp] = useSearchParams()
  const next = (sp.get('next') || '/').startsWith('/') && !(sp.get('next') || '').startsWith('//') ? sp.get('next') || '/' : '/'   // 우리 사이트 안 주소만
  const [f, setF] = useState({ email: '', password: '' })
  const [err, setErr] = useState('')
  const submit = async e => {
    e.preventDefault(); setErr('')
    try { await api.login(f); nav(next) } catch (x) { setErr(x.message) }
  }
  return (
    <form className="auth" onSubmit={submit}>
      <h1>로그인</h1>
      <input className="input" type="email" placeholder="이메일" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="username" />
      <input className="input" type="password" placeholder="비밀번호" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} autoComplete="current-password" />
      {err && <p className="err">{err}</p>}
      <button className="btn primary wide">로그인</button>
      <p className="muted">처음이세요? <Link to="/signup">회원가입</Link></p>
    </form>
  )
}

// 재료 직접 입력: 글자를 치면 재료 사전에서 후보를 보여주고, 고르거나 Enter 로 추가 (사전에 없으면 입력한 글자 그대로 저장)
function IngredientInput({ items, onChange, placeholder, tone }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const sug = useApi(() => (q.trim() ? api.ingredients(q.trim(), 8) : Promise.resolve([])), [q])
  const add = it => {
    const name = (it?.name || q).trim()
    if (!name || items.some(x => x.name === name)) { setQ(''); return }
    onChange([...items, { ingredientId: it?.id ?? null, name }]); setQ(''); setOpen(false)
  }
  const onKey = e => {
    if (e.key === 'Enter') { e.preventDefault(); const exact = (sug.data || []).find(x => x.name === q.trim()); add(exact || null) }
    if (e.key === 'Backspace' && !q && items.length) onChange(items.slice(0, -1))
  }
  return (
    <div className="ing-input">
      <div className={`ing-box ${tone || ''}`}>
        {items.map(x => (
          <span key={x.name} className={`ing-tag ${x.ingredientId ? '' : 'free'}`} title={x.ingredientId ? '재료 사전과 연결됨' : '사전에 없는 재료 · 이름이 들어간 재료를 모두 제외'}>
            {x.name}<button type="button" aria-label={`${x.name} 지우기`} onClick={() => onChange(items.filter(y => y !== x))}>✕</button>
          </span>
        ))}
        <input value={q} placeholder={items.length ? '' : placeholder} onChange={e => { setQ(e.target.value); setOpen(true) }}
          onKeyDown={onKey} onFocus={() => setOpen(true)} onBlur={() => setTimeout(() => setOpen(false), 150)} />
      </div>
      {open && q.trim() && (
        <ul className="ing-sug">
          {(sug.data || []).filter(x => !items.some(y => y.ingredientId === x.id)).map(x => (
            <li key={x.id}><button type="button" onMouseDown={e => e.preventDefault()} onClick={() => add(x)}>{x.name}<small>{x.category || ''}</small></button></li>
          ))}
          {!(sug.data || []).some(x => x.name === q.trim()) && (
            <li><button type="button" className="free" onMouseDown={e => e.preventDefault()} onClick={() => add(null)}>‘{q.trim()}’ 그대로 추가<small>Enter</small></button></li>
          )}
        </ul>
      )}
    </div>
  )
}

export function TagPicker({ tags, want, exclude, onChange, wantItems = [], excludeItems = [], onItems }) {
  const flip = (list, id) => (list.includes(id) ? list.filter(x => x !== id) : [...list, id])
  return (
    <>
      <div className="filter-row"><span>먹고 싶은</span><div className="pick-col">
        <div className="chips">{tags.filter(t => t.kind === 'TAGKIND_WANT').map(t =>
          <button type="button" key={t.tagId} className={want.includes(t.tagId) ? 'on' : ''} onClick={() => onChange(flip(want, t.tagId), exclude)}>{t.label}</button>)}</div>
        {onItems && <IngredientInput items={wantItems} onChange={v => onItems(v, excludeItems)} placeholder="좋아하는 재료 직접 입력 (예: 버섯, 연어)" />}
      </div></div>
      <div className="filter-row"><span>빼고 싶은</span><div className="pick-col">
        <div className="chips">{tags.filter(t => t.kind === 'TAGKIND_EXCLUDE').map(t =>
          <button type="button" key={t.tagId} className={exclude.includes(t.tagId) ? 'on bad' : ''} onClick={() => onChange(want, flip(exclude, t.tagId))}>{t.label}</button>)}</div>
        {onItems && <IngredientInput items={excludeItems} onChange={v => onItems(wantItems, v)} tone="bad" placeholder="못 먹거나 싫은 재료 직접 입력 (예: 고수, 땅콩, 가지)" />}
        {onItems && <p className="hint">알레르기 · 싫어하는 재료를 적으면 그 재료가 들어간 레시피는 추천에서 빠져요.</p>}
      </div></div>
    </>
  )
}

export function Signup() {
  const nav = useNavigate()
  const tags = useApi(() => api.filterTags())
  const [f, setF] = useState({ email: '', password: '', nickname: '', householdSize: 2, wantTagIds: [], excludeTagIds: [], wantItems: [], excludeItems: [] })
  const [msg, setMsg] = useState({})
  const check = async () => { const r = await api.checkEmail(f.email); setMsg({ email: r.available ? '사용할 수 있어요' : '이미 가입된 이메일이에요' }) }
  const submit = async e => {
    e.preventDefault()
    if (f.password.length < 8) return setMsg({ err: '비밀번호는 8자 이상이에요' })
    try { await api.signup(f); await api.updateMe({ ...f, password: undefined }).catch(() => {}); nav('/login') } catch (x) { setMsg({ err: x.message }) }
  }
  return (
    <form className="auth wide" onSubmit={submit}>
      <h1>회원가입</h1>
      <div className="row"><input className="input" type="email" placeholder="이메일" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} />
        <button type="button" className="btn line" onClick={check}>중복 확인</button></div>
      {msg.email && <p className="muted">{msg.email}</p>}
      <input className="input" type="password" placeholder="비밀번호 (8자 이상)" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} autoComplete="new-password" />
      <input className="input" placeholder="닉네임" value={f.nickname} onChange={e => setF({ ...f, nickname: e.target.value })} />
      <div className="filter-row"><span>가구원 수</span><div className="chips">{[1, 2, 3, 4, 5, 6].map(n =>
        <button type="button" key={n} className={f.householdSize === n ? 'on' : ''} onClick={() => setF({ ...f, householdSize: n })}>{n}명</button>)}</div></div>
      {tags.data && <TagPicker tags={tags.data.tags} want={f.wantTagIds} exclude={f.excludeTagIds} onChange={(w, x) => setF({ ...f, wantTagIds: w, excludeTagIds: x })}
        wantItems={f.wantItems} excludeItems={f.excludeItems} onItems={(w, x) => setF({ ...f, wantItems: w, excludeItems: x })} />}
      {msg.err && <p className="err">{msg.err}</p>}
      <button className="btn primary wide">가입하기</button>
    </form>
  )
}
