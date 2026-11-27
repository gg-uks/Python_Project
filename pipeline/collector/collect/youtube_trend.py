"""유튜브 요즘 뜨는 음식 찾기 (YouTube Data API v3)

아는 메뉴 · 재료를 검색하지 않음. '먹방' · '요즘 유행 디저트' 같은 넓은 검색어로 최근 영상을 모으고,
영상 제목 · 해시태그에 나온 음식 이름을 셈 → 최근에 갑자기 많아진 음식 = 트렌드.
  - 음식 이름: "○○ 먹방", "○○ 만들기", "○○ 레시피" 바로 앞 말 + 해시태그(#○○)
  - 메뉴 사전(menu_seed.csv · spelling_norm.csv)에 있으면 표준 메뉴명으로 (만개 · 영양과 이어짐)
    없으면 새 음식 후보 (사전에 아직 없는 것) → 맞으면 menu_seed.csv 에 추가
  - 기간 비교: 최근 30일 vs 그 전 150일 → 기간별 표본 안 비중끼리 비교한 증가 배수

준비: config.ini
  [youtube]
  api_key = 키
검색어: dict/youtube_queries.csv (직접 고쳐도 됨. shorts = Y 면 4분 미만 영상만 → 먹방은 쇼츠 위주)
재료 이름(레시피 20개 이상에 쓰인 재료: 고구마 · 참치캔 · 치즈 …)은 음식 이름으로 안 셈

실행 (프로젝트 폴더에서)
  python collect/youtube_trend.py                    # 검색어 24개 × 기간 2개 × 2페이지 = 검색 96번 (하루 한도 100번)
  python collect/youtube_trend.py --recent-days 14   # 최근 2주 기준
  python collect/youtube_trend.py --rebuild          # 수집 없이 집계만 다시 (메뉴 사전을 고친 뒤)
  주기 작업: 매일 1번 (검색 96번이라 같은 키로 하루에 두 번은 못 돌림. 같은 날 다시 돌리면 그날 회차를 덮어씀) → 실행할 때마다 trend_videos.csv 에 쌓이고(run_date), trend_foods.csv 는 가장 최근 회차 기준

결과 (data/youtube)
  trend_videos.csv               영상 × 검색어 × 기간 × 실행일 (제목 · 채널 · 업로드일 · 조회수 · 좋아요 · 댓글 · 길이(초) · is_shorts
                                 · title_menu: 제목을 레시피 제목과 같은 규칙으로 묶은 메뉴 · foods: 제목에서 찾은 음식 이름)
  trend_foods.csv                음식 이름 1개: 최근 영상 수 · 최근 채널 수 · 이전 영상 수 · 증가 배수(표본 안 비중끼리 비교) · 최근 조회수 합
                                 (채널 2곳 이상만, 확인 필요는 3곳 이상 — 한 채널 해시태그 반복은 뺌)
                                 · menu: 표준 메뉴명 (사전에 있으면) · status: 사전에 있음 / 새 음식 후보 / 확인 필요
  trend_new_food_candidates.csv  사전에 없는 음식만 (menu_seed.csv 에 추가할지 보는 용)
주의: 검색 결과 상위 영상(조회수순) 표본이라 전수가 아님. 같은 회차 안에서 최근 vs 이전 비교용. 조회수는 수집 시점 누적값.
"""
import os, re, sys, time, argparse, datetime, configparser, collections
import requests
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [ROOT, os.path.join(ROOT, 'clean')]
import paths as P
import menu_group as mg                       # 레시피 제목과 같은 메뉴 사전 · 같은 규칙

OUT = P.YOUTUBE
API = 'https://www.googleapis.com/youtube/v3'
VIDEOS = os.path.join(OUT, 'trend_videos.csv')
FOODS = os.path.join(OUT, 'trend_foods.csv')
NEW = os.path.join(OUT, 'trend_new_food_candidates.csv')
QUERY_FILE = os.path.join(P.DICT, 'youtube_queries.csv')
DEFAULT_QUERIES = ['먹방', '디저트 먹방', '신메뉴 먹방', '레시피', '요즘 유행 음식', '요즘 유행 디저트', '요즘 유행 레시피']
# 검색어 1개 = 검색 4번 (기간 2 × 페이지 2). 하루 검색 100번 한도 → 검색어 24개까지

ANCHOR = re.compile(r'([가-힣A-Za-z]{2,12}(?:\s[가-힣A-Za-z]{2,8})?)\s*(?=먹방|만들기|레시피|황금레시피|만드는\s?법|맛있게|꿀조합|리뷰|ASMR)')
HASHTAG = re.compile(r'#([가-힣A-Za-z]{2,15})')
FOOD_END = ('찌개', '국', '탕', '전골', '볶음', '조림', '무침', '나물', '전', '찜', '구이', '튀김', '밥', '덮밥', '죽', '국수', '면',
            '라면', '김치', '샐러드', '샌드위치', '떡볶이', '스테이크', '카레', '파스타', '피자', '버거', '치킨', '만두', '떡', '빵',
            '케이크', '쿠키', '타르트', '푸딩', '젤리', '초콜릿', '초코', '아이스크림', '빙수', '라떼', '스무디', '에이드', '주스',
            '마카롱', '도넛', '와플', '토스트', '김밥', '초밥', '꼬치', '탕후루', '쫀쿠', '과자', '칩', '잼', '수프', '스프', '라멘', '우동', '커리')
STOP = {'먹방', '레시피', '만들기', '요리', '음식', '간단', '초간단', '맛있게', '꿀조합', '리뷰', '요즘', '유행', '신상', '편의점', '디저트',
        '오늘', '진짜', '역대급', '난리난', '핫한', '인기', '꿀맛', '최애', '대왕', '소스', '집에서', '쉬운', '자취', '혼밥', '브이로그', 'vlog',
        'ASMR', 'asmr', 'shorts', 'Shorts', '쇼츠', '먹방ASMR', 'mukbang', 'Mukbang', 'MUKBANG', 'eating', 'recipe', 'Recipe', '한국',
        '레전드', '대박', '꿀팁', '황금', '간식', '야식', '편의점음식', '먹방브이로그', '맛집', '꿀템', '추천'}
STOP |= {'집밥', '일상', '자취요리', '초간단요리', '초간단레시피', '간단요리', '집밥레시피', '간식만들기', '디저트만들기', '요리브이로그',
         '한국여행', '여행', '편의점신상', '편의점꿀조합', '꿀조합', '신메뉴', '신메뉴리뷰', '한정', '한정판', '홈베이킹', '베이킹', '홈카페', '홈파티',
         '다이어트', '다이어트식단', '식단', '쿡방', '먹방유튜버', '데이트', '언박싱', '챌린지', '맛집', '맛집추천', '리뷰', '솔직리뷰', '내돈내산',
         '도시락', '아침', '점심', '저녁', '밥상', '반찬', '밑반찬', '술안주', '안주', '혼술', '캠핑', '캠핑요리', '파티', '크리스마스', '할로윈'}
STOP |= {'강아지', '종류별', '솔직', '이모지', '맛있는', '밥도둑', '애니', '한식', '중식', '일식', '양식', '시간', '카페', '전메뉴', '일본', '미국',
         '팩폭', '건강', '건강식', '리얼', '풀세트', '흑백요리사', '세입', '한판', '외국인', '먹는', '연예인', '유행하는', '스퀴시', '전자레인지',
         '유지어터', '밀프렙', '한정선', '광고', '현실', '유머', '공감', '폭풍', '어때', '이슈', '트렌드', '요즘유행', '유행음식', '가성비', '먹잘알',
         '최강', '비밀', '인생', '메뉴', '귀여운', '엄마의', '엄마표', '다이소', '길밥', '집순이', '저메추', '음료', '디저트', '동결건조', '제철음식',
         '대한민국', '코스트코', '편의점', '세븐일레븐', 'GS편의점', '도전', '기념', '먹방브이로그', '모음', '단계별', '후기', '종류', '다양한',
         '이게', '하기', '없는', '모르는', '풀코스', '나혼산', '예능', '넷플릭스', '아이디어', '저당', '팔로워', '만원어치', '말먹', '부어서', '말아서',
         '리센느', '리센느빵', '편의점라면', '아침밥', '초코', '맛있는한끼', '명장면', '반전', '사극', '장원영', '아이돌', '유튜버', '연예인추천템', '쇼핑쇼츠', '썰쇼츠', '해외반응', '외국인반응', 'k푸드'}
GENERIC_END = re.compile(r'(추천|추천템|꿀팁|꿀템|요리|레시피|간식|식단|반응|조합|꿀조합|브이로그|로그|먹방|리뷰|도시락|메뉴|투어|맛집|템|만들기|신상|신상음식|털이|파티)$')
TAIL = re.compile(r'(만들기|만드는법|레시피|황금레시피|먹방|요리법|리뷰|ASMR|asmr)$')   # '#빼빼로만들기' → 빼빼로


def base(w):
    w = mg.spell(w)
    b = TAIL.sub('', w)
    return b if len(b) >= 2 else w


MODIFIER_END = ('한', '는', '난', '운', '은', '된', '진', '던')     # 핫한 · 맛있는 · 난리난 같은 꾸밈말
CTRL = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')                # 보이지 않는 제어 문자 → 엑셀이 '파일 손상'으로 봄
STATUS = {'사전': '사전에 있음', '후보': '새 음식 후보', '확인': '확인 필요'}


def clean(x):
    return CTRL.sub('', x) if isinstance(x, str) else x


def api_key():
    cfg = configparser.ConfigParser()
    cfg.read(P.CONFIG, encoding='utf-8')
    k = cfg.get('youtube', 'api_key', fallback='').strip()
    if not k or k.startswith('여기에'):
        sys.exit('config.ini 의 [youtube] api_key 를 채워 주세요.')
    return k


class QuotaOver(Exception):
    pass


def get(path, params):
    for attempt in range(3):
        try:
            r = requests.get(f'{API}/{path}', params=params, timeout=30)
        except requests.RequestException as e:
            print(f'    재시도 {attempt + 1}/3: {e}')
            time.sleep(5 * (attempt + 1))
            continue
        if r.status_code == 403 and 'quota' in r.text.lower():
            raise QuotaOver()
        if r.status_code != 200:
            print(f'    API 오류 {r.status_code}: {r.text[:200]}')
            return {}
        return r.json()
    return {}


def queries():
    """[(검색어, 쇼츠만?)]  youtube_queries.csv 의 shorts = Y 면 4분 미만 영상만 검색 (먹방은 쇼츠가 많음)"""
    if os.path.exists(QUERY_FILE):
        d = pd.read_csv(QUERY_FILE, dtype=str, keep_default_na=False)
        d['query'] = d['query'].str.strip()
        sh = d['shorts'].str.strip().str.upper().eq('Y') if 'shorts' in d else d['query'].str.contains('먹방')
        return [(q, bool(x)) for q, x in dict(zip(d['query'], sh)).items() if q]
    return [(q, '먹방' in q) for q in DEFAULT_QUERIES]


DUR = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')


def seconds(iso):
    m = DUR.fullmatch(str(iso or ''))
    return (int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)) if m else None


def search(q, after, before, key, short=False, pages=2):
    ids, token = [], None
    for _ in range(pages):
        p = {'part': 'snippet', 'q': q, 'type': 'video', 'maxResults': 50, 'regionCode': 'KR', 'relevanceLanguage': 'ko',
             'order': 'viewCount', 'publishedAfter': after, 'publishedBefore': before, 'key': key}
        if short:
            p['videoDuration'] = 'short'                                 # 4분 미만 (쇼츠는 3분까지)
        if token:
            p['pageToken'] = token
        d = get('search', p)
        ids += [it['id']['videoId'] for it in d.get('items', []) if it.get('id', {}).get('videoId')]
        token = d.get('nextPageToken')
        if not token:
            break
    rows = []
    for i in range(0, len(ids), 50):
        v = get('videos', {'part': 'snippet,statistics,contentDetails', 'id': ','.join(ids[i:i + 50]), 'key': key})
        for it in v.get('items', []):
            sn, st = it.get('snippet', {}), it.get('statistics', {})
            rows.append({'video_id': it['id'], 'title': clean(sn.get('title', '')), 'channel': clean(sn.get('channelTitle')),
                         'published_at': sn.get('publishedAt'), 'views': int(st.get('viewCount', 0) or 0),
                         'likes': int(st['likeCount']) if st.get('likeCount') else None,
                         'comments': int(st['commentCount']) if st.get('commentCount') else None,
                         'duration_sec': seconds((it.get('contentDetails') or {}).get('duration'))})
    return rows


# ───────────── 제목 → 음식 이름 ─────────────
def dictionary():
    menus, to_std = mg.load_dictionary(P.MENU_SEED)
    return to_std, mg.build_matcher(to_std.keys()), mg.gap_rules(menus, to_std)


def ingredients(min_recipes=20):
    """레시피 20개 이상에 쓰인 재료 (고구마 · 참치캔 · 치즈 …) → 음식 이름으로 안 셈. 빼빼로 · 소금빵 같은 건 재료로 드물어서 남음"""
    p = P.clean('ingredient_dictionary.csv')
    if not os.path.exists(p):
        return set()
    d = pd.read_csv(p)
    return {mg.spell(str(x)) for x in d.loc[d['recipes'] >= min_recipes, 'std_name']}


INGREDIENTS = None


def suffix_menu(word, to_std):
    """낱말이 사전 메뉴 이름으로 끝나면 그 메뉴 (가장 긴 것). 메뉴 이름은 3글자 이상만 (2글자는 우연히 겹침: 강아지 ≠ 아지)"""
    for i in range(1, len(word) - 2):
        if word[i:] in to_std:
            return to_std[word[i:]]
    return None


def foods_in(title, to_std):
    """제목에서 음식 이름 → {(이름, 상태)}  상태: 사전 = 메뉴 사전에 있음 / 후보 = 음식 끝말로 찾은 새 음식 / 확인 = 음식인지 모름"""
    t = re.sub(r'\[.*?\]|\(.*?\)|【.*?】|[|/·~!?.,…♥❤️★☆"\'“”‘’]', ' ', title)
    phrases = [[base(h)] for h in HASHTAG.findall(title)]
    for m in ANCHOR.finditer(t):
        words = [w for w in m.group(1).split() if w not in STOP]
        if words:
            phrases.append(words[-2:])
    out = set()
    for words in phrases:
        last = base(words[-1])
        first = words[0] if len(words) == 2 else None
        if first and (first.endswith(MODIFIER_END) or first in STOP):
            first = None
        if last in STOP or len(last) < 2 or (last not in to_std and GENERIC_END.search(last)):
            continue                                                 # 고구마간식 · 라면꿀조합 · 직장인도시락 · 외국인반응 → 음식 이름 아님
        global INGREDIENTS
        if INGREDIENTS is None:
            INGREDIENTS = ingredients()
        if last in INGREDIENTS and last not in to_std and not (first and mg.spell(first + last) in to_std):
            continue                                                 # 재료 이름 (고구마 · 참치캔) → 메뉴가 아님
        if first and mg.spell(first + last) in to_std:              # 두 말을 붙이면 사전 메뉴 (두바이 + 쫀득쿠키)
            out.add((to_std[mg.spell(first + last)], '사전'))
        elif last in to_std:
            out.add((to_std[last], '사전'))
        elif suffix_menu(last, to_std):                             # 왁뿌소금빵 → 소금빵 · 순두부짬뽕 → 짬뽕 (꾸밈말 + 사전 메뉴)
            out.add((suffix_menu(last, to_std), '사전'))
        elif last.endswith(FOOD_END):
            out.add((last, '후보'))
            if first:
                out.add((mg.spell(first + last), '후보'))
        elif not re.fullmatch(r'[A-Za-z]+', last):
            out.add((last, '확인'))                                 # 엽떡 · 크룽지 같은 것 → 많이 나올 때만 남김
    return out


def rebuild(recent_days, before_days):
    v = pd.read_csv(VIDEOS)
    to_std, pat, rules = dictionary()
    if 'duration_sec' in v:
        v['is_shorts'] = v['duration_sec'].le(180)                     # 쇼츠 = 3분 이하
    v['title_menu'] = v['title'].map(lambda t: mg.match_best(str(t), pat, to_std, rules)[0])
    v['foods'] = v['title'].map(lambda t: '|'.join(sorted(n for n, _ in foods_in(str(t), to_std))))
    v.to_csv(VIDEOS, index=False, encoding='utf-8-sig')
    last = v['run_date'].max()
    r = v[v['run_date'] == last].drop_duplicates(['video_id', 'period'])     # 여러 검색어에 걸린 같은 영상은 한 번만
    # 표본 전체 영상 수 — 기간마다 검색 결과 개수가 달라서 '표본 안 비중'끼리 비교
    n_recent = max((r['period'] == '최근').sum(), 1)
    n_before = max((r['period'] == '이전').sum(), 1)
    cnt = collections.defaultdict(lambda: {'최근': 0, '이전': 0, 'views': 0, 'status': '', 'example': '', 'channels': set()})
    for _, x in r.iterrows():
        for name, status in foods_in(str(x['title']), to_std):
            c = cnt[name]
            c[x['period']] += 1
            c['status'] = status
            if x['period'] == '최근':
                c['views'] += int(x['views'] or 0)
                c['channels'].add(x['channel'])
                c['example'] = c['example'] or str(x['title'])[:60]
    rows = []
    for name, c in cnt.items():
        rows.append({'run_date': last, 'food': name, 'menu': name if c['status'] == '사전' else None,
                     'status': STATUS[c['status']], 'recent_videos': c['최근'], 'recent_channels': len(c['channels']),
                     'before_videos': c['이전'],                     # growth = 최근 표본 안 비중 / 이전 표본 안 비중
                     'growth': round(((c['최근'] + 0.5) / n_recent) / ((c['이전'] + 0.5) / n_before), 2), 'recent_views': c['views'], 'example_title': c['example']})
    cols = ['run_date', 'food', 'menu', 'status', 'recent_videos', 'recent_channels', 'before_videos', 'growth', 'recent_views', 'example_title']
    f = pd.DataFrame(rows, columns=cols)
    # 한 채널이 자기 해시태그를 반복한 건 트렌드가 아님 → 최근 영상을 올린 채널이 2곳 이상 (확인 필요는 3곳 이상)
    f = f[(f['recent_channels'] >= 2) & ((f['status'] != '확인 필요') | (f['recent_channels'] >= 3))]
    f = f.sort_values(['growth', 'recent_views'], ascending=False)
    f.to_csv(FOODS, index=False, encoding='utf-8-sig')
    f[f['status'] != '사전에 있음'].to_csv(NEW, index=False, encoding='utf-8-sig')
    known = (f['status'] == '사전에 있음').sum()
    print(f'\n{last} 회차: 영상 {r["video_id"].nunique():,}개 · 음식 이름 {len(f)}개 (사전에 있음 {known} · 새 음식 후보 · 확인 필요 {len(f) - known})')
    print(f'  → {FOODS}\n  → {NEW}  (음식이 맞으면 menu_seed.csv 에 추가 → --rebuild)')
    if len(f):
        print(f.head(20)[['food', 'status', 'recent_videos', 'recent_channels', 'before_videos', 'growth', 'recent_views']].to_string(index=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--recent-days', type=int, default=30, help='최근 기간 (기본 30일)')
    ap.add_argument('--before-days', type=int, default=150, help='비교할 이전 기간 길이 (기본 150일 = 5개월)')
    ap.add_argument('--rebuild', action='store_true', help='수집 없이 집계만 다시 (메뉴 사전을 고친 뒤)')
    a = ap.parse_args()
    os.makedirs(OUT, exist_ok=True)
    if a.rebuild:
        return rebuild(a.recent_days, a.before_days)
    key = api_key()
    now = datetime.datetime.utcnow()
    z = lambda d: d.strftime('%Y-%m-%dT%H:%M:%SZ')
    r_from = now - datetime.timedelta(days=a.recent_days)
    b_from = r_from - datetime.timedelta(days=a.before_days)
    periods = {'최근': (z(r_from), z(now)), '이전': (z(b_from), z(r_from))}
    run_date = now.strftime('%Y-%m-%d')
    qs = queries()
    print(f"쇼츠만 검색: {', '.join(q for q, sh in qs if sh) or '없음'}")
    if len(qs) * 4 > 100:
        print(f'검색어 {len(qs)}개 = 검색 {len(qs) * 4}번 → 하루 한도 100번을 넘어서 앞 25개만 씀')
        qs = qs[:25]
    print(f'검색어 {len(qs)}개 × 기간 2개 (최근 {a.recent_days}일 / 그 전 {a.before_days}일)')
    vids = []
    try:
        for q, short in qs:
            for label, (s, e) in periods.items():
                rows = search(q, s, e, key, short)
                vids += [{'run_date': run_date, 'query': q, 'shorts_search': short, 'period': label, **r} for r in rows]
                print(f'  "{q}"{" (쇼츠)" if short else ""} {label}: 영상 {len(rows)}개')
                time.sleep(0.5)
    except QuotaOver:
        print('\n오늘 할당량을 다 썼어요. 모은 것까지만 저장해요.')
    if not vids:
        return
    v = pd.DataFrame(vids).drop_duplicates(['run_date', 'query', 'period', 'video_id'])
    if os.path.exists(VIDEOS):                                           # 같은 날 다시 돌리면 그날 회차를 새로 씀
        old = pd.read_csv(VIDEOS)
        v = pd.concat([old[old['run_date'] != run_date], v], ignore_index=True)
    v.to_csv(VIDEOS, index=False, encoding='utf-8-sig')
    rebuild(a.recent_days, a.before_days)
    send_kafka(run_date)


def send_kafka(run_date):
    """이번 회차 영상만 토픽으로 (config.ini [kafka] enabled = yes 일 때만)"""
    import kafka_bus as K
    if not K.settings():
        return
    v = pd.read_csv(VIDEOS, encoding='utf-8-sig', dtype=str)
    rows = v[v['run_date'] == run_date].where(v.notna(), None).to_dict('records')
    K.send_youtube(rows)
    K.flush()


if __name__ == '__main__':
    main()
