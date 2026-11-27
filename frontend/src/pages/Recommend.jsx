// 메뉴 추천: 메인(맨 위 조건표 + 내 취향 메뉴 + 시세·트렌드 순위) / 추천 결과(조건표 + 정렬 탭 + 목록)
import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, auth } from '../api'
import { useApi, State, num } from '../components/ui'
import { Source, wonUnit } from '../components/v3'
import { FilterTable, FRow, Opt, SortTabs, Pager, MenuRow, Thumb } from '../components/dn'
import { TasteBox } from '../components/Facts'

export const MODES = [
  ['balance', '균형', '시세와 요즘 관심도를 같이 봐요'],
  ['price', '시세 우선', '평년보다 싼 재료가 많은 메뉴부터'],
  ['trend', '유행 우선', '레시피 등록·후기와 유튜브 언급이 늘어난 메뉴부터'],
]
const PRESET_WANTS = ['얼큰한 국물', '고기', '한식', '면 요리', '간단한 한 그릇', '해산물', '매콤한', '다이어트']
const PRESET_AVOIDS = ['오이', '가지', '버섯', '해산물', '매운 음식', '밀가루']
// 화면 항목 이름 → 추천 API 가 찾을 수 있는 말 (태그로 있는 항목은 태그 번호로 보냄)
// 추천 API 는 메뉴 이름 · 요리 종류 · 대표 레시피 재료 · 맛 표현에서 글자로 찾아서, '얼큰한 국물' 같은 문장은 못 찾음
const WANT_MAP = {
  '얼큰한 국물': '얼큰,칼칼', '고기': '고기', '한식': '국·찌개,반찬·메인,밥·죽,김치', '면 요리': '면·분식,국수,라면,파스타,우동,칼국수',
  '간단한 한 그릇': '덮밥,볶음밥,비빔밥,밥·죽', '해산물': '새우,오징어,조개,고등어,연어,낙지,홍합,꽃게,바지락,전복,문어,주꾸미',
  '매콤한': '매콤,매운,칼칼,얼큰', '다이어트': '샐러드,닭가슴살,두부,곤약',
}
const AVOID_MAP = {
  '매운 음식': '고추,고춧가루,청양고추,고추장,매운', '밀가루': '밀가루,부침가루,튀김가루',
  '해산물': '새우,오징어,조개,고등어,연어,낙지,홍합,꽃게,바지락,전복,문어,주꾸미,해물',
}
export function toApi(want = [], avoid = [], tags = []) {
  const ids = [], w = [], a = []
  const tagOf = (label, kind) => tags.find(t => t.label === label && t.kind === kind)
  want.forEach(l => { const t = tagOf(l, 'TAGKIND_WANT'); t ? ids.push(t.tagId) : w.push(...split(WANT_MAP[l] || l)) })
  avoid.forEach(l => { const t = tagOf(l, 'TAGKIND_EXCLUDE'); t ? ids.push(t.tagId) : a.push(...split(AVOID_MAP[l] || l)) })
  return { want: uniq(w).join(',') || undefined, avoid: uniq(a).join(',') || undefined, tags: ids.join(',') || undefined }
}

export const split = s => (s || '').split(',').map(x => x.trim()).filter(Boolean)
const uniq = a => [...new Set(a.filter(Boolean))]

// 로그인한 회원의 저장된 취향 (먹고 싶은 · 제외할) → 글자 목록
export function useMyPrefs() {
  const loggedIn = Boolean(auth.token())
  const tags = useApi(() => api.filterTags())
  const me = useApi(() => (loggedIn ? api.me().catch(() => null) : Promise.resolve(null)))
  return useMemo(() => {
    const byId = Object.fromEntries((tags.data?.tags || []).map(t => [t.tagId, t.label]))
    const d = me.data
    return {
      loading: tags.loading || me.loading,
      tags: tags.data?.tags || [],
      want: d ? uniq([...(d.wantTagIds || []).map(id => byId[id]), ...(d.wantItems || []).map(x => x.name)]) : [],
      avoid: d ? uniq([...(d.excludeTagIds || []).map(id => byId[id]), ...(d.excludeItems || []).map(x => x.name)]) : [],
    }
  }, [tags.data, tags.loading, me.data, me.loading])
}

// ── 조건표 (메인 · 결과 화면 공통) ──
export function ConditionTable({ init, tags = [], title, sub, compact, onSubmit }) {
  const sits = useApi(() => api.situations())
  const [want, setWant] = useState(init.want || [])
  const [avoid, setAvoid] = useState(init.avoid || [])
  const [situation, setSituation] = useState(init.situation || '')
  const [mode, setMode] = useState(init.mode || 'balance')
  const [wt, setWt] = useState('')
  const [at, setAt] = useState('')
  const key = JSON.stringify(init)
  useEffect(() => { setWant(init.want || []); setAvoid(init.avoid || []); setSituation(init.situation || ''); setMode(init.mode || 'balance') }, [key]) // eslint-disable-line
  const wantOpts = uniq([...PRESET_WANTS, ...tags.filter(t => t.kind === 'TAGKIND_WANT').map(t => t.label), ...want])
  const avoidOpts = uniq([...PRESET_AVOIDS, ...tags.filter(t => t.kind === 'TAGKIND_EXCLUDE').map(t => t.label), ...avoid])
  const tog = (list, set, v) => set(list.includes(v) ? list.filter(x => x !== v) : [...list, v])
  const add = (txt, setTxt, list, set) => { const v = txt.trim(); if (v && !list.includes(v)) set([...list, ...split(v)]); setTxt('') }
  const submit = e => {
    e?.preventDefault()
    const w = uniq([...want, ...split(wt)]), a = uniq([...avoid, ...split(at)])
    onSubmit({ want: w, avoid: a, situation, mode })
  }
  const sit = (sits.data || []).find(s => String(s.clusterId) === String(situation))
  const summary = [want.length && `먹고 싶은 ${want.length}`, avoid.length && `제외 ${avoid.length}`, sit && sit.name, MODES.find(m => m[0] === mode)[1]].filter(Boolean).join(' · ')
  return (
    <form onSubmit={submit} aria-label="조건 골라 메뉴 추천받기">
      <FilterTable className={compact ? 'compact' : ''}
        title={<>{title}{sub && <small>{sub}</small>}</>}
        right={<button type="button" className="dn-btn line" onClick={() => { setWant([]); setAvoid([]); setSituation(''); setMode('balance') }}>초기화</button>}>
        <FRow label="먹고 싶은 음식">
          <div className="dn-opts">{wantOpts.map(o => <Opt key={o} on={want.includes(o)} onClick={() => tog(want, setWant, o)}>{o}</Opt>)}</div>
          <div className="dn-inline">
            <input value={wt} onChange={e => setWt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(wt, setWt, want, setWant) } }} placeholder="직접 입력 (예: 김치, 닭고기) 후 Enter" aria-label="먹고 싶은 음식 직접 입력" />
            <button type="button" onClick={() => add(wt, setWt, want, setWant)}>추가</button>
          </div>
        </FRow>
        <FRow label="제외할 음식" help="메뉴 이름이나 대표 레시피 재료에 들어 있으면 빼요">
          <div className="dn-opts">{avoidOpts.map(o => <Opt key={o} tone="avoid" on={avoid.includes(o)} onClick={() => tog(avoid, setAvoid, o)}>{o}</Opt>)}</div>
          <div className="dn-inline">
            <input value={at} onChange={e => setAt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); add(at, setAt, avoid, setAvoid) } }} placeholder="못 먹는 재료 · 메뉴 직접 입력 후 Enter" aria-label="제외할 음식 직접 입력" />
            <button type="button" onClick={() => add(at, setAt, avoid, setAvoid)}>추가</button>
          </div>
        </FRow>
        <FRow label="지금 상황" help="조리시간 · 재료비로 나눈 메뉴 4유형">
          <div className="dn-opts">
            <Opt on={!situation} onClick={() => setSituation('')}>상관없음</Opt>
            {(sits.data || []).map(s => <Opt key={s.clusterId} on={String(situation) === String(s.clusterId)} onClick={() => setSituation(String(s.clusterId))}>{s.name}<span className="dn-optsub">{s.description}</span></Opt>)}
          </div>
        </FRow>
        <FRow label="추천 기준" help={MODES.find(m => m[0] === mode)[2]}>
          <div className="dn-opts">{MODES.map(([k, l]) => <Opt key={k} on={mode === k} onClick={() => setMode(k)}>{l}</Opt>)}</div>
        </FRow>
        <div className="dn-ftable-foot">
          <span className="dn-sum">선택한 조건: <b>{summary}</b></span>
          <button type="submit" className="dn-btn big">메뉴 추천 받기</button>
        </div>
      </FilterTable>
    </form>
  )
}

const toQuery = c => {
  const q = new URLSearchParams()
  if (c.want?.length) q.set('want', c.want.join(','))
  if (c.avoid?.length) q.set('avoid', c.avoid.join(','))
  if (c.situation) q.set('situation', c.situation)
  q.set('mode', c.mode || 'balance')
  return q
}

// ── 메인 ──
export function Main() {
  const nav = useNavigate()
  const pref = useMyPrefs()
  const loggedIn = Boolean(auth.token())
  const init = useMemo(() => ({ want: [], avoid: pref.avoid, mode: 'balance' }), [pref.avoid.join(',')]) // eslint-disable-line
  return (
    <div className="v3-page">
      <div className="dn-hero">
        <ConditionTable init={init} tags={pref.tags} title="오늘 뭐 먹지? 조건 골라 메뉴 추천받기"
          sub="먹고 싶은 것 · 빼고 싶은 것을 체크하면 요즘 시세와 관심도를 보고 메뉴를 골라 드려요"
          onSubmit={c => nav(`/recommend?${toQuery(c)}`)} />
        <aside className="dn-side">
          {loggedIn ? <MyBox /> : (
            <div className="dn-box dn-login">
              <div className="dn-box-body">
                <p style={{ margin: 0 }}>로그인하면 <b>내 취향 맞춤 메뉴</b>와 <b>먹은 기록</b>을 볼 수 있어요.</p>
                <Link to="/login" className="dn-btn">로그인</Link>
                <div className="dn-login-links"><Link to="/signup">회원가입</Link><Link to="/recipes">레시피 둘러보기</Link></div>
              </div>
            </div>
          )}
          <PriceRank kind="down" />
        </aside>
      </div>

      {loggedIn && <SimilarRow />}
      <PickRow pref={pref} loggedIn={loggedIn} />

      <div className="dn-grid3 four">
        <PriceRank kind="up" />
        <TrendRank />
        <TasteBox />
        <div className="dn-box">
          <div className="dn-box-head">바로 가기</div>
          <div className="dn-box-body dn-shortcuts">
            <Link to="/recipes?sort=cost">1인분 싼 레시피<span>재료비 낮은 순</span></Link>
            <Link to="/recipes?sort=value">가성비 레시피<span>천 원당 단백질</span></Link>
            <Link to="/fridge">냉장고 털기<span>있는 재료로 찾기</span></Link>
            <Link to="/explore">재료 시세<span>평년 대비 · 관심도</span></Link>
          </div>
        </div>
      </div>
    </div>
  )
}

function MyBox() {
  const sum = useApi(() => api.mealSummary().catch(() => null))
  const s = sum.data
  return (
    <div className="dn-box">
      <div className="dn-box-head">{auth.nickname() || '내'}님 <Link to="/mypage?tab=prefs">취향 설정</Link></div>
      <div className="dn-box-body">
        <span>이번 주 먹은 기록</span>
        <div className="dn-mini">
          <div><b>{s ? s.count : '–'}</b><span>끼니</span></div>
          <div><b>{s?.total?.kcal != null ? num(s.total.kcal) : '–'}</b><span>kcal</span></div>
          <div><b>{s?.dishMix?.[0]?.dishType || '–'}</b><span>많이 먹은 종류</span></div>
        </div>
        <Link to="/mypage?tab=meals" className="dn-btn line">먹은 기록 보기</Link>
      </div>
    </div>
  )
}

function PriceRank({ kind }) {
  const d = useApi(() => api.ingredientSummary())
  const items = (d.data?.items || []).filter(i => i.vsNormalPct != null && (kind === 'down' ? i.vsNormalPct < 0 : i.vsNormalPct > 0))
    .sort((a, b) => (kind === 'down' ? a.vsNormalPct - b.vsNormalPct : b.vsNormalPct - a.vsNormalPct)).slice(0, 5)
  return (
    <div className="dn-box">
      <div className="dn-box-head">{kind === 'down' ? '평년보다 싼 재료' : '평년보다 비싼 재료'}<Link to="/explore">전체 시세</Link></div>
      <div className="dn-box-body">
        <State loading={d.loading} error={d.error} empty={d.data && !items.length && '해당 재료가 없어요'}>
          <ol className="dn-rankl">
            {items.map((i, k) => (
              <li key={i.ingredientId}><Link to={`/explore?id=${i.ingredientId}`}>
                <span className="dn-rn">{k + 1}</span>
                <span className="dn-rn-name">{i.name} <small className="muted">{wonUnit(i.avgPrice, i.unitLabel)}</small></span>
                <span className={`dn-rn-v ${kind}`}>{i.vsNormalPct > 0 ? '▲' : '▼'} {Math.abs(i.vsNormalPct).toFixed(0)}%</span>
              </Link></li>
            ))}
          </ol>
        </State>
        {d.data?.ym && <span className="dn-fhelp">KAMIS 소매가 {d.data.ym} · 평년 대비</span>}
      </div>
    </div>
  )
}

function TrendRank() {
  const d = useApi(() => api.trendMenusBy('rise', 5))
  return (
    <div className="dn-box">
      <div className="dn-box-head">요즘 뜨는 메뉴<Link to="/trends">트렌드 더 보기</Link></div>
      <div className="dn-box-body">
        <State loading={d.loading} error={d.error}>
          <ol className="dn-rankl">
            {(d.data || []).slice(0, 5).map((m, k) => (
              <li key={m.id}><Link to={`/menus/${m.id}`}>
                <span className="dn-rn">{k + 1}</span>
                <span className="dn-rn-name">{m.name}</span>
                <span className="dn-rn-v hot">{m.yoyPct != null ? `▲ ${Math.round(m.yoyPct)}%` : ''}</span>
              </Link></li>
            ))}
          </ol>
        </State>
      </div>
    </div>
  )
}

// 내 취향 맞춤 메뉴 (로그인 안 했으면 지금 추천)
// 먹은 기록 기반: 최근 먹은 메뉴와 비슷한 메뉴 (GET /api/recommend/similar)
function SimilarRow() {
  const r = useApi(() => api.similarMenus(6).catch(() => null))
  const D = r.data
  if (!r.loading && !D?.items?.length) return null
  return (
    <section className="dn-sec" aria-labelledby="similar">
      <div className="dn-sec-head">
        <h2 id="similar">{D?.basedOn?.length ? '최근 먹은 메뉴와 비슷한 메뉴' : '먹은 기록으로 추천'}<small>{D?.basedOn?.length ? '먹은 기록 · 메뉴 유사도로 골랐어요' : '먹은 기록을 남기면 비슷한 메뉴를 골라 드려요'}</small></h2>
        <Link to="/mypage?tab=meals">먹은 기록 ›</Link>
      </div>
      {D?.basedOn?.length > 0 && <div className="dn-pref"><span className="v3-tag plain">최근 먹은 · {D.basedOn.slice(0, 4).map(b => `${b.name}${b.times > 1 ? ` ${b.times}번` : ''}`).join(' · ')}</span></div>}
      <State loading={r.loading}>
        <div className="dn-pcards">
          {D?.items.map(m => (
            <Link key={m.menuId} to={`/menus/${m.menuId}`} className="dn-pcard">
              <Thumb src={m.imageUrl} alt={m.name} />
              <small>{m.dishType}{m.cookMin ? ` · ${m.cookMin}분` : ''}</small>
              <b>{m.name}</b>
              <span className="sr-why">{m.reasons[0]}</span>
            </Link>
          ))}
        </div>
      </State>
    </section>
  )
}

function PickRow({ pref, loggedIn }) {
  const ready = !pref.loading
  const q = { want: pref.want.join(',') || undefined, avoid: pref.avoid.join(',') || undefined, mode: 'balance', sort: 'rec', limit: 6 }
  const list = useApi(() => (ready ? api.recommend({ ...toApi(pref.want, pref.avoid, pref.tags), mode: 'balance', sort: 'rec', limit: 6 }) : new Promise(() => {})), [ready, q.want, q.avoid])
  const has = pref.want.length + pref.avoid.length > 0
  const more = new URLSearchParams(Object.entries({ want: q.want, avoid: q.avoid, mode: 'balance' }).filter(([, v]) => v))
  return (
    <section className="dn-sec" aria-labelledby="picks">
      <div className="dn-sec-head">
        <h2 id="picks">{loggedIn && has ? `${auth.nickname() || '내'}님 취향 맞춤 메뉴` : '오늘의 추천 메뉴'}
          <small>{has ? '저장한 취향으로 골랐어요' : '시세 · 관심도 기준'}</small></h2>
        <Link to={`/recommend?${more}`}>더 보기 ›</Link>
      </div>
      <div className="dn-pref">
        {has ? <>
          {pref.want.length > 0 && <span className="v3-tag">먹고 싶은 · {pref.want.join(' · ')}</span>}
          {pref.avoid.length > 0 && <span className="v3-tag avoid">제외 · {pref.avoid.join(' · ')}</span>}
          <Link to="/mypage?tab=prefs" className="v3-more">취향 바꾸기</Link>
        </> : loggedIn ? <span>취향을 저장하면 여기서 맞춰 보여 드려요. <Link to="/mypage?tab=prefs" className="v3-more">취향 설정하기</Link></span>
          : <span><Link to="/login" className="v3-more">로그인</Link>하면 내 취향에 맞춰 드려요.</span>}
      </div>
      <State loading={list.loading} error={list.error} empty={list.data && !list.data.items.length && '취향에 맞는 메뉴를 못 찾았어요. 위 조건표에서 직접 골라 보세요.'}>
        <div className="dn-pcards">
          {list.data?.items.map(m => {
            const pv = m.priceVsNormalPct
            return (
              <Link key={m.id} to={`/menus/${m.id}`} className="dn-pcard">
                <Thumb src={m.imageUrl} alt={m.name} />
                <small>{m.dishType}{m.cookMin ? ` · ${m.cookMin}분` : ''}</small>
                <b>{m.name}</b>
                <span className={`dn-pv ${pv == null ? '' : pv > 0 ? 'up' : 'down'}`}>{pv == null ? '시세 –' : `주재료 ${pv > 0 ? '+' : '−'}${Math.abs(pv).toFixed(0)}%`}</span>
                {m.recentlyEaten && <small>최근에 먹었어요</small>}
              </Link>
            )
          })}
        </div>
      </State>
    </section>
  )
}

// ── 추천 결과 ──
const SORTS = [['rec', '추천순'], ['cheap', '싼 재료 많은 순'], ['hot', '관심도 높은 순'], ['rating', '별점 높은 순']]
const PAGE = 10

export function Candidates() {
  const nav = useNavigate()
  const [sp, setSp] = useSearchParams()
  const p = Object.fromEntries(sp)
  const pref = useMyPrefs()
  const page = +p.page || 1
  const { data, loading, error } = useApi(() => (pref.loading ? new Promise(() => {}) : api.recommend({ ...toApi(split(p.want), split(p.avoid), pref.tags), situation: p.situation, mode: p.mode || 'balance', sort: p.sort || 'rec', page, limit: PAGE })), [sp.toString(), pref.loading])
  const set = (k, v) => setSp(Object.fromEntries(Object.entries({ ...p, [k]: v, ...(k !== 'page' ? { page: '' } : {}) }).filter(([, x]) => x)))
  const pages = data ? Math.min(20, Math.max(1, Math.ceil(data.total / PAGE))) : 1
  const init = useMemo(() => ({ want: split(p.want), avoid: split(p.avoid), situation: p.situation || '', mode: p.mode || 'balance' }), [p.want, p.avoid, p.situation, p.mode])
  return (
    <div className="v3-page">
      <div className="v3-title-row"><div><h1>메뉴 추천 결과</h1><span className="v3-sub">조건을 바꾸고 다시 추천받을 수 있어요 · 메뉴를 체크해 비교함에 담아 보세요</span></div></div>
      <ConditionTable compact init={init} tags={pref.tags} title="추천 조건" onSubmit={c => { const q = toQuery(c); if (p.sort) q.set('sort', p.sort); nav(`/recommend?${q}`) }} />
      <div className="dn-sec">
        <SortTabs items={SORTS} value={p.sort || 'rec'} onChange={v => set('sort', v)} total={data?.total} unit="개 메뉴" />
        <div className="dn-legend">
          <span><b className="down">파랑</b> 평년보다 싼 재료</span><span><b className="up">주황</b> 평년보다 비싼 재료</span>
          <span><b>관심도</b> 이번 달 레시피 등록·후기 + 유튜브 쇼츠 언급 (작년 같은 달 대비)</span>
        </div>
        <State loading={loading} error={error} empty={data && !data.items.length && '조건에 맞는 메뉴가 없어요. 먹고 싶은 음식을 줄이거나 상황을 ‘상관없음’으로 바꿔 보세요.'}>
          <ul className="dn-list">{data?.items.map((m, i) => <MenuRow key={m.id} m={m} rank={(page - 1) * PAGE + i + 1} />)}</ul>
          <Pager page={page} pages={pages} onChange={n => set('page', String(n))} />
        </State>
      </div>
      <Source>재료 시세: KAMIS 소매가(전국 평균)의 평년 대비 등락이에요{data?.priceMonth ? ` (${data.priceMonth})` : ''}. 양념·조미료는 빼고 주재료만 봐요. 메뉴와 대표 레시피는 만개의레시피 기준이에요 (같은 메뉴 레시피 중 조회수 1위).</Source>
    </div>
  )
}
