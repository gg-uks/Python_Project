import { useEffect, useState } from 'react'
import { Routes, Route, Link, NavLink, Navigate, useNavigate, useLocation, useParams } from 'react-router-dom'
import { api, auth, isMock } from './api'
import { Main, Candidates } from './pages/Recommend'
import Explore from './pages/Explore'
import RecipeList from './pages/RecipeList'
import RecipeDetail from './pages/RecipeDetail'
import Fridge from './pages/Fridge'
import MenuDetail from './pages/MenuDetail'
import Trends from './pages/Trends'
import { Login, Signup } from './pages/Auth'
import { ErrorBoundary, useApi } from './components/ui'
import MyPage from './pages/MyPage'
import Admin from './pages/Admin'
import Compare from './pages/Compare'
import ChatBot from './components/ChatBot'
import OmmMark from './components/OmmMark'
import SearchBox from './components/SearchBox'
import Search from './pages/Search'
import { CompareBar } from './components/dn'

// UI v3: 윗쪽 주 메뉴 4개 (시안) + 보조 메뉴 (레시피 검색 · 냉장고 털기)
const MAIN_NAV = [
  ['/', '메뉴 추천', p => p === '/' || p.startsWith('/recommend') || p.startsWith('/menus')],
  ['/explore', '재료 탐색'],
  ['/trends', '음식 트렌드'],
]
const SUB_NAV = [['/recipes', '레시피 검색'], ['/fridge', '냉장고 털기']]

const ALL_MENU = [
  ['메뉴 고르기', [['/', '메뉴 추천'], ['/recommend', '조건별 추천 결과'], ['/compare', '메뉴 비교']]],
  ['레시피', [['/recipes', '레시피 검색'], ['/recipes?sort=cost', '1인분 싼 레시피'], ['/recipes?sort=value', '가성비 레시피'], ['/fridge', '냉장고 털기']]],
  ['물가 · 재료', [['/explore', '재료 탐색 · 시세'], ['/explore#price-interest', '시세 × 관심도']]],
  ['트렌드', [['/trends', '음식 트렌드']]],
  ['내 정보', [['/mypage?tab=meals', '먹은 기록'], ['/mypage?tab=prefs', '취향 설정']]],
]

function Header() {
  const navigate = useNavigate()
  const { pathname } = useLocation()
  const [all, setAll] = useState(false)
  const loggedIn = Boolean(auth.token())
  const k = useApi(() => (isMock ? Promise.resolve(null) : api.insight().catch(() => null)))
  useEffect(() => setAll(false), [pathname])
  return (
    <header className="dn-header">
      <div className="dn-util">
        <div className="dn-in">
          <span className="dn-util-l">{isMock ? '예시 데이터로 보는 중' : k.data?.ym ? `재료 시세 KAMIS ${k.data.ym} 기준 · 레시피 만개의레시피` : '오늘 뭐 먹지 · 시세로 고르는 메뉴'}</span>
          <div className="dn-util-r">
            {loggedIn ? <>
              <NavLink to="/mypage" className="dn-me">{auth.nickname() || '내'}님</NavLink>
              <NavLink to="/mypage?tab=meals">먹은 기록</NavLink>
              {auth.isAdmin() && <NavLink to="/admin">관리</NavLink>}
              <button type="button" onClick={async () => { await api.logout(); navigate('/') }}>로그아웃</button>
            </> : <>
              <NavLink to="/login">로그인</NavLink>
              <NavLink to="/signup">회원가입</NavLink>
            </>}
          </div>
        </div>
      </div>
      <div className="dn-bar">
        <div className="dn-in">
          <Link to="/" className="dn-logo has-mark" aria-label="OMM 처음으로"><OmmMark size={58} tall /><span className="dn-logo-txt"><b>오늘 뭐 먹지</b><span>OMM · 시세로 고르는 메뉴</span></span></Link>
          <SearchBox />
          <nav className="dn-quick" aria-label="바로가기">
            <Link to="/fridge"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3h10a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Z M5 10h14 M8 6v1 M8 13v3" /></svg>냉장고</Link>
            <Link to="/compare"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h7v12H4z M13 6h7v12h-7z" /></svg>비교함</Link>
            <Link to={loggedIn ? '/mypage?tab=meals' : '/login?next=/mypage'}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12.5L10 17.5L19 7" /></svg>먹은 기록</Link>
          </nav>
        </div>
      </div>
      <div className="dn-cat">
        <div className="dn-in">
          <div className="dn-all">
            <button type="button" aria-expanded={all} onClick={() => setAll(!all)}>
              <svg width="16" height="16" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M4 12h16M4 17h16" stroke="currentColor" strokeWidth="2" strokeLinecap="round" /></svg>전체 메뉴
            </button>
            {all && (
              <div className="dn-all-panel">
                {ALL_MENU.map(([g, items]) => (
                  <div key={g}><b>{g}</b>{items.map(([to, l]) => <Link key={to} to={to}>{l}</Link>)}</div>
                ))}
              </div>
            )}
          </div>
          <nav aria-label="주 메뉴" className="dn-nav">
            {MAIN_NAV.map(([to, label, match]) => {
              const on = match ? match(pathname) : pathname.startsWith(to)
              return <NavLink key={to} to={to} className={on ? 'on' : ''} end={to === '/'}>{label}</NavLink>
            })}
            {SUB_NAV.map(([to, label]) => <NavLink key={to} to={to} className={({ isActive }) => `sub ${isActive ? 'on' : ''}`}>{label}</NavLink>)}
          </nav>
        </div>
      </div>
    </header>
  )
}

const ToExplore = () => { const { id } = useParams(); return <Navigate to={`/explore?id=${id}`} replace /> }

export default function App() {
  const loc = useLocation()
  return (
    <div className="v3 dn">
      <Header />
      <main className="v3-main">
        <ErrorBoundary resetKey={loc.pathname + loc.search}>
          <Routes>
            <Route path="/" element={<Main />} />
            <Route path="/recommend" element={<Candidates />} />
            <Route path="/menus/:id" element={<MenuDetail />} />
            <Route path="/insight" element={<Navigate to="/explore" replace />} />
            <Route path="/explore" element={<Explore />} />
            <Route path="/ingredients/:id" element={<ToExplore />} />
            <Route path="/trends" element={<Trends />} />
            <Route path="/search" element={<Search />} />
            <Route path="/recipes" element={<RecipeList />} />
            <Route path="/recipes/:id" element={<RecipeDetail />} />
            <Route path="/fridge" element={<Fridge />} />
            <Route path="/compare" element={<Compare />} />
            <Route path="/analysis" element={<Navigate to={`/admin?tab=analysis${loc.search.replace('?', '&')}`} replace />} />
            <Route path="/login" element={<Login />} />
            <Route path="/signup" element={<Signup />} />
            <Route path="/mypage" element={<MyPage />} />
            <Route path="/admin" element={<Admin />} />
            <Route path="*" element={<div className="state">없는 페이지예요. <Link to="/">메인으로</Link></div>} />
          </Routes>
        </ErrorBoundary>
      </main>
      <footer className="v3-footer">
        <div>
          <b>OMM</b> · 오늘 뭐 먹지 — 메뉴 추천 + 재료 시세 · 레시피 데이터<br />
          <span>데이터: 만개의레시피(수업용 · 원문 링크 연결), KAMIS 농산물 가격, 한국소비자원 참가격, 식약처 영양성분, YouTube Data API</span>
          <br /><Link to="/admin">관리자</Link>
        </div>
      </footer>
      <CompareBar />
      <ChatBot />
    </div>
  )
}
