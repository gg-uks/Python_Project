// OMM 도우미 챗봇: 오른쪽 아래 버튼 → 대화창
// 백엔드에 POST /api/chat 이 생기면 그걸 쓰고, 없으면 지금 있는 API(추천 · 시세 · 레시피 · 먹은 기록)로 규칙 답변
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate } from 'react-router-dom'
import { api, auth, isMock } from '../api'
import { num, won, costOk } from './ui'
import OmmMark from './OmmMark'

const BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')
const QUICK = [
  ['오늘 뭐 먹지?', '오늘 뭐 먹을지 추천해 줘'],
  ['싼 재료로 만들 메뉴', '요즘 싼 재료로 만들 메뉴 추천해 줘'],
  ['요즘 뜨는 메뉴', '요즘 뜨는 메뉴 알려 줘'],
  ['재료 시세 알아보기', '대파 시세 얼마야?'],
  ['냉장고 재료로 찾기', '냉장고에 감자랑 계란 있어'],
  ['이번 주 먹은 기록', '이번 주 먹은 기록 보여 줘'],
]
const WELCOME = () => ({
  from: 'bot', welcome: true,
  text: `안녕하세요${auth.nickname() ? `, ${auth.nickname()}님` : ''}! OMM 도우미예요.\n오늘 뭐 먹을지, 재료가 지금 싼지 같이 찾아 드릴게요. 아래에서 골라도 되고 편하게 물어봐도 돼요.`,
})
const now = () => new Date().toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' })

// ── 말 → 낱말 (조사 · 요청 표현 떼기) ──
const STOP = new Set('먹을지 먹을지는 뭐먹지 뭐먹을까 먹을래 먹고싶은 먹고싶다 땡기는 당기는 오늘 내일 지금 요즘 뭐 뭘 무엇 무슨 좀 좀더 하나 같은 거 것 걸 게 추천 추천해 추천해줘 알려 알려줘 해줘 줘 주세요 해 먹고 먹을 먹을까 먹지 싶어 싶은 먹고싶어 메뉴 음식 요리 레시피 만들 만들기 만드는 법 방법 있어 있는 있음 있고 냉장고 재료 시세 가격 얼마 얼마야 얼마예요 싼 싸게 저렴한 저렴 비싼 비싸 요즘 뜨는 유행 트렌드 인기 이번 주 기록 보여 보여줘 이랑 랑 하고 그리고 또 및 정도 거야 할까 수 있는 만한 저녁 점심 아침 간식 혼밥 간단한 간단히 빨리 빠른'.split(' '))
const JOSA = /(으로|에서|이랑|하고|에는|이나|부터|까지|처럼|보다|을|를|이|가|은|는|도|로|랑|와|과|의|에|만|요)$/
function words(t) {
  return t.replace(/[?!.~,·]/g, ' ').split(/\s+/).map(w => w.trim()).filter(Boolean)
    .map(w => (w.length > 2 ? w.replace(JOSA, '') : w)).filter(w => w.length >= 1 && !STOP.has(w) && !/^(먹을|먹고|먹지|먹자|추천|알려|보여|해줘)/.test(w))
}
// "오이 빼고 돼지고기" → 빼는 말 / 원하는 말
function parseWantAvoid(t) {
  const avoid = [], want = []
  const re = /([가-힣a-zA-Z]+)\s*(?:은|는|이|가|을|를)?\s*(?:빼고|말고|없이|제외하고|제외|싫어|못 ?먹어)/g
  let m; let rest = t
  while ((m = re.exec(t))) { avoid.push(m[1].replace(JOSA, '')); rest = rest.replace(m[0], ' ') }
  want.push(...words(rest).filter(w => !avoid.includes(w)))
  return { want: [...new Set(want)].slice(0, 4), avoid: [...new Set(avoid)] }
}
// 받침 있으면 을, 없으면 를
const eul = w => { const c = (w || '').charCodeAt(w.length - 1); return c >= 0xAC00 && c <= 0xD7A3 && (c - 0xAC00) % 28 ? '을' : '를' }
const ro = w => { const c = (w || '').charCodeAt(w.length - 1); const j = c >= 0xAC00 && c <= 0xD7A3 ? (c - 0xAC00) % 28 : 0; return j && j !== 8 ? '으로' : '로' }
const pct = v => (v == null ? '–' : `${v > 0 ? '▲' : v < 0 ? '▼' : ''} ${Math.abs(v).toFixed(0)}%`)
const menuCard = m => ({ to: `/menus/${m.id}`, img: m.imageUrl, title: m.name, sub: [m.dishType, m.cookMin && `${m.cookMin}분`, m.priceVsNormalPct != null && `주재료 평년 대비 ${pct(m.priceVsNormalPct)}`].filter(Boolean).join(' · ') })
const recipeCard = r => ({ to: `/recipes/${r.id}`, img: r.imageUrl, title: r.title, sub: [r.cookMin != null && `${r.cookMin}분`, costOk(r) && `1인분 ${won(r.costPerServing)}`, r.haveRatio != null && `가진 재료 ${Math.round(r.haveRatio * 100)}%`].filter(Boolean).join(' · ') })

async function findIngredients(ws) {
  const out = []
  for (const w of ws.slice(0, 5)) {
    const list = await api.ingredients(w).catch(() => [])
    const hit = list.find(i => i.name === w) || list.find(i => !i.seas && i.name.includes(w)) || null
    if (hit && !out.some(x => x.id === hit.id)) out.push(hit)
  }
  return out
}

// ── 규칙 답변 ──
async function ruleReply(text) {
  const t = text.trim()
  if (/^(안녕|하이|hi|hello|처음)/i.test(t)) return { ...WELCOME(), welcome: true }

  if (/먹은|기록|일기/.test(t)) {
    if (!auth.token()) return { text: '먹은 기록은 로그인하면 볼 수 있어요.', actions: [['로그인하기', '/login']] }
    const s = await api.mealSummary()
    if (!s.count) return { text: '이번 주에는 아직 기록이 없어요. 메뉴 화면에서 ‘먹었어요’를 누르면 여기서 요약해 드려요.', actions: [['메뉴 추천 보기', '/']] }
    const top = s.dishMix?.[0]
    return {
      text: `이번 주(${s.weekStart.slice(5)} ~ ${s.weekEnd.slice(5)}) ${s.count}끼를 기록했어요.\n· 열량 ${s.total.kcal != null ? num(s.total.kcal) + ' kcal' : '–'} (하루 평균 ${s.dailyAvg.kcal != null ? num(s.dailyAvg.kcal) : '–'})\n· 단백질 ${s.total.proteinG != null ? num(s.total.proteinG) + ' g' : '–'} · 나트륨 ${s.total.sodiumMg != null ? num(s.total.sodiumMg) + ' mg' : '–'}${top ? `\n· ${top.dishType}${eul(top.dishType)} 가장 많이 먹었어요 (${Math.round(top.pct)}%)` : ''}`,
      actions: [['먹은 기록 자세히', '/mypage?tab=meals'], ['다른 종류 추천', `@${top ? `${top.dishType} 말고 추천해 줘` : '오늘 뭐 먹지'}`]],
    }
  }

  if (/뜨는|유행|트렌드|요즘 인기|핫한/.test(t)) {
    const list = await api.trendMenusBy('rise', 5)
    return { text: '레시피 등록·후기와 유튜브 언급이 작년보다 많이 늘어난 메뉴예요.', cards: list.slice(0, 5).map(m => ({ to: `/menus/${m.id}`, img: m.imageUrl, title: m.name, sub: [m.dishType, m.yoyPct != null && `관심도 ${pct(m.yoyPct)}`].filter(Boolean).join(' · ') })), actions: [['트렌드 더 보기', '/trends']] }
  }

  const ws = words(t)
  if (/냉장고|남은 재료|있는 재료|집에|가지고 있|있어(요)?\s*[.!?]*$/.test(t) && !/추천/.test(t.replace(/냉장고/, '')) || /냉장고/.test(t)) {
    const ings = await findIngredients(ws)
    if (!ings.length) return { text: '어떤 재료가 있는지 알려 주세요. 예: “냉장고에 감자랑 계란 있어”', actions: [['냉장고 털기 화면', '/fridge']] }
    const list = await api.byIngredients(ings.map(i => i.id), 5)
    if (!list.length) return { text: `${ings.map(i => i.name).join(', ')}${ro(ings.at(-1).name)} 만들 레시피를 못 찾았어요. 재료를 더 알려 주세요.` }
    return { text: `${ings.map(i => i.name).join(', ')}${eul(ings.at(-1).name)} 가장 많이 쓰는 레시피예요.`, cards: list.slice(0, 5).map(recipeCard), actions: [['냉장고 털기에서 더 보기', '/fridge']] }
  }

  if (/시세|가격|얼마|비싸|싸\?|싸요|싼가/.test(t) && !/메뉴|추천/.test(t)) {
    const ings = await findIngredients(ws)
    if (!ings.length) {
      const s = await api.ingredientSummary()
      const lines = (s.items || []).slice(0, 6).map(i => `· ${i.name} ${num(i.avgPrice)}원/${i.unitLabel} (평년 대비 ${pct(i.vsNormalPct)})`)
      return { text: `요즘 시세가 많이 움직인 재료예요 (KAMIS 소매가 ${s.ym || ''}).\n${lines.join('\n')}`, actions: [['재료 탐색', '/explore']] }
    }
    const s = await api.ingredientSummary(ings.map(i => i.id))
    const lines = (s.items || []).map(i => i.avgPrice == null ? `· ${i.name}: 시세 정보가 아직 없어요` : `· ${i.name} ${num(i.avgPrice)}원/${i.unitLabel} — 평년보다 ${i.vsNormalPct == null ? '정보 없음' : `${Math.abs(i.vsNormalPct).toFixed(0)}% ${i.vsNormalPct > 0 ? '비싸요' : '싸요'}`}`)
    return { text: `KAMIS 소매가 ${s.ym || ''} 기준이에요.\n${lines.join('\n')}`, actions: ings.slice(0, 2).map(i => [`${i.name} 시세 자세히`, `/explore?id=${i.id}`]).concat([[`${ings[0].name} 들어간 메뉴`, `@${ings[0].name} 들어간 메뉴 추천해 줘`]]) }
  }

  if (/레시피|만드는|만들|만드는 법|조리법/.test(t) && ws.length) {
    const r = await api.recipes({ q: ws.join(' '), size: 5, sort: 'views', prefs: 'off' })
    if (!r.items.length) return { text: `‘${ws.join(' ')}’ 레시피를 못 찾았어요. 다른 이름으로 물어봐 주세요.` }
    return { text: `‘${ws.join(' ')}’ 인기 레시피예요. 재료와 조리 순서는 눌러서 볼 수 있어요.`, cards: r.items.slice(0, 5).map(recipeCard), actions: [['검색 결과 더 보기', `/recipes?q=${encodeURIComponent(ws.join(' '))}`]] }
  }

  // 기본: 메뉴 추천
  const { want, avoid } = parseWantAvoid(t)
  const mode = /싼|싸게|저렴|가성비|절약|아끼/.test(t) ? 'price' : /유행|핫|요즘/.test(t) ? 'trend' : 'balance'
  let res = await api.recommend({ want: want.join(',') || undefined, avoid: avoid.join(',') || undefined, mode, limit: 5 })
  let note = ''
  if (!res.items.length && want.length) {
    res = await api.recommend({ avoid: avoid.join(',') || undefined, mode, limit: 5 })
    note = `‘${want.join(', ')}’에 딱 맞는 메뉴는 못 찾아서, `
  }
  if (!res.items.length) return { text: '조건에 맞는 메뉴를 못 찾았어요. 조건을 줄여서 다시 물어봐 주세요.' }
  const cond = [want.length && !note && `${want.join(', ')}`, avoid.length && `${avoid.join(', ')} 빼고`, mode === 'price' && '싼 재료 위주', mode === 'trend' && '요즘 유행 위주'].filter(Boolean).join(' · ')
  const q = new URLSearchParams(Object.entries({ want: note ? '' : want.join(','), avoid: avoid.join(','), mode }).filter(([, v]) => v))
  return {
    text: `${note}${cond ? `${cond} 조건으로 ` : '요즘 시세와 관심도를 보고 '}골라 봤어요.`,
    cards: res.items.slice(0, 5).map(menuCard),
    actions: [['추천 결과 전체 보기', `/recommend?${q}`], ['더 싸게', `@${[...want, ...avoid.map(a => `${a} 빼고`)].join(' ')} 싼 재료로 추천해 줘`]],
  }
}

// 백엔드 AI 챗봇(/api/chat · Gemini)이 켜져 있으면 사용, 꺼져 있거나 실패하면 규칙 답변
let status = null
export async function chatStatus() {
  if (isMock) return { enabled: false }
  status ??= fetch(`${BASE}/api/chat/status`).then(r => (r.ok ? r.json() : { enabled: false })).catch(() => ({ enabled: false }))
  return status
}
async function reply(text, history) {
  const st = await chatStatus()
  if (st.enabled) {
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (auth.token()) headers.Authorization = `Bearer ${auth.token()}`
      const res = await fetch(`${BASE}/api/chat`, { method: 'POST', headers, body: JSON.stringify({ message: text, history: history.slice(-11, -1).filter(m => m.text).map(m => ({ role: m.from === 'me' ? 'user' : 'assistant', content: m.text.slice(0, 1900) })) }) })
      if (res.ok) { const d = await res.json(); return { text: d.reply, cards: d.cards, actions: d.actions, ai: true } }
      const detail = await res.json().then(d => d.detail).catch(() => null)
      if (res.status === 429) return { text: `${detail || 'AI 사용량을 넘었어요.'} 그동안은 기본 답변으로 도와드릴게요.`, ...(await ruleReply(text).then(r => ({ cards: r.cards, actions: r.actions }))) }
      if (res.status === 503) status = Promise.resolve({ enabled: false })
    } catch { /* 네트워크 오류 → 규칙 답변 */ }
  }
  return ruleReply(text)
}

const STORE = 'omm_chat'
const load = () => { try { return JSON.parse(sessionStorage.getItem(STORE) || 'null') } catch { return null } }

export default function ChatBot() {
  const nav = useNavigate()
  const { pathname } = useLocation()
  const [open, setOpen] = useState(false)
  const [tip, setTip] = useState(() => { try { return !localStorage.getItem('omm_chat_tip') } catch { return true } })
  const [msgs, setMsgs] = useState(() => load() || [{ ...WELCOME(), at: now() }])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [ai, setAi] = useState(false)
  useEffect(() => { chatStatus().then(x => setAi(!!x.enabled)) }, [])
  const body = useRef(null)
  const input = useRef(null)
  useEffect(() => { try { sessionStorage.setItem(STORE, JSON.stringify(msgs.slice(-40))) } catch {} }, [msgs])
  useEffect(() => { body.current?.scrollTo({ top: body.current.scrollHeight, behavior: 'smooth' }) }, [msgs, busy, open])
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 50) }, [open])
  useEffect(() => { const f = e => e.key === 'Escape' && setOpen(false); window.addEventListener('keydown', f); return () => window.removeEventListener('keydown', f) }, [])
  if (pathname.startsWith('/admin')) return null

  const send = async raw => {
    const t = (raw ?? text).trim()
    if (!t || busy) return
    setText('')
    const mine = { from: 'me', text: t, at: now() }
    const next = [...msgs, mine]
    setMsgs(next); setBusy(true)
    try {
      const r = await reply(t, next)
      setMsgs(m => [...m, { from: 'bot', ...r, at: now() }])
    } catch (e) {
      setMsgs(m => [...m, { from: 'bot', text: `답을 가져오다 문제가 생겼어요. 잠시 뒤 다시 물어봐 주세요. (${e.message})`, at: now() }])
    } finally { setBusy(false) }
  }
  const act = ([label, to]) => {
    if (to.startsWith('@')) return send(to.slice(1))
    nav(to)
    if (window.innerWidth < 640) setOpen(false)
  }
  const toggle = () => { setOpen(!open); setTip(false); try { localStorage.setItem('omm_chat_tip', '1') } catch {} }

  return (
    <>
      {!open && tip && (
        <div className="cb-tip" role="status">
          오늘 뭐 먹을지 물어보세요
          <button type="button" aria-label="안내 닫기" onClick={() => { setTip(false); try { localStorage.setItem('omm_chat_tip', '1') } catch {} }}>✕</button>
        </div>
      )}
      <button type="button" className={`cb-launch ${open ? 'open' : ''}`} aria-label={open ? '도우미 닫기' : 'OMM 도우미 열기'} aria-expanded={open} onClick={toggle}>
        {open
          ? <svg width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6L18 18M18 6L6 18" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" /></svg>
          : <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3h11A2.5 2.5 0 0 1 20 5.5v8a2.5 2.5 0 0 1-2.5 2.5H10l-4.2 3.6c-.5.4-1.3.1-1.3-.6V16A2.5 2.5 0 0 1 4 13.5z" fill="currentColor" /><circle cx="8.5" cy="9.5" r="1.2" fill="#1F3A5F" /><circle cx="12" cy="9.5" r="1.2" fill="#1F3A5F" /><circle cx="15.5" cy="9.5" r="1.2" fill="#1F3A5F" /></svg>}
      </button>
      {open && (
        <section className="cb-panel" role="dialog" aria-label="OMM 도우미">
          <header className="cb-head">
            <span className="cb-ava" aria-hidden="true"><OmmMark size={34} /></span>
            <div className="cb-who"><b>OMM 도우미 {ai && <em className="cb-ai">AI</em>}</b><span><i /> {ai ? 'Gemini AI로 답해요' : '보통 바로 답해요'}</span></div>
            <button type="button" className="cb-hbtn" onClick={() => setMsgs([{ ...WELCOME(), at: now() }])} title="대화 새로 시작">
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12a8 8 0 1 0 2.4-5.7M4 4v4h4" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" /></svg>
              <span className="sr">대화 새로 시작</span>
            </button>
            <button type="button" className="cb-hbtn" onClick={() => setOpen(false)} title="닫기">
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6L18 18M18 6L6 18" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" /></svg>
              <span className="sr">닫기</span>
            </button>
          </header>
          <div className="cb-body" ref={body} aria-live="polite">
            <div className="cb-day"><span>오늘</span></div>
            {msgs.map((m, i) => m.from === 'me' ? (
              <div key={i} className="cb-me"><span className="cb-at">{m.at}</span><p>{m.text}</p></div>
            ) : (
              <div key={i} className="cb-bot">
                <span className="cb-ava sm" aria-hidden="true"><OmmMark size={28} /></span>
                <div className="cb-bot-col">
                  <span className="cb-name">OMM 도우미</span>
                  <div className={`cb-bubble ${m.welcome ? 'welcome' : ''}`}>
                    <p>{m.text}</p>
                    {m.welcome && <div className="cb-menu">{QUICK.map(([l, q]) => <button key={l} type="button" onClick={() => send(q)}>{l}<svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true"><path d="M9 5l7 7-7 7" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg></button>)}</div>}
                  </div>
                  {m.cards?.length > 0 && (
                    <div className="cb-cards">
                      {m.cards.map((c, k) => (
                        <Link key={k} to={c.to} className="cb-card" onClick={() => window.innerWidth < 640 && setOpen(false)}>
                          <span className="cb-img">{c.img && <img src={c.img} alt="" loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none' }} />}</span>
                          <span className="cb-ct"><b>{c.title}</b>{c.sub && <small>{c.sub}</small>}</span>
                        </Link>
                      ))}
                    </div>
                  )}
                  {m.actions?.length > 0 && <div className="cb-acts">{m.actions.map((a, k) => <button key={k} type="button" onClick={() => act(a)}>{a[0]}</button>)}</div>}
                  <span className="cb-at">{m.at}</span>
                </div>
              </div>
            ))}
            {busy && <div className="cb-bot"><span className="cb-ava sm" aria-hidden="true"><OmmMark size={28} /></span><div className="cb-bubble cb-typing" aria-label="답변 쓰는 중"><i /><i /><i /></div></div>}
          </div>
          {!busy && msgs.length > 1 && (
            <div className="cb-suggest">{QUICK.slice(0, 4).map(([l, q]) => <button key={l} type="button" onClick={() => send(q)}>{l}</button>)}</div>
          )}
          <form className="cb-input" onSubmit={e => { e.preventDefault(); send() }}>
            <input ref={input} value={text} onChange={e => setText(e.target.value)} maxLength={200} placeholder="예: 오이 빼고 돼지고기 요리 추천해 줘" aria-label="도우미에게 물어보기" />
            <button type="submit" disabled={!text.trim() || busy} aria-label="보내기">
              <svg width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12L20 4L14 20L11 13Z" fill="currentColor" /></svg>
            </button>
          </form>
          <p className="cb-foot">{ai ? 'AI 답변은 틀릴 수 있어요. 숫자는 카드를 눌러 화면에서 확인해 주세요.' : 'OMM 데이터(만개의레시피 · KAMIS · 식약처)로 답해요. 틀릴 수 있으니 화면에서 한 번 더 확인해 주세요.'}</p>
        </section>
      )}
    </>
  )
}
