import { useState } from 'react'

// 선 그래프 (월별 추이) · 마우스를 올리면 값 표시
export function LineChart({ data, x, y, height = 220, color = 'var(--brand)', fmt = v => v }) {
  const [hover, setHover] = useState(null)
  const pts = data.filter(d => d[y] != null)
  if (pts.length < 2) return <div className="state">그래프로 그릴 데이터가 부족해요</div>
  const W = 640, H = height, L = 52, R = 16, T = 16, B = 30
  const vs = pts.map(d => +d[y]), min = Math.min(...vs), max = Math.max(...vs), pad = (max - min) * 0.1 || 1
  const lo = min - pad, hi = max + pad
  const sx = i => L + (i * (W - L - R)) / (pts.length - 1), sy = v => T + ((hi - v) * (H - T - B)) / (hi - lo)
  const path = pts.map((d, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(+d[y])}`).join('')
  const ticks = [lo + (hi - lo) * 0.15, (lo + hi) / 2, hi - (hi - lo) * 0.15]
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)}>
        {ticks.map(t => (
          <g key={t}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="grid-line" /><text x={L - 8} y={sy(t) + 4} className="axis" textAnchor="end">{fmt(t)}</text></g>
        ))}
        <path d={`${path}L${sx(pts.length - 1)},${H - B}L${L},${H - B}Z`} fill={color} opacity="0.08" />
        <path d={path} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
        {pts.map((d, i) => (
          <g key={i} onMouseEnter={() => setHover(i)}>
            <rect x={sx(i) - (W - L - R) / pts.length / 2} y={T} width={(W - L - R) / pts.length} height={H - T - B} fill="transparent" />
            <circle cx={sx(i)} cy={sy(+d[y])} r={hover === i ? 5 : 3} fill="#fff" stroke={color} strokeWidth="2" />
            {(i % Math.ceil(pts.length / 8) === 0 || i === pts.length - 1) && <text x={sx(i)} y={H - 8} className="axis" textAnchor="middle">{String(d[x]).slice(2)}</text>}
          </g>
        ))}
        {hover != null && (
          <g transform={`translate(${Math.min(sx(hover), W - 120)},${Math.max(sy(+pts[hover][y]) - 44, 4)})`}>
            <rect width="112" height="36" rx="6" className="tip" />
            <text x="8" y="15" className="tip-t">{pts[hover][x]}</text>
            <text x="8" y="30" className="tip-v">{fmt(+pts[hover][y])}</text>
          </g>
        )}
      </svg>
    </div>
  )
}

// 가로 막대 (순위)
export function Bars({ items, label, value, fmt = v => v, color = 'var(--brand)', max }) {
  const m = max ?? Math.max(...items.map(i => Math.abs(+i[value] || 0)), 1)
  return (
    <div className="bars">
      {items.map((it, k) => {
        const v = +it[value] || 0
        return (
          <div className="bar-row" key={k}>
            <span className="bar-label" title={it[label]}>{it[label]}</span>
            <span className="bar-track"><span className="bar-fill" style={{ width: `${(Math.abs(v) / m) * 100}%`, background: v < 0 ? 'var(--down)' : color }} /></span>
            <span className="bar-val">{fmt(v)}</span>
          </div>
        )
      })}
    </div>
  )
}

// 재료 네트워크 (원형 배치)
export function Network({ nodes, edges }) {
  const W = 720, H = 500, cx = W / 2, cy = H / 2
  const groups = [...new Set(nodes.map(n => n.community))]
  const colors = ['#FF6B35', '#1F3A5F', '#3D7DD8', '#A35BD6', '#E2A100', '#D64B6B', '#5C6B7A']
  const pos = {}
  const inner = Math.min(12, nodes.length), outer = nodes.length - inner
  nodes.forEach((n, i) => {
    const a = i < inner ? (i / inner) * Math.PI * 2 : ((i - inner) / outer) * Math.PI * 2 + 0.05
    const r = i < inner ? 100 : 200
    pos[n.id] = [cx + Math.cos(a) * r * 1.35, cy + Math.sin(a) * r]
  })
  const maxN = Math.max(...edges.map(e => e.n))
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`}>
        {edges.map((e, i) => pos[e.a] && pos[e.b] && (
          <line key={i} x1={pos[e.a][0]} y1={pos[e.a][1]} x2={pos[e.b][0]} y2={pos[e.b][1]} stroke="#9AA4B2" strokeOpacity={0.15 + (0.5 * e.n) / maxN} strokeWidth={0.5 + (2.5 * e.n) / maxN} />
        ))}
        {nodes.map((n, i) => (
          <g key={n.id} transform={`translate(${pos[n.id][0]},${pos[n.id][1]})`}>
            <circle r={4 + Math.sqrt(n.degree) / 2.2} fill={colors[groups.indexOf(n.community) % colors.length]} stroke="#fff" strokeWidth="1.5" />
            {i < 36 && <text y={-9} textAnchor="middle" className="node-t">{n.name}</text>}
          </g>
        ))}
      </svg>
      <div className="legend">{groups.slice(0, 7).map((g, i) => <span key={g}><i style={{ background: colors[i % colors.length] }} />{g || '기타'}</span>)}</div>
    </div>
  )
}

// ── 분석용 웹 차트 (matplotlib 보고서 차트와 같은 색 순서) ─────────────────────
export const SERIES = ['#2a78d6', '#eb6834', '#0F8B8D', '#eda100', '#e87ba4', '#2B4C7E', '#6250d6', '#e34948']

const niceTicks = (lo, hi, log) => {
  if (log) {
    const out = []
    for (let k = Math.floor(Math.log10(lo)); k <= Math.ceil(Math.log10(hi)); k++) for (const m of [1, 2, 5]) { const v = m * 10 ** k; if (v >= lo && v <= hi) out.push(v) }
    return out.length > 7 ? out.filter(v => String(v)[0] === '1') : out
  }
  const step = 10 ** Math.floor(Math.log10((hi - lo) / 4 || 1)), s = [1, 2, 5, 10].map(m => m * step).find(x => (hi - lo) / x <= 6) || step * 10
  const out = []; for (let v = Math.ceil(lo / s) * s; v <= hi + 1e-9; v += s) out.push(+v.toFixed(10)); return out
}

// 산점도 · 그룹별 색 · 로그 축 선택 · 가장 가까운 점에 마우스를 올리면 값 표시
export function Scatter({ points, groups = [], xLog, yLog, xTitle, yTitle, xFmt = v => v, yFmt = v => v, tip, centers = [], zeroLines, fit, height = 380, color, labels }) {
  const [hover, setHover] = useState(null)
  const pts = points.filter(p => Number.isFinite(p.x) && Number.isFinite(p.y) && (!xLog || p.x > 0) && (!yLog || p.y > 0))
  if (pts.length < 2) return <div className="state">그래프로 그릴 데이터가 부족해요</div>
  const W = 720, H = height, L = 66, R = 16, T = 14, B = 44
  const ext = (k, log) => { const v = pts.map(p => p[k]); let lo = Math.min(...v), hi = Math.max(...v); if (log) { lo /= 1.3; hi *= 1.3 } else { const pad = (hi - lo) * 0.06 || 1; lo -= pad; hi += pad } return [lo, hi] }
  const [x0, x1] = ext('x', xLog), [y0, y1] = ext('y', yLog)
  const f = (v, a, b, log) => (log ? (Math.log(v) - Math.log(a)) / (Math.log(b) - Math.log(a)) : (v - a) / (b - a))
  const sx = v => L + f(v, x0, x1, xLog) * (W - L - R), sy = v => H - B - f(v, y0, y1, yLog) * (H - T - B)
  const gi = g => Math.max(0, groups.findIndex(x => x.id === g))
  const move = e => {
    const svg = e.currentTarget, r = svg.getBoundingClientRect(), mx = ((e.clientX - r.left) / r.width) * W, my = ((e.clientY - r.top) / r.height) * H
    let best = null, bd = 18 ** 2
    for (const p of pts) { const d = (sx(p.x) - mx) ** 2 + (sy(p.y) - my) ** 2; if (d < bd) { bd = d; best = p } }
    setHover(best)
  }
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseMove={move} onMouseLeave={() => setHover(null)} role="img" aria-label={`${yTitle} 대 ${xTitle} 산점도`}>
        {niceTicks(y0, y1, yLog).map(t => <g key={'y' + t}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="grid-line" /><text x={L - 8} y={sy(t) + 4} className="axis" textAnchor="end">{yFmt(t)}</text></g>)}
        {niceTicks(x0, x1, xLog).map(t => <text key={'x' + t} x={sx(t)} y={H - B + 18} className="axis" textAnchor="middle">{xFmt(t)}</text>)}
        {zeroLines && !xLog && x0 < 0 && x1 > 0 && <line x1={sx(0)} x2={sx(0)} y1={T} y2={H - B} stroke="#9aa4b2" strokeDasharray="4 4" />}
        {zeroLines && !yLog && y0 < 0 && y1 > 0 && <line x1={L} x2={W - R} y1={sy(0)} y2={sy(0)} stroke="#9aa4b2" strokeDasharray="4 4" />}
        <text x={(L + W - R) / 2} y={H - 6} className="axis" textAnchor="middle">{xTitle}</text>
        <text x={14} y={(T + H - B) / 2} className="axis" textAnchor="middle" transform={`rotate(-90 14 ${(T + H - B) / 2})`}>{yTitle}</text>
        {fit && !xLog && !yLog && (() => {   // 추세선 (최소제곱)
          const n = pts.length, mx = pts.reduce((a, p) => a + p.x, 0) / n, my = pts.reduce((a, p) => a + p.y, 0) / n
          const b = pts.reduce((a, p) => a + (p.x - mx) * (p.y - my), 0) / (pts.reduce((a, p) => a + (p.x - mx) ** 2, 0) || 1)
          return <line x1={sx(x0)} y1={sy(my + b * (x0 - mx))} x2={sx(x1)} y2={sy(my + b * (x1 - mx))} stroke="#5E6672" strokeDasharray="6 5" strokeWidth="1.5" />
        })()}
        {labels && pts.map((p, i) => <text key={'l' + i} x={sx(p.x) + 7} y={sy(p.y) + 4} className="node-t">{p.name}</text>)}
        {pts.map((p, i) => <circle key={i} cx={sx(p.x)} cy={sy(p.y)} r={hover === p ? 6 : labels ? 5 : 3} fill={color || SERIES[gi(p.g) % SERIES.length]} fillOpacity={hover === p ? 1 : 0.5} stroke="#fff" strokeWidth={hover === p ? 2 : 0.6} />)}
        {centers.map(c => <g key={c.id} transform={`translate(${sx(c.x)},${sy(c.y)})`}><path d="M-8,-8L8,8M-8,8L8,-8" stroke="#fff" strokeWidth="6" /><path d="M-8,-8L8,8M-8,8L8,-8" stroke={SERIES[gi(c.id) % SERIES.length]} strokeWidth="3.5" /><text x="11" y="-8" className="node-t">{c.name}</text></g>)}
        {hover && (() => {
          const lines = tip ? tip(hover) : [`${xTitle}: ${xFmt(hover.x)}`, `${yTitle}: ${yFmt(hover.y)}`]
          const w = Math.max(...lines.map(l => l.length)) * 7.2 + 18, h = lines.length * 16 + 10
          const tx = Math.min(sx(hover.x) + 10, W - w - 4), ty = Math.max(sy(hover.y) - h - 8, 4)
          return <g transform={`translate(${tx},${ty})`} pointerEvents="none"><rect width={w} height={h} rx="6" className="tip" />{lines.map((l, k) => <text key={k} x="9" y={17 + k * 16} className={k ? 'tip-v' : 'tip-t'}>{l}</text>)}</g>
        })()}
      </svg>
      {groups.length > 1 && <div className="legend">{groups.map((g, i) => <span key={g.id}><i style={{ background: SERIES[i % SERIES.length] }} />{g.name}</span>)}</div>}
    </div>
  )
}

// 여러 선 (월별 추이) · 세로선을 따라 그 달 값 전부 표시 · 범례 + 선 끝 이름
export function MultiLine({ series, xs, yFmt = v => v, yTitle, height = 340, hideLegend, zero = true }) {
  const [hover, setHover] = useState(null)
  if (!series.length || xs.length < 2) return <div className="state">그래프로 그릴 데이터가 부족해요</div>
  const W = 720, H = height, L = 56, R = 96, T = 14, B = 34
  const vals = series.flatMap(s => xs.map(x => s.values[x]).filter(v => v != null))
  const hi = Math.max(...vals, 1) * 1.08, lo = zero ? 0 : Math.min(...vals) * 0.9
  const sx = i => L + (i * (W - L - R)) / (xs.length - 1), sy = v => H - B - ((v - lo) / (hi - lo || 1)) * (H - T - B)
  return (
    <div className="chart">
      <svg viewBox={`0 0 ${W} ${H}`} onMouseLeave={() => setHover(null)} role="img" aria-label={`${yTitle} 월별 추이`}>
        {niceTicks(lo, hi).map(t => <g key={t}><line x1={L} x2={W - R} y1={sy(t)} y2={sy(t)} className="grid-line" /><text x={L - 8} y={sy(t) + 4} className="axis" textAnchor="end">{yFmt(t)}</text></g>)}
        {xs.map((x, i) => (i % Math.ceil(xs.length / 8) === 0 || i === xs.length - 1) && <text key={x} x={sx(i)} y={H - 10} className="axis" textAnchor="middle">{String(x).slice(2)}</text>)}
        {hover != null && <line x1={sx(hover)} x2={sx(hover)} y1={T} y2={H - B} stroke="#9aa4b2" strokeDasharray="3 3" />}
        {series.map((s, k) => {
          const d = xs.map((x, i) => [i, s.values[x]]).filter(([, v]) => v != null).map(([i, v], j) => `${j ? 'L' : 'M'}${sx(i)},${sy(v)}`).join('')
          const last = [...xs.keys()].reverse().find(i => s.values[xs[i]] != null)
          return <g key={s.name}>
            <path d={d} fill="none" stroke={s.color || SERIES[k % SERIES.length]} strokeWidth={s.dash ? 2 : 2.5} strokeDasharray={s.dash ? '5 4' : undefined} strokeLinejoin="round" />
            {hover != null && s.values[xs[hover]] != null && <circle cx={sx(hover)} cy={sy(s.values[xs[hover]])} r="4" fill="#fff" stroke={s.color || SERIES[k % SERIES.length]} strokeWidth="2" />}
            {last != null && <text x={sx(last) + 6} y={sy(s.values[xs[last]]) + 4} className="node-t" style={{ fill: s.color || SERIES[k % SERIES.length] }}>{s.name}</text>}
          </g>
        })}
        {xs.map((x, i) => <rect key={x} x={sx(i) - (W - L - R) / xs.length / 2} y={T} width={(W - L - R) / xs.length} height={H - T - B} fill="transparent" onMouseEnter={() => setHover(i)} />)}
        {hover != null && (() => {
          const rows = series.map((s, k) => [s.name, s.values[xs[hover]], k]).filter(r => r[1] != null).sort((a, b) => b[1] - a[1])
          const w = 150, h = rows.length * 15 + 26, tx = sx(hover) + 10 > W - R - w ? sx(hover) - w - 10 : sx(hover) + 10
          return <g transform={`translate(${tx},${T + 4})`} pointerEvents="none"><rect width={w} height={h} rx="6" className="tip" /><text x="9" y="16" className="tip-t">{xs[hover]}</text>
            {rows.map(([n, v, k], j) => <g key={n} transform={`translate(9,${31 + j * 15})`}><rect y="-8" width="8" height="8" rx="2" fill={series[k].color || SERIES[k % SERIES.length]} /><text x="13" className="tip-v">{n} {yFmt(v)}</text></g>)}</g>
        })()}
      </svg>
      {!hideLegend && <div className="legend">{series.map((s, k) => <span key={s.name}><i style={{ background: s.color || SERIES[k % SERIES.length] }} />{s.name}</span>)}</div>}
    </div>
  )
}
