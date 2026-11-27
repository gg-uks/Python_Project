import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api'
import { useApi, State } from './ui'
import { INSIGHT_TABS } from '../insights'
import { makeZip, saveBlob } from '../zip'

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

// ZIP 안 폴더 이름: '① 메뉴 군집' → '1_메뉴군집', '② 별점 × 재료비' → '2_별점x재료비'
const folderOf = (label, i) => `${i + 1}_${label.replace(/^[①-⑳]\s*/, '').replace(/\s*×\s*/g, 'x').replace(/[\s/\\:*?"<>|]+/g, '')}`

// 그림을 분석 번호(no — 6 · "5-1" 처럼 와서 '-' 앞만)로 묶음. 번호가 안 맞으면 INSIGHT_TABS 의 파일 목록으로. 어디에도 없는 그림은 '기타'
function groupCharts(charts) {
  const groups = INSIGHT_TABS.map(([key, label, , fn, files], i) => {
    const no = String(fn || '').replace('chart', '')
    const byNo = charts.filter(c => no && String(c.no).split('-')[0] === no)
    return { key, label, folder: folderOf(label, i), charts: byNo.length ? byNo : charts.filter(c => files.includes(c.file)) }
  })
  const known = new Set(groups.flatMap(g => g.charts.map(c => c.file)))
  const etc = charts.filter(c => !known.has(c.file))
  if (etc.length) groups.push({ key: 'etc', label: '기타', folder: `${INSIGHT_TABS.length + 1}_기타`, charts: etc })
  return groups
}

// 관리자 › 보고서 차트: 인사이트별 탭 + 다시 그리기 + ZIP 저장
export function ReportGallery() {
  const [tick, setTick] = useState(0)
  const [msg, setMsg] = useState('')
  const [sp, setSp] = useSearchParams()
  const [dl, setDl] = useState('')
  const [busy, setBusy] = useState(false)
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

  const charts = r.data?.charts || []
  const v = r.data?.generatedAt
  const groups = groupCharts(charts)
  const cur = groups.find(g => g.key === sp.get('rt'))          // 없으면 '전체'
  const shown = cur ? [cur] : groups.filter(g => g.charts.length)
  const pick = key => {                                         // ?tab= 은 그대로 두고 ?rt= 만 바꿈
    const q = Object.fromEntries(sp)
    if (key) q.rt = key; else delete q.rt
    setSp(q)
  }

  // 그림을 받아서 인사이트별 폴더로 ZIP 하나에 담음 (네트워크는 마우스로 보는 html 도 같이)
  const save = async gs => {
    const list = gs.flatMap(g => g.charts.flatMap(c => {
      const out = [{ url: api.reportUrl(c.file, v), name: `${g.folder}/${c.file}` }]
      if (c.file === '7_네트워크.png') out.push({ url: api.reportUrl('7_네트워크.html', v), name: `${g.folder}/7_네트워크.html` })
      return out
    }))
    if (!list.length) return
    setBusy(true); setDl(`파일 ${list.length}개 모으는 중…`)
    const files = [], miss = []
    for (const f of list) {
      try {
        const res = await fetch(f.url)
        if (!res.ok) throw new Error(res.status)
        files.push({ name: f.name, data: new Uint8Array(await res.arrayBuffer()) })
      } catch { miss.push(f.name) }
    }
    setBusy(false)
    if (!files.length) { setDl('파일을 하나도 받지 못했어요. ‘다시 그리기’ 후 다시 시도해 주세요.'); return }
    const stamp = (v || '').replace(/[^0-9]/g, '').slice(0, 12) || new Date().toISOString().replace(/[^0-9]/g, '').slice(0, 12)
    const name = gs.length === 1 ? `OMM_보고서_${gs[0].folder}_${stamp}.zip` : `OMM_보고서_전체_${stamp}.zip`
    saveBlob(makeZip(files), name)
    setDl(miss.length ? `${files.length}개 저장 · 받지 못한 파일: ${miss.join(', ')}` : `${files.length}개 저장했어요 (${name})`)
  }

  return (
    <div className="panel">
      <div className="panel-head">
        <h3>보고서 차트 <small>pandas + matplotlib · 매일 적재 뒤 자동으로 다시 그림</small></h3>
        <button type="button" className="btn line" onClick={refresh} disabled={r.data?.running}>{r.data?.running ? '그리는 중…' : '다시 그리기'}</button>
      </div>
      {msg && !r.data?.running && <p className="muted">{msg.startsWith('실패') ? msg : ''}</p>}
      <State loading={r.loading} error={r.error}>
        {r.data && (charts.length
          ? <>
            <div className="nb-tabs rpt-tabs" role="tablist">
              <button role="tab" aria-selected={!cur} className={cur ? '' : 'on'} onClick={() => pick(null)}>전체 ({charts.length})</button>
              {groups.map(g => (
                <button key={g.key} role="tab" aria-selected={cur === g} className={cur === g ? 'on' : ''}
                  disabled={!g.charts.length} title={g.charts.length ? '' : '아직 그린 그림이 없어요'} onClick={() => pick(g.key)}>{g.label}</button>
              ))}
            </div>
            <div className="rpt-tools">
              {cur && <button type="button" className="btn line" disabled={busy || !cur.charts.length} onClick={() => save([cur])}>이 탭 PNG 저장 (ZIP · {cur.charts.length}개)</button>}
              <button type="button" className="btn line" disabled={busy} onClick={() => save(groups.filter(g => g.charts.length))}>전체 PNG 저장 (ZIP · 인사이트별 폴더)</button>
              {dl && <small className="muted">{dl}</small>}
            </div>
            {shown.map(g => (
              <section key={g.key} className="rpt-group">
                {!cur && <h4>{g.label}</h4>}
                {g.charts.length
                  ? g.charts.map(c => <Figure key={c.file} c={c} v={v} />)
                  : <div className="state">이 인사이트 그림이 아직 없어요. ‘다시 그리기’를 눌러 주세요.</div>}
              </section>
            ))}
            <p className="muted">그린 시각 {v}</p>
          </>
          : <div className="state">아직 그린 차트가 없어요. ‘다시 그리기’를 눌러 주세요.</div>)}
        {r.data?.error && <pre className="df-code">{r.data.error}</pre>}
      </State>
    </div>
  )
}
