import { useEffect, useState } from 'react'
import { api } from '../api'
import { useApi, State } from './ui'

// matplotlib 보고서 차트 (back1 이 pandas + matplotlib 로 그린 PNG)
export const REPORT_FOR = {
  value: ['6_영양효율.png'], clusters: ['1_군집.png', '2_별점_재료비.png'], network: ['7_네트워크.png', '7_중심성.png'],
  interest: ['5_트렌드.png', '5_트렌드_순위.png'], measure: ['8_신뢰도.png'],
}

function Figure({ c, v }) {
  const src = api.reportUrl(c.file, v)
  const svg = c.svg ? api.reportUrl(c.svg, v) : src          // SVG(벡터)가 있으면 선명하게
  return (
    <figure className="report-fig">
      <figcaption><b>{c.no}. {c.title}</b> <span className="muted">{c.note}</span> <a className="muted" href={src} download={c.file}>PNG 저장</a></figcaption>
      <a href={svg} target="_blank" rel="noreferrer"><img src={svg} alt={c.title} loading="lazy" onError={e => { if (e.currentTarget.src !== src) e.currentTarget.src = src }} /></a>
      {c.file === '7_네트워크.png' && <a className="muted" href={api.reportUrl('7_네트워크.html', v)} target="_blank" rel="noreferrer">마우스로 보는 네트워크 열기 →</a>}
    </figure>
  )
}

// 분석 탭 안: 그 분석에 해당하는 보고서 차트만
export function ReportView({ type }) {
  const r = useApi(() => api.report())
  const files = REPORT_FOR[type] || []
  return (
    <State loading={r.loading} error={r.error}>
      {r.data && (() => {
        const list = r.data.charts.filter(c => files.includes(c.file))
        if (!r.data.charts.length) return <div className="state">아직 그린 보고서 차트가 없어요. 관리자 › 보고서 차트 탭에서 ‘다시 그리기’를 눌러 주세요.</div>
        if (!list.length) return <div className="state">이 분석은 matplotlib 보고서 차트가 따로 없어요. 위의 ‘차트’ · ‘DataFrame’ 으로 보세요.</div>
        return <>{list.map(c => <Figure key={c.file} c={c} v={r.data.generatedAt} />)}<p className="muted">그린 시각 {r.data.generatedAt || '-'} · pandas + matplotlib</p></>
      })()}
    </State>
  )
}

// 관리자 › 보고서 차트: 전체 + 다시 그리기
export function ReportGallery() {
  const [tick, setTick] = useState(0)
  const [msg, setMsg] = useState('')
  const r = useApi(() => api.report(), [tick])
  useEffect(() => {                       // 그리는 중이면 5초마다 다시 확인
    if (!r.data?.running) return
    const t = setTimeout(() => setTick(x => x + 1), 5000)
    return () => clearTimeout(t)
  }, [r.data])
  const refresh = async () => {
    setMsg('그리는 중… (1~2분)')
    try { await api.refreshReport(); setTick(x => x + 1) } catch (x) { setMsg(`실패: ${x.message}`) }
  }
  return (
    <div className="panel">
      <div className="panel-head">
        <h3>보고서 차트 <small>pandas + matplotlib · 매일 적재 뒤 자동으로 다시 그림</small></h3>
        <button type="button" className="btn line" onClick={refresh} disabled={r.data?.running}>{r.data?.running ? '그리는 중…' : '다시 그리기'}</button>
      </div>
      {msg && !r.data?.running && <p className="muted">{msg.startsWith('실패') ? msg : ''}</p>}
      <State loading={r.loading} error={r.error}>
        {r.data && (r.data.charts.length
          ? <>{r.data.charts.map(c => <Figure key={c.file} c={c} v={r.data.generatedAt} />)}<p className="muted">그린 시각 {r.data.generatedAt}</p></>
          : <div className="state">아직 그린 차트가 없어요. ‘다시 그리기’를 눌러 주세요.</div>)}
        {r.data?.error && <pre className="df-code">{r.data.error}</pre>}
      </State>
    </div>
  )
}
