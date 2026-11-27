// 레시피 검색: 조건표 + 정렬 탭 + 목록 (사진 | 정보 | 1인분 재료비)
import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, DISH } from '../components/ui'
import { FilterTable, FRow, Opt, SortTabs, Pager, RecipeRow } from '../components/dn'

const SORTS = [['views', '인기순'], ['value', '가성비순'], ['cost', '1인분 싼 순'], ['rating', '평점순'], ['time', '빨리 만드는 순']]
const TIMES = [['', '전체'], ['10', '10분 이내'], ['15', '15분 이내'], ['30', '30분 이내'], ['60', '1시간 이내']]
const COSTS = [['', '전체'], ['1000', '1,000원 이하'], ['2000', '2,000원 이하'], ['3000', '3,000원 이하'], ['5000', '5,000원 이하']]
const SIZE = 20

export default function RecipeList() {
  const [sp, setSp] = useSearchParams()
  const p = Object.fromEntries(sp)
  const set = (k, v) => { const n = { ...p, [k]: v, page: k === 'page' ? v : '' }; setSp(Object.fromEntries(Object.entries(n).filter(([, x]) => x))) }
  const [q, setQ] = useState(p.q || '')
  useEffect(() => setQ(p.q || ''), [p.q])
  const [view, setView] = useState(() => { try { return localStorage.getItem('omm_view') || 'list' } catch { return 'list' } })
  const chView = v => { setView(v); try { localStorage.setItem('omm_view', v) } catch {} }
  const { data, loading, error } = useApi(() => api.recipes({ ...p, size: SIZE }), [sp.toString()])
  const pages = data ? Math.min(50, Math.ceil(data.total / (data.size || SIZE))) : 0
  return (
    <div className="v3-page">
      <div className="v3-title-row"><div><h1>{p.q ? <>‘{p.q}’ 레시피 검색 결과</> : '레시피 검색'}</h1><span className="v3-sub">만개의레시피 레시피를 재료비 · 조리시간으로 비교해요</span></div></div>
      <FilterTable className="compact" title="검색 조건" right={<button type="button" className="dn-btn line" onClick={() => setSp({})}>초기화</button>}>
        <FRow label="검색어">
          <form className="dn-inline" onSubmit={e => { e.preventDefault(); set('q', q.trim()) }}>
            <input value={q} onChange={e => setQ(e.target.value)} placeholder="요리 이름 · 재료 (예: 김치찌개, 감자)" aria-label="레시피 검색어" />
            <button type="submit">검색</button>
          </form>
        </FRow>
        <FRow label="요리 종류">
          <div className="dn-opts">
            <Opt on={!p.dishType} onClick={() => set('dishType', '')}>전체</Opt>
            {Object.keys(DISH).map(d => <Opt key={d} on={p.dishType === d} onClick={() => set('dishType', p.dishType === d ? '' : d)}>{d}</Opt>)}
          </div>
        </FRow>
        <FRow label="조리시간">
          <div className="dn-opts">{TIMES.map(([v, l]) => <Opt key={l} on={(p.maxMin || '') === v} onClick={() => set('maxMin', v)}>{l}</Opt>)}</div>
        </FRow>
        <FRow label="1인분 재료비" help="재료 가격이 60% 넘게 확인된 레시피만 걸러요">
          <div className="dn-opts">{COSTS.map(([v, l]) => <Opt key={l} on={(p.maxCost || '') === v} onClick={() => set('maxCost', v)}>{l}</Opt>)}</div>
        </FRow>
        <FRow label="내 취향 제외">
          <div className="dn-opts">
            <Opt on={p.prefs !== 'off'} onClick={() => set('prefs', p.prefs === 'off' ? '' : 'off')}>로그인했으면 내 ‘제외할 음식’이 들어간 레시피 빼기</Opt>
            {data?.excluded?.length > 0 && p.prefs !== 'off' && <span className="dn-fhelp">지금 빼는 중: <b>{data.excluded.join(', ')}</b></span>}
          </div>
        </FRow>
      </FilterTable>
      <div className="dn-sec">
        <SortTabs items={SORTS} value={p.sort || 'views'} onChange={v => set('sort', v)} total={data?.total} unit="개 레시피"
          right={<span className="dn-view" role="group" aria-label="보기 방식">
            <button type="button" className={view === 'list' ? 'on' : ''} onClick={() => chView('list')}>목록형</button>
            <button type="button" className={view === 'grid' ? 'on' : ''} onClick={() => chView('grid')}>사진형</button>
          </span>} />
        <State loading={loading} error={error} empty={data && !data.items.length && '조건에 맞는 레시피가 없어요. 조건을 줄여 보세요.'}>
          <ul className={`dn-list ${view === 'grid' ? 'grid' : ''}`}>{data?.items.map(r => <RecipeRow key={r.id} r={r} />)}</ul>
          <Pager page={+p.page || 1} pages={pages} onChange={n => set('page', String(n))} />
        </State>
      </div>
    </div>
  )
}
