// UI v3 ⑥ 음식 트렌드
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useApi, State, num } from '../components/ui'
import { Panel, BarList, Source, signPct } from '../components/v3'

const SHADE = v => (v == null ? ['#F1F3EF', '#9AA39D'] : v >= 90 ? ['#142842', '#fff'] : v >= 75 ? ['#3D7758', '#fff'] : v >= 60 ? ['#659A7B', '#fff'] : v >= 45 ? ['#9BC9AA', '#1B2330'] : v >= 30 ? ['#B4D6BE', '#1B2330'] : ['#DCE5F0', '#1B2330'])
const ago = d => { const days = Math.round((Date.now() - new Date(d)) / 864e5); return days <= 0 ? '오늘' : `${days}일 전` }

export default function Trends() {
  const kw = useApi(() => api.trendKeywords())
  const rise = useApi(() => api.trendMenusBy('rise', 6))
  const fall = useApi(() => api.trendMenusBy('fall', 4))
  const cal = useApi(() => api.calendar())
  const keys = (kw.data?.keywords || []).slice(0, 10)
  const maxRise = Math.max(...(rise.data || []).map(m => +m.yoyPct || 0), 1)
  return (
    <div className="v3-page">
      <div>
        <h1>요즘 많이 만드는 음식</h1>
        <p className="v3-lead">유튜브 '먹방' 쇼츠(매일 수집)와 만개의레시피 신규 레시피·후기로 봐요. 이번 달, 작년 같은 달 대비.</p>
      </div>

      <Panel title="유튜브 쇼츠 · 요즘 뜨는 키워드" sub="쇼츠 제목·설명에서 찾은 음식 · 작년 같은 달 대비 (없으면 조회수 합)">
        <State loading={kw.loading} error={kw.error}>
          <div className="v3-chips">
            {keys.map((k, i) => (
              <span key={k.keyword} className={`v3-kw ${k.yoyPct != null && k.yoyPct < 0 ? 'cold' : i < 3 ? 'top' : ''}`}>
                {k.keyword} <strong>{k.yoyPct != null ? signPct(k.yoyPct) : `${num((k.views || 0) / 10000)}만`}</strong>
              </span>
            ))}
          </div>
          <div className="v3-shorts">
            {(kw.data?.videos || []).slice(0, 6).map(v => (
              <a key={v.id} href={`https://www.youtube.com/shorts/${v.id}`} target="_blank" rel="noreferrer" className="v3-short">
                <div className="v3-photo"><img src={`https://i.ytimg.com/vi/${v.id}/hqdefault.jpg`} alt="" loading="lazy" referrerPolicy="no-referrer" onError={e => { e.currentTarget.style.display = 'none' }} /><span>쇼츠 썸네일</span></div>
                <b>{v.title}</b>
                <small>조회 {num(v.views)} · {ago(v.publishedAt)}</small>
              </a>
            ))}
          </div>
        </State>
        <Source>재료나 메뉴 이름으로 검색하지 않고 '먹방' 같은 넓은 검색어로 모은 뒤, 제목에서 찾은 음식을 메뉴 사전으로 맞춰요.</Source>
      </Panel>

      <div className="v3-two wide-left">
        <Panel title="뜨는 메뉴" sub="막대 = 레시피 등록·후기 증가율 (작년 같은 달 대비)">
          <State loading={rise.loading} error={rise.error}>
            <ol className="v3-rank">
              {(rise.data || []).map((m, i) => (
                <li key={m.id}>
                  <span className="v3-rank-no">{i + 1}</span>
                  <span className="v3-rank-name"><Link to={`/menus/${m.id}`}>{m.name}</Link><small>{m.dishType || '기타'}{m.ytYoyPct != null ? ` · 쇼츠 ${signPct(m.ytYoyPct)}` : m.ytVideos ? ` · 쇼츠 ${m.ytVideos}개` : ''}</small></span>
                  <span className="v3-bar-track"><span className="v3-bar-fill" style={{ width: `${Math.max(4, ((+m.yoyPct || 0) / maxRise) * 100)}%` }} /></span>
                  <span className="v3-rank-pct">{signPct(m.yoyPct)}</span>
                </li>
              ))}
            </ol>
          </State>
        </Panel>
        <Panel title="지는 메뉴" sub="작년 같은 달 대비">
          <State loading={fall.loading} error={fall.error}>
            <ul className="v3-menu-list">
              {(fall.data || []).map(m => <li key={m.id}><Link to={`/menus/${m.id}`}><span>{m.name}</span><span className="v3-badge cold">{signPct(m.yoyPct)}</span></Link></li>)}
            </ul>
          </State>
          <Link to="/insight" className="v3-more">가격과 같이 보기</Link>
        </Panel>
      </div>

      <Panel title="계절 캘린더 · 언제 많이 만들고, 언제 싼가" sub="칸 숫자 = 그 재료 레시피 관심도 지수 (최근 12개월 중 가장 많은 달 = 100) · 점 = 평년 소매가가 가장 싼 달">
        <State loading={cal.loading} error={cal.error}>
          <div className="v3-table-wrap">
            <table className="v3-cal">
              <thead><tr><th />{Array.from({ length: 12 }, (_, i) => <th key={i} scope="col">{i + 1}월</th>)}</tr></thead>
              <tbody>
                {(cal.data?.items || []).map(r => (
                  <tr key={r.ingredientId}>
                    <th scope="row"><Link to={`/explore?id=${r.ingredientId}`}>{r.name}</Link></th>
                    {r.cells.map((v, i) => {
                      const [bg, fg] = SHADE(v)
                      return <td key={i}><div style={{ background: bg, color: fg }}>{v ?? '–'}{r.cheapMonth === i + 1 && <span className="v3-cheap" aria-label="평년가 가장 쌈" />}</div></td>
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </State>
      </Panel>
      <Source>출처: YouTube Data API(먹방 쇼츠, 매일 수집) · 만개의레시피 월별 레시피·후기 수 · KAMIS 평년 소매가.</Source>
    </div>
  )
}
