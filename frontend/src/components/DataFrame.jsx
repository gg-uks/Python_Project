// pandas DataFrame 처럼 보여주기 (Jupyter 의 df 출력 모양)
// rows: [{col: value, ...}]  →  인덱스 · 컬럼 · NaN · "n rows × m columns"
// 행이 많으면 pandas 처럼 앞 10행 … 뒤 5행

const isNum = v => typeof v === 'number' && Number.isFinite(v)

function fmt(v) {
  if (v === null || v === undefined || (typeof v === 'number' && Number.isNaN(v))) return <span className="df-nan">NaN</span>
  if (typeof v === 'boolean') return v ? 'True' : 'False'
  if (isNum(v)) return Number.isInteger(v) ? String(v) : String(Math.round(v * 10000) / 10000)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

export function columnsOf(rows) {
  const cols = []
  for (const r of rows) for (const k of Object.keys(r)) if (!cols.includes(k)) cols.push(k)
  return cols
}

export default function DataFrame({ rows, head = 10, tail = 5, columns }) {
  if (!rows?.length) return <div className="df-empty">Empty DataFrame<br />Columns: []<br />Index: []</div>
  const cols = columns || columnsOf(rows)
  const numCol = Object.fromEntries(cols.map(c => [c, rows.some(r => isNum(r[c])) && rows.every(r => r[c] == null || isNum(r[c]))]))
  const cut = rows.length > head + tail
  const shown = cut ? [...rows.slice(0, head).map((r, i) => [i, r]), null, ...rows.slice(-tail).map((r, i) => [rows.length - tail + i, r])] : rows.map((r, i) => [i, r])
  return (
    <div className="df-wrap">
      <table className="dataframe">
        <thead><tr><th />{cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>
          {shown.map((x, k) => x === null
            ? <tr key="dots" className="df-dots"><th>...</th>{cols.map(c => <td key={c}>...</td>)}</tr>
            : <tr key={k}><th>{x[0]}</th>{cols.map(c => <td key={c} className={numCol[c] ? 'num' : ''}>{fmt(x[1][c])}</td>)}</tr>)}
        </tbody>
      </table>
      <p className="df-shape">{rows.length} rows × {cols.length} columns</p>
    </div>
  )
}

// df.describe(): 숫자 컬럼별 count · mean · std · min · 25% · 50% · 75% · max
export function describe(rows) {
  const cols = columnsOf(rows).filter(c => rows.some(r => isNum(r[c])))
  const q = (a, p) => { const i = (a.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return a[lo] + (a[hi] - a[lo]) * (i - lo) }
  const stats = ['count', 'mean', 'std', 'min', '25%', '50%', '75%', 'max']
  const by = Object.fromEntries(cols.map(c => {
    const a = rows.map(r => r[c]).filter(isNum).sort((x, y) => x - y)
    const n = a.length, mean = a.reduce((s, v) => s + v, 0) / n
    const std = n > 1 ? Math.sqrt(a.reduce((s, v) => s + (v - mean) ** 2, 0) / (n - 1)) : NaN
    return [c, { count: n, mean, std, min: a[0], '25%': q(a, 0.25), '50%': q(a, 0.5), '75%': q(a, 0.75), max: a[n - 1] }]
  }))
  return { cols, rows: stats.map(s => ({ _: s, ...Object.fromEntries(cols.map(c => [c, by[c][s]])) })) }
}

export function Describe({ rows }) {
  const d = describe(rows || [])
  if (!d.cols.length) return <div className="df-empty">숫자 컬럼이 없어요</div>
  return (
    <div className="df-wrap">
      <table className="dataframe">
        <thead><tr><th />{d.cols.map(c => <th key={c}>{c}</th>)}</tr></thead>
        <tbody>{d.rows.map(r => <tr key={r._}><th>{r._}</th>{d.cols.map(c => <td key={c} className="num">{fmt(r[c])}</td>)}</tr>)}</tbody>
      </table>
    </div>
  )
}
