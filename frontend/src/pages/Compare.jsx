// 메뉴 비교: 비교함에 담은 메뉴 2~4개를 표 하나로 (재료비 · 영양 · 조리시간 · 별점 · 관심도)
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, won, num, costOk } from '../components/ui'
import { Thumb, useCompare } from '../components/dn'
import { Source } from '../components/v3'

// [행 이름, 값 꺼내기, 보기 좋게, 좋은 쪽(min/max/없음)]
const ROWS = [
  ['요리 종류', x => x.m.dishType],
  ['메뉴 유형', x => x.m.cluster?.name],
  ['대표 레시피', x => x.r?.title || x.m.repRecipe?.title, (v, x) => (v ? <Link to={`/recipes/${x.r?.id || x.m.repRecipe?.id}`}>{v}</Link> : '–')],
  ['1인분 재료비', x => (x.r && costOk(x.r) ? x.r.costPerServing : null), v => won(v), 'min'],
  ['조리시간', x => x.r?.cookMin ?? x.m.cookMin, v => (v == null ? '–' : `${v}분`), 'min'],
  ['난이도', x => x.r?.difficulty],
  ['열량 (1인분)', x => x.m.kcal, v => (v == null ? '–' : `${num(v)} kcal`)],
  ['단백질', x => x.m.protein, v => (v == null ? '–' : `${num(v, 1)} g`), 'max'],
  ['나트륨', x => x.m.sodium, v => (v == null ? '–' : `${num(v)} mg`), 'min'],
  ['별점', x => (x.r?.rating != null ? Number(x.r.rating) : null), (v, x) => (v == null ? '–' : `★ ${v.toFixed(1)} (후기 ${num(x.r?.reviewCount)})`), 'max'],
  ['레시피 수', x => x.m.recipeCount, v => (v == null ? '–' : `${num(v)}개`), 'max'],
  ['관심도 지수', x => x.m.interestIndex, v => (v == null ? '–' : num(v, 0)), 'max'],
]

export default function Compare() {
  const [sp] = useSearchParams()
  const c = useCompare()
  const ids = (sp.get('ids') ? sp.get('ids').split(',') : c.list.map(x => String(x.id))).filter(Boolean).slice(0, 4)
  const d = useApi(() => Promise.all(ids.map(async id => {
    const m = await api.menu(id)
    const r = m.repRecipe?.id ? await api.recipe(m.repRecipe.id).catch(() => null) : null
    return { m, r }
  })), [ids.join(',')])
  return (
    <div className="v3-page">
      <div className="v3-title-row"><div><h1>메뉴 비교</h1><span className="v3-sub">메뉴 추천 결과에서 ‘비교’를 체크해 최대 4개까지 담을 수 있어요 · 초록 칸이 더 나은 값이에요</span></div></div>
      {ids.length < 2 ? (
        <div className="state">비교할 메뉴를 2개 이상 담아 주세요. <Link to="/recommend">메뉴 추천 결과로</Link></div>
      ) : (
        <State loading={d.loading} error={d.error}>
          {d.data && (
            <div style={{ overflowX: 'auto' }}>
              <table className="dn-ctable">
                <thead>
                  <tr>
                    <th scope="row">메뉴</th>
                    {d.data.map(x => (
                      <td key={x.m.id}>
                        <Thumb src={x.r?.imageUrl || x.m.imageUrl} alt={x.m.name} />
                        <Link className="name" to={`/menus/${x.m.id}`}>{x.m.name}</Link>
                        <div><button type="button" className="btn text" onClick={() => c.remove(x.m.id)}>비교함에서 빼기</button></div>
                      </td>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {ROWS.map(([label, get, fmt = v => v ?? '–', better]) => {
                    const vals = d.data.map(get)
                    const nums = vals.filter(v => typeof v === 'number')
                    const best = better && nums.length > 1 ? (better === 'min' ? Math.min(...nums) : Math.max(...nums)) : null
                    return (
                      <tr key={label}>
                        <th scope="row">{label}</th>
                        {d.data.map((x, i) => <td key={x.m.id} className={best != null && vals[i] === best ? 'best' : ''}>{fmt(vals[i], x)}</td>)}
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </State>
      )}
      <Source>재료비는 대표 레시피의 1인분 재료비(KAMIS 소매가, 재료 가격 60% 이상 확인된 경우만), 영양은 식약처 식품영양성분DB 메뉴 단위 값이에요.</Source>
    </div>
  )
}
