// 냉장고 털기: 가진 재료 고르기(조건표) → 그 재료를 가장 많이 쓰는 레시피 목록 (오른쪽 = 더 살 재료비)
import { useState } from 'react'
import { api } from '../api'
import { useApi, State, won } from '../components/ui'
import { FilterTable, FRow, Opt, SortTabs, RecipeRow, PriceCell } from '../components/dn'
import { PairIngredients } from '../components/Facts'

const SORTS = [['have', '가진 재료 많은 순'], ['extra', '더 살 돈 적은 순'], ['views', '인기순']]

export default function Fridge() {
  const [q, setQ] = useState('')
  const [picked, setPicked] = useState([])
  const [run, setRun] = useState(0)
  const [sort, setSort] = useState('have')
  const found = useApi(() => api.ingredients(q, 24), [q])
  const res = useApi(() => (picked.length ? api.byIngredients(picked.map(p => p.id)) : Promise.resolve(null)), [run])
  const toggle = i => setPicked(ps => (ps.some(p => p.id === i.id) ? ps.filter(p => p.id !== i.id) : [...ps, i]))
  const extra = r => r.missing.reduce((s, m) => s + (m.cost || 0), 0)
  const list = [...(res.data || [])].sort({ have: (a, b) => b.haveRatio - a.haveRatio, extra: (a, b) => extra(a) - extra(b) || b.haveRatio - a.haveRatio, views: (a, b) => (b.views || 0) - (a.views || 0) }[sort])
  return (
    <div className="v3-page">
      <div className="v3-title-row"><div><h1>냉장고 털기</h1><span className="v3-sub">가진 재료를 고르면 그 재료를 가장 많이 쓰는 레시피와 더 사야 할 재료비를 보여 줘요 (양념은 빼고 계산)</span></div></div>
      <FilterTable className="compact" title="가진 재료 고르기" right={picked.length > 0 && <button type="button" className="dn-btn line" onClick={() => setPicked([])}>모두 빼기</button>}>
        <FRow label="재료 찾기">
          <div className="dn-inline"><input value={q} onChange={e => setQ(e.target.value)} placeholder="재료 이름 (예: 감자, 돼지고기)" aria-label="재료 이름" /></div>
          <State loading={found.loading} error={found.error}>
            <div className="dn-opts">{(found.data || []).filter(i => !i.seas).map(i => <Opt key={i.id} on={picked.some(p => p.id === i.id)} onClick={() => toggle(i)}>{i.name}</Opt>)}</div>
          </State>
        </FRow>
        <FRow label="고른 재료">
          {picked.length ? <div className="dn-picked">{picked.map(p => <button key={p.id} type="button" className="want" onClick={() => toggle(p)}>{p.name} ✕</button>)}</div>
            : <span className="dn-fhelp">위에서 재료를 체크해 주세요</span>}
          <PairIngredients names={picked.map(p => p.name)} title="같이 있으면 좋은 재료" limit={8} onPick={async n => { const r = (await api.ingredients(n, 5).catch(() => [])).find(x => x.name === n); if (r) toggle(r) }} />
        </FRow>
        <div className="dn-ftable-foot">
          <span className="dn-sum">고른 재료 <b>{picked.length}</b>개</span>
          <button type="button" className="dn-btn big" disabled={!picked.length} onClick={() => setRun(x => x + 1)}>이 재료로 레시피 찾기</button>
        </div>
      </FilterTable>
      {run > 0 && (
        <div className="dn-sec">
          <SortTabs items={SORTS} value={sort} onChange={setSort} total={res.data?.length} unit="개 레시피" />
          <State loading={res.loading} error={res.error} empty={res.data && !res.data.length && '맞는 레시피가 없어요. 재료를 더 골라 보세요.'}>
            <ul className="dn-list">
              {list.map(r => (
                <RecipeRow key={r.id} r={r}
                  extraBadges={<>
                    <span className="v3-badge down">가진 재료 {Math.round(r.haveRatio * 100)}%</span>
                    {r.missing.length > 0 && <span className="v3-badge neutral">더 필요: {r.missing.slice(0, 4).map(m => m.name).join(', ')}{r.missing.length > 4 ? ' …' : ''}</span>}
                  </>}
                  side={<PriceCell label="더 살 재료비" value={r.missing.length ? (extra(r) ? `+${won(extra(r))}` : '–') : '0원'}
                    tone={r.missing.length ? '' : 'down'} note={r.missing.length ? `부족한 재료 ${r.missing.length}가지` : '지금 바로 만들 수 있어요'} to={`/recipes/${r.id}`} cta="레시피 보기" />} />
              ))}
            </ul>
          </State>
        </div>
      )}
    </div>
  )
}
