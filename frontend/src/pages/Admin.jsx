import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Analysis from './Analysis'
import { ReportGallery } from '../components/Report'
import { api, auth } from '../api'
import { useApi, State, num } from '../components/ui'

const STATUS = { ETL_OK: ['성공', 'ok'], ETL_FAILED: ['실패', 'bad'], ETL_RUNNING: ['실행 중', 'run'], USER_ACTIVE: ['사용 중', 'ok'], USER_DORMANT: ['휴면', 'run'], USER_WITHDRAWN: ['탈퇴', 'bad'] }
const Badge = ({ s }) => { const [l, c] = STATUS[s] || [s, '']; return <span className={`badge ${c}`}>{l}</span> }

// 관리자 화면: 관리자로 로그인돼 있지 않으면 이 자리에서 관리자 이메일 · 비밀번호로 로그인
export default function Admin() {
  const [, refresh] = useState(0)
  if (!auth.isAdmin()) return <AdminLogin onDone={() => refresh(x => x + 1)} />
  return <AdminBody />
}

function AdminLogin({ onDone }) {
  const [f, setF] = useState({ email: '', password: '' })
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const submit = async e => {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      await api.login(f)
      if (auth.isAdmin()) onDone()
      else setErr('관리자 계정이 아니에요. 관리자 이메일로 로그인해 주세요.')
    } catch (x) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <form className="auth" onSubmit={submit}>
      <h1>관리자 로그인</h1>
      <p className="muted">데이터 분석 · 적재 현황 · 공통코드 · 회원 관리는 관리자만 볼 수 있어요.</p>
      <input className="input" type="email" placeholder="관리자 이메일" value={f.email} onChange={e => setF({ ...f, email: e.target.value })} autoComplete="username" />
      <input className="input" type="password" placeholder="비밀번호" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} autoComplete="current-password" />
      {err && <p className="err">{err}</p>}
      <button className="btn primary wide" disabled={busy}>{busy ? '확인 중…' : '관리자로 들어가기'}</button>
    </form>
  )
}

function AdminBody() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') || 'analysis'
  const setTab = k => setSp({ tab: k })
  const etl = useApi(() => api.etlRuns())
  const codes = useApi(() => api.codes())
  const users = useApi(() => api.users())
  const [group, setGroup] = useState('')
  const [cacheMsg, setCacheMsg] = useState('')
  const clearCache = async () => {
    setCacheMsg('비우는 중…')
    try { await api.clearCache(); setCacheMsg('캐시를 비웠어요. 화면을 새로고침하면 최신 값이 나와요.') } catch (x) { setCacheMsg(`실패: ${x.message}`) }
  }
  const groups = [...new Set((codes.data || []).map(c => c.group))]
  return (
    <>
      <div className="admin-head">
        <h1 className="filter-title">관리자</h1>
        <div><button type="button" className="btn line" onClick={clearCache}>캐시 비우기</button>{cacheMsg && <small className="muted"> {cacheMsg}</small>}</div>
      </div>
      <div className="tabs">{[['analysis', '데이터 분석'], ['report', '보고서 차트'], ['etl', '적재 현황'], ['codes', '공통코드'], ['users', '회원']].map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</div>
      {tab === 'analysis' && <Analysis />}
      {tab === 'report' && <ReportGallery />}
      {tab !== 'analysis' && tab !== 'report' && <div className="panel">
        {tab === 'etl' && <State loading={etl.loading} error={etl.error}>
          <table className="table"><thead><tr><th>#</th><th>출처</th><th>작업</th><th>시작</th><th>상태</th><th className="r">건수</th><th>메시지</th></tr></thead>
            <tbody>{[...(etl.data || [])].sort((a, b) => (a.status === 'ETL_FAILED' ? -1 : 0) - (b.status === 'ETL_FAILED' ? -1 : 0)).map(r =>
              <tr key={r.runId}><td>{r.runId}</td><td>{r.source}</td><td>{r.job}</td><td>{r.startedAt}</td><td><Badge s={r.status} /></td><td className="r">{num(r.rowCount)}</td><td className="muted">{r.message}</td></tr>)}</tbody></table>
        </State>}
        {tab === 'codes' && <State loading={codes.loading} error={codes.error}>
          <select className="input" value={group} onChange={e => setGroup(e.target.value)}><option value="">그룹 전체</option>{groups.map(g => <option key={g}>{g}</option>)}</select>
          <table className="table"><thead><tr><th>그룹</th><th>코드</th><th>이름</th><th>순서</th><th>사용</th></tr></thead>
            <tbody>{(codes.data || []).filter(c => !group || c.group === group).map(c =>
              <tr key={c.codeId}><td className="muted">{c.groupNm}</td><td><code>{c.codeId}</code></td><td>{c.name}</td><td>{c.sort}</td><td>{c.useYn}</td></tr>)}</tbody></table>
        </State>}
        {tab === 'users' && <State loading={users.loading} error={users.error}>
          <table className="table"><thead><tr><th>#</th><th>이메일</th><th>닉네임</th><th>상태</th></tr></thead>
            <tbody>{(users.data || []).map(u => <tr key={u.userId}><td>{u.userId}</td><td>{u.email}</td><td>{u.nickname}</td><td><Badge s={u.status} /></td></tr>)}</tbody></table>
        </State>}
      </div>}
    </>
  )
}
