"""만개의레시피 수집기 (분석 · 추천용) — 최근 레시피 전부 + 분류 + 상세 · 후기

robots.txt 에서 허용된 경로만, 요청 사이 2~3초 쉬고, 작성자 정보는 저장하지 않음.
기준: 레시피 번호 --min-id 이상 전부 (번호가 시간순이라 기간 제한으로 씀. 1년 전 번호는 count_recent.py --years 1)

1단계  레시피 번호 모으기 (전체 최신순 목록 + 상황별 · 테마별 분류 목록)
  python collect/collect_10000.py list --min-id 7062000
    - 결과: data/raw/recipe_categories.csv  (recipe_id, group, code, name)
      group = 전체 / 상황별 / 테마별 ...  (전체 = 기간 안 모든 레시피, 나머지 = 분류 표)
    - 다른 분류도: --groups 전체,상황별,테마별,종류별,재료별,방법별

2단계  레시피 상세 · 후기 (1단계에서 모은 번호 전부)
  python collect/collect_10000.py detail
  python collect/collect_10000.py detail --limit 20          # 먼저 20개만
    - 결과: data/raw/recipes.jsonl   레시피 1개 = 1줄 (제목 · 이미지 · 소개 · 등록일 · 인분 · 시간 · 난이도 · 조회수
                                 · 평균 별점 · 후기 총개수 · 재료 묶음별 [이름 · 수량 · 만개 재료번호] · 수집 시각)
            data/raw/reviews.csv     후기 1개 = 1줄 (review_id, recipe_id, written_at, stars, text)

멈춰도 다시 실행하면 이어서 받음.
나중에 기간을 늘릴 때: --min-id 를 더 작게 해서 1단계 → 2단계를 다시 실행 (이미 받은 건 건너뜀)

계속 돌리기 (추천: 카프카 서버에서 한 번 띄워 두면 멈추지 않고 돔)
  python collect/collect_10000.py --delay 2.5 run --stop-date 2024-11-01
    한 바퀴 = ① 새 레시피 확인 → ② 새 레시피 상세 → ③ 옛날 레시피 --cycle-minutes 분(기본 60) → ④ 옛날 분류
    → 다시 ① (그래서 새 레시피는 한 시간 안에 들어옴)
    - 막히면(403 · 429 · 503) --blocked-wait 초(기본 1800 = 30분) 쉬고 다시. 계속 막히면 쉬는 시간을 두 배씩 (최대 4시간)
    - --stop-date 에 닿으면 ③은 쉬고, ①②만 --cycle-minutes 마다
    - 같은 폴더에서 수집기가 두 개 돌지 않게 data/raw/collect.lock 으로 막음 (Ctrl+C 로 끄면 지워짐)
    - 정제 · 몽고 적재는 수집 중에도 돌려도 됨 (받은 데까지 읽음)
    - --daily-at 18:00 을 주면 하루 한 번 그 시각이 지나면 daily_pipeline.sh(정제 → KAMIS → 유튜브 → 몽고)를
      따로 띄움 (수집은 멈추지 않음). 오늘 이미 돌았으면 data/raw/daily_last.txt 를 보고 건너뜀
      → 이 명령 하나로 수집 · 정제 · 적재가 다 돌아감 (cron 필요 없음)

매일 한 번에 (정해진 시간에 한 번 돌고 끝나는 방식)
  python collect/collect_10000.py daily --backfill-minutes 120
    ① update  : 최근에 올라온 레시피 번호부터 확인
    ② detail  : ①에서 찾은 새 레시피 상세 · 후기 (일꾼 2)
    ③ backfill: 남는 시간 동안 가지고 있는 가장 옛날 레시피보다 더 옛날 것을 (일꾼 2)
    ④ tags    : ③에서 받은 옛날 레시피에 상황별 · 종류별 분류 붙이기 (분류 목록을 그 번호까지 내려감)

옛날 레시피 분류 붙이기 (tags 만 따로)
  python collect/collect_10000.py --delay 2.5 tags --max-minutes 30
    - 상세 페이지에는 분류가 없어서, 분류별 최신순 목록을 backfill 이 내려간 번호까지 따라 내려감
    - 분류마다 몇 쪽까지 봤는지 data/raw/list_deep.json 에 저장 → 다음엔 그 쪽 근처부터
    - 결과는 recipe_categories.csv 에 추가 → recipe_clean.py 를 다시 돌리면 situation · theme 에 붙음
    - 테마별은 최신순이 아니라서 제외

과거로 거슬러 받기 (backfill 만 따로)
  python collect/collect_10000.py --delay 2.5 backfill --max-minutes 120
    - 가지고 있는 가장 작은 레시피 번호 - 1 부터 번호를 하나씩 내려가며 상세를 받음
      (번호가 등록 순서라 = 점점 옛날 레시피. 지운 · 비공개 번호는 건너뜀)
    - 어디까지 내려갔는지 data/raw/backfill_progress.json 에 저장 → 다음 실행에서 이어서
    - 안 막히게: 일꾼 2개(--workers), 요청마다 --delay 초 이상 쉼, --rest-every 개마다 --rest-sec 초 더 쉼
    - 403 · 429 · 503 이 오면 바로 멈추고 저장 (다음 날 이어서). 종료 코드 2
    - --stop-date 2023-01-01 처럼 주면 그 날짜보다 옛날 레시피가 나오면 멈춤

매일 새 레시피만 (update 만 따로)
  python collect/collect_10000.py update                    → 이어서  detail --workers 2
    - 분류마다 지난번에 본 가장 큰 번호(list_top.json)보다 큰 번호만 받고, 그 번호가 나오면 멈춤
    - list_top.json 이 없으면 recipe_categories.csv 에서 분류별 가장 큰 번호로 시작
    - 테마별 목록은 최신순이 아닐 수 있어서 앞 --theme-pages 쪽(기본 5)만 봄

준비: pip install requests beautifulsoup4 lxml   (lxml 은 페이지 읽기를 빠르게 함)
"""
import os, re, csv, sys, json, time, random, argparse, threading
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P
import kafka_bus as K     # config.ini [kafka] enabled = yes 면 받은 것을 토픽에도 보냄 (아니면 아무것도 안 함)

BASE = 'https://www.10000recipe.com'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
DATA = P.RAW
CAT_FILE = P.CATEGORY_CODES
TAGS = os.path.join(DATA, 'recipe_categories.csv')
PROGRESS = os.path.join(DATA, 'list_progress.json')   # 분류마다 어느 번호까지 받았는지
TOP = os.path.join(DATA, 'list_top.json')             # 분류마다 지금까지 본 가장 큰 번호 (update 용)
BACKFILL = os.path.join(DATA, 'backfill_progress.json')  # 과거로 어디까지 내려갔는지 (backfill 용)
DEEP = os.path.join(DATA, 'list_deep.json')           # 분류 목록을 몇 쪽까지 내려갔는지 (tags 용)
LOCK = os.path.join(DATA, 'collect.lock')             # 수집기 두 개가 같은 파일에 쓰지 않게
DAILY_LAST = os.path.join(DATA, 'daily_last.txt')     # 매일 작업을 마지막으로 띄운 날짜
DAILY_DONE = os.path.join(DATA, 'daily_done.txt')     # 매일 작업이 끝까지 돈 날짜 (daily_pipeline.sh 마지막 줄이 씀)
RECIPES = os.path.join(DATA, 'recipes.jsonl')
REVIEWS = os.path.join(DATA, 'reviews.csv')
DELAY = (2.0, 3.0)        # --delay 로 바꿀 수 있음
_local = threading.local()      # 일꾼마다 연결 하나씩 재사용


def session():
    if not hasattr(_local, 's'):
        _local.s = requests.Session()
        _local.s.headers.update(UA)
    return _local.s


class Blocked(Exception):
    pass
REVIEW_CAP = 500          # 한 페이지에 실리는 후기 최대 개수 (확인값)
try:
    import lxml  # noqa: F401
    PARSER = 'lxml'          # html.parser 보다 몇 배 빠름 (pip install lxml)
except ImportError:
    PARSER = 'html.parser'
SEASONING = re.compile(r'양념|소스|드레싱|조미|시즈닝')


def get(url):
    time.sleep(random.uniform(*DELAY))
    for attempt in range(3):
        try:
            r = session().get(url, timeout=30)
            if r.status_code in (403, 429, 503):
                raise Blocked(r.status_code)
            return r.text
        except requests.RequestException as e:
            print(f'  재시도 {attempt + 1}/3: {e}')
            time.sleep(5)
    return ''


# ───────────────────────── 1단계: 분류 목록 ─────────────────────────
def list_url(param, code, page):
    if param == '':
        return f'{BASE}/recipe/list.html?order=date&page={page}'          # 전체 최신순
    if param == 't1':
        return f'{BASE}/theme/list.html?t1={code}&page={page}'
    return f'{BASE}/recipe/list.html?{param}={code}&order=date&page={page}'


def run_list(a):
    groups = a.groups.split(',')
    cats = [{'param': '', 'group': '전체', 'code': '', 'name': '전체'}] if '전체' in groups else []
    cats += [r for r in csv.DictReader(open(CAT_FILE, encoding='utf-8-sig')) if r['group'] in groups]
    os.makedirs(DATA, exist_ok=True)
    prog = json.load(open(PROGRESS, encoding='utf-8')) if os.path.exists(PROGRESS) else {}
    have = set()
    if os.path.exists(TAGS):
        have = {(r['recipe_id'], r['group'], r['code']) for r in csv.DictReader(open(TAGS, encoding='utf-8-sig'))}
    new = not os.path.exists(TAGS)
    f = open(TAGS, 'a', newline='', encoding='utf-8-sig')
    w = csv.DictWriter(f, fieldnames=['recipe_id', 'group', 'code', 'name'])
    if new:
        w.writeheader()
    for c in cats:
        key = f"{c['group']}|{c['code']}"
        if prog.get(key, 10**9) <= a.min_id:           # 이 기간까지 이미 다 받은 분류
            continue
        seen, page, added = set(), 1, 0
        while page <= a.max_pages:
            html = get(list_url(c['param'], c['code'], page))
            ids = [i for i in dict.fromkeys(int(x) for x in re.findall(r'/recipe/(\d{5,})', html)) if i not in seen]
            if not ids:
                break
            seen.update(ids)
            keep = [i for i in ids if i >= a.min_id]
            for i in keep:
                if (str(i), c['group'], c['code']) not in have:
                    w.writerow({'recipe_id': i, 'group': c['group'], 'code': c['code'], 'name': c['name']})
                    have.add((str(i), c['group'], c['code']))
                    added += 1
            f.flush()
            print(f"{c['group']} {c['name']} p{page}: 기간 안 {len(keep)}/{len(ids)}개 · 새로 {added}개")
            # 테마 목록은 최신순이 아닐 수 있어서 기간으로 멈추지 않고 끝까지 넘김
            if c['param'] != 't1' and len(keep) < len(ids):
                break
            page += 1
        prog[key] = a.min_id
        json.dump(prog, open(PROGRESS, 'w', encoding='utf-8'), ensure_ascii=False)
    f.close()


def run_update(a):
    """매일: 분류마다 지난번 가장 큰 번호보다 새 번호만 받음"""
    groups = a.groups.split(',')
    cats = [{'param': '', 'group': '전체', 'code': '', 'name': '전체'}] if '전체' in groups else []
    cats += [r for r in csv.DictReader(open(CAT_FILE, encoding='utf-8-sig')) if r['group'] in groups]
    os.makedirs(DATA, exist_ok=True)
    have, top = set(), {}
    if os.path.exists(TAGS):
        for r in csv.DictReader(open(TAGS, encoding='utf-8-sig')):
            have.add((r['recipe_id'], r['group'], r['code']))
            k = f"{r['group']}|{r['code']}"
            top[k] = max(top.get(k, 0), int(r['recipe_id']))
    if os.path.exists(TOP):
        top.update(json.load(open(TOP, encoding='utf-8')))
    floor = max(top.values()) if top else 0                # 처음 보는 분류는 전체에서 가장 큰 번호부터
    new = not os.path.exists(TAGS)
    f = open(TAGS, 'a', newline='', encoding='utf-8-sig')
    w = csv.DictWriter(f, fieldnames=['recipe_id', 'group', 'code', 'name'])
    if new:
        w.writeheader()
    total = 0
    for c in cats:
        key = f"{c['group']}|{c['code']}"
        last = top.get(key, floor)
        theme = c['param'] == 't1'
        seen, page, added, best = set(), 1, 0, last
        while page <= (a.theme_pages if theme else a.max_pages):
            html = get(list_url(c['param'], c['code'], page))
            ids = [i for i in dict.fromkeys(int(x) for x in re.findall(r'/recipe/(\d{5,})', html)) if i not in seen]
            if not ids:
                break
            seen.update(ids)
            keep = [i for i in ids if i > last]
            for i in keep:
                best = max(best, i)
                if (str(i), c['group'], c['code']) not in have:
                    w.writerow({'recipe_id': i, 'group': c['group'], 'code': c['code'], 'name': c['name']})
                    have.add((str(i), c['group'], c['code']))
                    added += 1
            f.flush()
            if not theme and len(keep) < len(ids):            # 지난번 번호까지 내려옴
                break
            page += 1
        top[key] = best
        json.dump(top, open(TOP, 'w', encoding='utf-8'), ensure_ascii=False)
        total += added
        print(f"{c['group']} {c['name']}: 새로 {added}개 (기준 번호 {last})")
    f.close()
    print(f'새 번호 {total}개 → 이어서 detail 을 실행하세요')


# ───────────────────────── 2단계: 상세 · 후기 ─────────────────────────
def parse_recipe(html, rid):
    soup = BeautifulSoup(html, PARSER)
    ld = {}
    for sc in soup.find_all('script', type='application/ld+json'):
        try:
            d = json.loads(sc.string or '')
            if isinstance(d, dict) and d.get('@type') == 'Recipe':
                ld = d
        except ValueError:
            pass
    rating = ld.get('aggregateRating') or {}
    txt = lambda el: el.get_text(' ', strip=True) if el else None

    groups = []
    area = soup.find(id='divConfirmedMaterialArea')
    for ul in (area.find_all('ul') if area else []):
        t = ul.find('b', class_='ready_ingre3_tt')
        gname = txt(t) or ''
        items = []
        for li in ul.find_all('li'):
            nm = li.find(class_='ingre_list_name')
            if not nm:
                continue
            a = nm.find('a')
            m = re.search(r"viewMaterial\('(\d+)'\)", a.get('href', '')) if a else None
            note = nm.find(['span', 'p'])           # '100원 동전 크기 정도' 같은 메모
            name = txt(a) if a else txt(nm)
            items.append({'name': name, 'amount': txt(li.find(class_='ingre_list_ea')),
                          'note': txt(note) if note else None, 'material_id': int(m.group(1)) if m else None})
        groups.append({'group': gname, 'is_seasoning': bool(SEASONING.search(gname)), 'items': items})

    hit = soup.select_one('.view_cate_num .hit')
    rec = {
        'recipe_id': rid,
        'title': ld.get('name') or txt(soup.title),
        'image': (ld.get('image') or [None])[0] if isinstance(ld.get('image'), list) else ld.get('image'),
        'description': ld.get('description'),
        'published_at': ld.get('datePublished'),
        'servings': txt(soup.find(class_='view2_summary_info1')),
        'time': txt(soup.find(class_='view2_summary_info2')),
        'difficulty': txt(soup.find(class_='view2_summary_info3')),
        'views': int(re.sub(r'\D', '', hit.get_text())) if hit and re.search(r'\d', hit.get_text()) else None,
        'rating': float(rating['ratingValue']) if rating.get('ratingValue') else None,
        'review_count': int(rating['reviewCount']) if rating.get('reviewCount') else 0,
        'ingredients_flat': ld.get('recipeIngredient') or [],
        'ingredient_groups': groups,
        'crawled_at': time.strftime('%Y-%m-%d %H:%M:%S'),
    }
    return rec, parse_reviews(soup, rid)


def parse_reviews(soup, rid):
    out = []
    for sec in soup.find_all('div', class_='view_reply'):
        tit = sec.find(class_='reply_tit')
        if not tit or '요리 후기' not in tit.get_text():      # 포토 리뷰 · 댓글 영역은 제외
            continue
        for x in sec.find_all('div', class_='reply_list'):
            if 'reply_list_re' in x.get('class', []):       # 작성자 답글(쉐프의 한마디) 제외
                continue
            h = x.find('h4')
            d = re.search(r'20\d\d-\d\d-\d\d \d\d:\d\d:\d\d', h.get_text()) if h else None
            st = x.find(class_='reply_list_star')
            body = x.find('p', class_='reply_list_cont', recursive=False) or x.select_one('.media-body > .reply_list_cont')
            idel = x.find(id=re.compile(r'replyReviewDiv_\d+'))
            out.append({'review_id': int(idel['id'].split('_')[1]) if idel else None, 'recipe_id': rid,
                        'written_at': d.group(0) if d else None,
                        'stars': len(st.find_all('img', src=re.compile(r'star2_on'))) if st else None,
                        'text': body.get_text(' ', strip=True) if body else None})
    return out


def run_detail(a):
    ids = list(dict.fromkeys(int(r['recipe_id']) for r in csv.DictReader(open(TAGS, encoding='utf-8-sig'))))
    if a.min_id:                                         # 목록은 넓게 받아 뒀어도 상세는 이 번호 이상만
        ids = [i for i in ids if i >= a.min_id]
    done = set()
    if os.path.exists(RECIPES):
        for l in open(RECIPES, encoding='utf-8'):
            try:
                done.add(json.loads(l)['recipe_id'])
            except (ValueError, KeyError):              # Ctrl+C 로 끊긴 마지막 줄은 무시 (다시 받음)
                pass
    todo = [i for i in ids if i not in done]
    if a.limit:
        todo = todo[:a.limit]
    print(f'레시피 {len(ids)}개 중 {len(done)}개 완료 · 이번에 {len(todo)}개 · 일꾼 {a.workers}개 '
          f'(예상 {len(todo) * 7 / a.workers / 3600:.1f}시간)')
    newrv = not os.path.exists(REVIEWS)
    rf = open(RECIPES, 'a', encoding='utf-8')
    vf = open(REVIEWS, 'a', newline='', encoding='utf-8-sig')
    vw = csv.DictWriter(vf, fieldnames=['review_id', 'recipe_id', 'written_at', 'stars', 'text'])
    if newrv:
        vw.writeheader()
    lock, stop, count = threading.Lock(), threading.Event(), [0]

    def work(rid):
        if stop.is_set():
            return
        try:
            t0 = time.time()
            html = get(f'{BASE}/recipe/{rid}')
            t1 = time.time()
            if not html:
                return
            rec, reviews = parse_recipe(html, rid)
            t2 = time.time()
            if rec['review_count'] > REVIEW_CAP:                # 500개 넘으면 최신순으로 한 번 더 → 합침
                _, more = parse_recipe(get(f'{BASE}/recipe/{rid}?tg_review_sort=1'), rid)
                seen = {r['review_id'] for r in reviews}
                reviews += [r for r in more if r['review_id'] not in seen]
        except Blocked as e:
            stop.set()
            print(f'\n접속이 막혔어요 (HTTP {e}). 멈춥니다. 한참 쉬었다가 --delay 를 늘려 다시 실행하면 이어서 받아요.')
            return
        except Exception as e:                                  # 한 레시피가 이상해도 계속
            print(f'  {rid} 건너뜀: {e}')
            return
        rec['reviews_collected'] = len(reviews)
        with lock:
            rf.write(json.dumps(rec, ensure_ascii=False) + '\n')
            vw.writerows(reviews)
            rf.flush(); vf.flush()
            K.send_recipe(rec); K.send_reviews(reviews)
            count[0] += 1
            print(f"[{count[0]}/{len(todo)}] {rid} {rec['title'][:25]} · {rec['published_at'][:10] if rec['published_at'] else '-'} "
                  f"· 후기 {len(reviews)}/{rec['review_count']} · 받기 {t1 - t0:.1f}초(쉬는 시간 포함) 읽기 {t2 - t1:.1f}초")

    with ThreadPoolExecutor(max_workers=a.workers) as ex:
        list(ex.map(work, todo))
    rf.close(); vf.close()
    return 2 if stop.is_set() else 0

# ───────────────────────── 3단계: 과거로 거슬러 받기 ─────────────────────────
def is_missing(rec):
    """지운 · 비공개 · 레시피 아닌 번호: 등록일도 재료도 없음"""
    return not rec['published_at'] and not rec['ingredients_flat'] and not any(g['items'] for g in rec['ingredient_groups'])


def run_backfill(a):
    done, low = set(), None
    if os.path.exists(RECIPES):
        for l in open(RECIPES, encoding='utf-8'):
            try:
                i = json.loads(l)['recipe_id']
            except (ValueError, KeyError):
                continue
            done.add(i)
            low = i if low is None else min(low, i)
    st = json.load(open(BACKFILL, encoding='utf-8')) if os.path.exists(BACKFILL) else {}
    nxt = st.get('next_id') or ((low - 1) if low else None)
    if not nxt:
        sys.exit('recipes.jsonl 이 비어 있어요. 먼저 list · detail 로 최근 레시피를 받아 주세요.')
    if st.get('reached_stop_date') and st.get('stop_date') == (a.stop_date or None):
        print(f"이미 --stop-date {a.stop_date} 까지 받았어요. 더 옛날로 가려면 날짜를 바꿔 주세요.")
        return 0
    st.update({'got': st.get('got', 0), 'missing': st.get('missing', 0), 'stop_date': a.stop_date or None,
               'reached_stop_date': False})
    end = time.time() + a.max_minutes * 60
    workers = max(1, min(getattr(a, 'workers', 1), 3))
    newrv = not os.path.exists(REVIEWS)
    rf = open(RECIPES, 'a', encoding='utf-8')
    vf = open(REVIEWS, 'a', newline='', encoding='utf-8-sig')
    vw = csv.DictWriter(vf, fieldnames=['review_id', 'recipe_id', 'written_at', 'stars', 'text'])
    if newrv:
        vw.writeheader()
    print(f"과거로 받기: {nxt}번부터 내려감 · 일꾼 {workers} · 최대 {a.max_minutes:.0f}분 · "
          f"지금까지 {st['got']:,}개 · 빈 번호 {st['missing']:,}개")
    got = miss = streak = since_rest = 0
    code = 0

    def save():
        st['next_id'] = nxt
        st['updated_at'] = time.strftime('%Y-%m-%d %H:%M:%S')
        json.dump(st, open(BACKFILL, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)

    def fetch(rid):                                         # (번호, 레시피, 후기, 오류)
        try:
            html = get(f'{BASE}/recipe/{rid}')
            if not html:
                return rid, None, None, 'empty'
            rec, reviews = parse_recipe(html, rid)
            if rec['review_count'] > REVIEW_CAP:
                _, more = parse_recipe(get(f'{BASE}/recipe/{rid}?tg_review_sort=1'), rid)
                seen = {r['review_id'] for r in reviews}
                reviews += [r for r in more if r['review_id'] not in seen]
            return rid, rec, reviews, None
        except Blocked as e:
            return rid, None, None, f'blocked {e}'
        except Exception as e:
            return rid, None, None, f'skip {e}'

    ex = ThreadPoolExecutor(max_workers=workers)
    try:
        while nxt > 0 and time.time() < end and (not a.max_new or got < a.max_new) and not code:
            batch = []
            k = nxt
            while len(batch) < workers * 5 and k > 0:              # 아직 안 받은 번호 몇 개씩 묶어서
                if k not in done:
                    batch.append(k)
                k -= 1
            if not batch:
                break
            res = sorted(ex.map(fetch, batch), key=lambda x: -x[0])  # 큰 번호(최근) → 작은 번호(옛날) 순서로 처리
            stop_here = None
            for rid, rec, reviews, err in res:
                if err and err.startswith('blocked'):
                    print(f"\n접속이 막혔어요 (HTTP {err.split()[1]}). {rid}번에서 멈추고 저장합니다. "
                          "다음 실행에서 이어서 받아요. (--delay 를 늘려 주세요)")
                    code, stop_here = 2, rid
                    break
                if err == 'empty':                                  # 3번 재시도 실패 → 다음 실행에서 다시
                    print(f'  {rid} 응답 없음 → 멈춤 (다음 실행에서 이 번호부터)')
                    code, stop_here = 4, rid
                    break
                if err:
                    print(f'  {rid} 건너뜀: {err[5:]}')
                    continue
                if is_missing(rec):
                    miss += 1; streak += 1; st['missing'] += 1
                    if streak >= a.max_missing:
                        print(f'빈 번호가 {streak}개 연속 → 페이지 모양이 바뀌었을 수 있어서 멈춤. probe_10000.py 로 확인해 주세요.')
                        code, stop_here = 3, rid - 1
                        break
                    continue
                streak = 0
                if a.stop_date and rec['published_at'] and rec['published_at'][:10] < a.stop_date:
                    print(f"{rid}번 등록일 {rec['published_at'][:10]} < --stop-date {a.stop_date} → 여기서 멈춤")
                    st['reached_stop_date'] = True
                    stop_here = rid
                    break
                rec['reviews_collected'] = len(reviews)
                rf.write(json.dumps(rec, ensure_ascii=False) + '\n')
                vw.writerows(reviews)
                K.send_recipe(rec); K.send_reviews(reviews)
                done.add(rid)
                got += 1; st['got'] += 1
                st['oldest_published'] = rec['published_at'] or st.get('oldest_published')
                print(f"[과거 {got}] {rid} {rec['title'][:25]} · {(rec['published_at'] or '-')[:10]} "
                      f"· 별점 {rec['rating']} · 후기 {len(reviews)}")
            rf.flush(); vf.flush()
            nxt = stop_here if stop_here is not None else batch[-1] - 1
            save()
            if st['reached_stop_date']:
                break
            since_rest += len(batch)
            if a.rest_every and since_rest >= a.rest_every:
                print(f'  {a.rest_every}개마다 쉬기: {a.rest_sec}초')
                time.sleep(a.rest_sec)
                since_rest = 0
    finally:
        ex.shutdown(wait=True)
        save()
        rf.close(); vf.close()
    print(f"이번에 {got}개 받음 · 빈 번호 {miss}개 · 다음 시작 번호 {nxt} · 가장 옛날 등록일 {(st.get('oldest_published') or '-')[:10]}")
    return 2 if code == 2 else 0


def run_tags(a):
    """backfill 로 받은 옛날 레시피에 분류 붙이기: 분류 목록(최신순)을 backfill 번호까지 내려감"""
    st = json.load(open(BACKFILL, encoding='utf-8')) if os.path.exists(BACKFILL) else {}
    floor = st.get('next_id')
    if not floor:
        print('backfill 을 아직 안 돌려서 붙일 옛날 레시피가 없어요.')
        return 0
    groups = [g for g in a.groups.split(',') if g not in ('전체', '테마별')]
    cats = [r for r in csv.DictReader(open(CAT_FILE, encoding='utf-8-sig')) if r['group'] in groups]
    deep = json.load(open(DEEP, encoding='utf-8')) if os.path.exists(DEEP) else {}
    have = set()
    if os.path.exists(TAGS):
        have = {(r['recipe_id'], r['group'], r['code']) for r in csv.DictReader(open(TAGS, encoding='utf-8-sig'))}
    new = not os.path.exists(TAGS)
    f = open(TAGS, 'a', newline='', encoding='utf-8-sig')
    w = csv.DictWriter(f, fieldnames=['recipe_id', 'group', 'code', 'name'])
    if new:
        w.writeheader()
    end = time.time() + a.max_minutes * 60
    total = 0
    for c in cats:
        if time.time() >= end:
            print('시간이 다 돼서 멈춤 (다음 실행에서 이어서)')
            break
        key = f"{c['group']}|{c['code']}"
        d = deep.get(key, {})
        if d.get('low', 10**9) <= floor:                      # 이미 그 번호까지 내려감
            continue
        page = max(1, d.get('page', 1) - a.back_pages)       # 새 레시피가 위에 쌓이면 목록이 밀리므로 몇 쪽 앞부터
        low, added = d.get('low', 10**9), 0
        while page <= a.max_pages and time.time() < end:
            html = get(list_url(c['param'], c['code'], page))
            ids = list(dict.fromkeys(int(x) for x in re.findall(r'/recipe/(\d{5,})', html)))
            if not ids:                                       # 목록 끝 = 이 분류는 다 봄
                low = 0
                break
            for i in ids:
                if i > floor and (str(i), c['group'], c['code']) not in have:   # floor = 아직 안 받은 번호
                    w.writerow({'recipe_id': i, 'group': c['group'], 'code': c['code'], 'name': c['name']})
                    have.add((str(i), c['group'], c['code']))
                    added += 1
            f.flush()
            low = min(low, min(ids))
            if low <= floor:
                break
            page += 1
        deep[key] = {'page': page, 'low': low}
        json.dump(deep, open(DEEP, 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        total += added
        print(f"{c['group']} {c['name']}: 분류 {added}개 추가 · {page}쪽 · 가장 작은 번호 {low if low < 10**9 else '-'}")
    f.close()
    print(f'분류 {total}개 추가 (기준: backfill 번호 {floor} 이상). recipe_clean.py 를 다시 돌리면 붙어요.')
    return 0


def run_daily(a):
    """① 새 레시피 번호 → ② 새 레시피 상세 → ③ 남는 시간에 과거로"""
    t0 = time.time()
    run_update(argparse.Namespace(groups=a.groups, max_pages=50, theme_pages=5))
    if run_detail(argparse.Namespace(limit=0, min_id=0, workers=a.workers)):
        return 2                                           # 막혔으면 과거로 받기도 하지 않음
    left = a.backfill_minutes - (time.time() - t0) / 60 if a.total else a.backfill_minutes
    if left <= 1:
        print('과거로 받기는 시간이 없어 이번엔 건너뜀')
        return 0
    rc = run_backfill(argparse.Namespace(max_minutes=left, max_new=0, stop_date=a.stop_date, workers=a.workers,
                                         rest_every=a.rest_every, rest_sec=a.rest_sec, max_missing=a.max_missing))
    if rc == 2:                                            # 막혔으면 분류 목록도 쉬기
        return rc
    return run_tags(argparse.Namespace(groups=a.tag_groups, max_minutes=a.tags_minutes, max_pages=3000, back_pages=3)) or rc

def take_lock():
    """같은 폴더에서 수집기가 동시에 두 개 돌면 recipes.jsonl 에 줄이 섞이므로 하나만"""
    os.makedirs(DATA, exist_ok=True)
    if os.path.exists(LOCK):
        try:
            pid = int(open(LOCK).read().strip() or 0)
            os.kill(pid, 0)                                  # 아직 살아 있는 수집기
            sys.exit(f'다른 수집기(pid {pid})가 돌고 있어요. 끝난 뒤 실행하거나, 확실히 없으면 {LOCK} 를 지워 주세요.')
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            pass                                             # 죽은 수집기가 남긴 잠금 → 무시
    open(LOCK, 'w').write(str(os.getpid()))


def drop_lock():
    try:
        if open(LOCK).read().strip() == str(os.getpid()):
            os.remove(LOCK)
    except OSError:
        pass


_daily_proc = None


def nap(a, sec):
    """오래 쉬는 동안에도 5분마다 매일 작업 시각을 확인"""
    end = time.time() + sec
    while True:
        left = end - time.time()
        if left <= 0:
            return
        time.sleep(min(left, 300))
        maybe_daily(a)


def maybe_daily(a):
    """--daily-at 시각이 지났고 오늘 아직 안 돌았으면 daily_pipeline.sh 를 따로 띄움 (기다리지 않음)"""
    global _daily_proc
    if not a.daily_at:
        return
    if _daily_proc is not None and _daily_proc.poll() is None:      # 아직 도는 중
        return
    today = time.strftime('%Y-%m-%d')
    # 끝난 기록(daily_done)으로 판단: 도중에 서버가 꺼져 끊긴 날은 넘겨받은 서버가 다시 돌림 (하루 최대 2번)
    done = open(DAILY_DONE).read().strip() if os.path.exists(DAILY_DONE) else ''
    tries = open(DAILY_LAST).read().split() if os.path.exists(DAILY_LAST) else []
    n = tries.count(today)
    if done == today or n >= 2 or time.strftime('%H:%M') < a.daily_at:
        return
    script = os.path.join(P.ROOT, 'daily_pipeline.sh')
    if not os.path.exists(script):
        print(f'{script} 가 없어서 매일 작업을 건너뜀')
        return
    import subprocess
    _daily_proc = subprocess.Popen(['bash', script], cwd=P.ROOT, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    open(DAILY_LAST, 'w').write(' '.join([today] * (n + 1)))      # 오늘 시작한 횟수만큼 날짜를 적음
    print(f"매일 작업 시작 ({n + 1}번째) (pid {_daily_proc.pid}) → 로그: logs/daily_{today}.log")


def run_forever(a):
    """멈추지 않고: ① 새 레시피 → ② 상세 → ③ 옛날 레시피 (cycle 분) → ④ 옛날 분류 → 반복"""
    wait = a.blocked_wait
    n = 0
    while True:
        n += 1
        t0 = time.time()
        print(f"\n===== {n}바퀴 시작 {time.strftime('%Y-%m-%d %H:%M:%S')} =====")
        maybe_daily(a)
        rc = 0
        try:
            st0 = json.load(open(BACKFILL, encoding='utf-8')) if os.path.exists(BACKFILL) else {}
            run_update(argparse.Namespace(groups=a.groups, max_pages=50, theme_pages=5))
            rc = run_detail(argparse.Namespace(limit=0, min_id=0, workers=a.workers))
            if not rc:
                rc = run_backfill(argparse.Namespace(max_minutes=a.cycle_minutes, max_new=0, stop_date=a.stop_date,
                                                     workers=a.workers, rest_every=a.rest_every, rest_sec=a.rest_sec,
                                                     max_missing=a.max_missing))
            if not rc:
                run_tags(argparse.Namespace(groups=a.tag_groups, max_minutes=a.tags_minutes, max_pages=3000, back_pages=3))
        except Blocked as e:                                 # update · tags 에서 막힌 경우
            print(f'접속이 막혔어요 (HTTP {e}).')
            rc = 2
        except SystemExit as e:                              # backfill 의 '비어 있음' 같은 종료는 그대로
            raise
        except Exception as e:                               # 예상 못 한 오류도 멈추지 않고 다음 바퀴
            print(f'오류: {e!r} → 5분 쉬고 다시')
            nap(a, 300)
            continue
        if rc == 2:
            print(f'{wait // 60}분 쉬고 다시 시작해요.')
            nap(a, wait)
            wait = min(wait * 2, 4 * 3600)                   # 계속 막히면 점점 오래 쉼
            continue
        wait = a.blocked_wait
        st1 = json.load(open(BACKFILL, encoding='utf-8')) if os.path.exists(BACKFILL) else {}
        idle = st1.get('reached_stop_date') and st1.get('next_id') == st0.get('next_id')   # 옛날 레시피 다 받음
        left = a.cycle_minutes * 60 - (time.time() - t0)
        nap_s = max(left, a.idle_minutes * 60 if idle else 0)
        if nap_s > 0:
            print(f'이번 바퀴 끝 → {nap_s / 60:.0f}분 뒤 새 레시피 확인')
            nap(a, nap_s)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('list')
    p.add_argument('--groups', default='전체,상황별,테마별', help='전체,상황별,테마별,종류별,재료별,방법별 중 쉼표로')
    p.add_argument('--min-id', type=int, required=True, help='이 번호 이상만 받음 (1년 전 번호: count_recent.py --years 1)')
    p.add_argument('--max-pages', type=int, default=2000)
    p = sub.add_parser('update', help='매일: 지난번 이후 새 레시피 번호만')
    p.add_argument('--groups', default='전체,상황별,테마별,종류별,재료별,방법별')
    p.add_argument('--max-pages', type=int, default=50)
    p.add_argument('--theme-pages', type=int, default=5)
    p = sub.add_parser('detail')
    p.add_argument('--limit', type=int, default=0)
    p.add_argument('--min-id', type=int, default=0, help='이 번호 이상인 레시피만 상세를 받음 (목록을 더 넓게 받아 둔 경우)')
    p.add_argument('--workers', type=int, default=1, help='동시에 받는 개수 (1~3, 기본 1). 일꾼마다 요청 사이 --delay 초 쉼')
    p = sub.add_parser('backfill', help='가진 것보다 옛날 레시피를 번호를 내려가며')
    p.add_argument('--max-minutes', type=float, default=120, help='이번에 최대 몇 분 (기본 120)')
    p.add_argument('--max-new', type=int, default=0, help='이번에 최대 몇 개 (0 = 제한 없음)')
    p.add_argument('--stop-date', default='', help='이 날짜(YYYY-MM-DD)보다 옛날이 나오면 멈춤')
    p.add_argument('--rest-every', type=int, default=200, help='몇 개마다 길게 쉴지 (기본 200)')
    p.add_argument('--rest-sec', type=int, default=60, help='길게 쉬는 초 (기본 60)')
    p.add_argument('--max-missing', type=int, default=300, help='빈 번호가 연속 몇 개면 멈출지')
    p.add_argument('--workers', type=int, default=2, help='동시에 받는 개수 (1~3, 기본 2)')
    p = sub.add_parser('tags', help='backfill 로 받은 옛날 레시피에 분류 붙이기')
    p.add_argument('--groups', default='상황별,종류별', help='정제에서 쓰는 분류만 (재료별 · 방법별은 지금 안 씀)')
    p.add_argument('--max-minutes', type=float, default=30)
    p.add_argument('--max-pages', type=int, default=3000)
    p.add_argument('--back-pages', type=int, default=3, help='지난번 쪽보다 몇 쪽 앞부터 다시 볼지')
    p = sub.add_parser('run', help='멈추지 않고 계속 (새 레시피 확인 → 옛날 레시피 → 반복)')
    p.add_argument('--groups', default='전체,상황별,테마별,종류별,재료별,방법별')
    p.add_argument('--workers', type=int, default=2)
    p.add_argument('--cycle-minutes', type=float, default=60, help='한 바퀴에 옛날 레시피를 받는 분 (= 새 레시피 확인 간격)')
    p.add_argument('--tags-minutes', type=float, default=10)
    p.add_argument('--tag-groups', default='상황별,종류별')
    p.add_argument('--stop-date', default='')
    p.add_argument('--rest-every', type=int, default=200)
    p.add_argument('--rest-sec', type=int, default=60)
    p.add_argument('--max-missing', type=int, default=300)
    p.add_argument('--blocked-wait', type=int, default=1800, help='막혔을 때 처음 쉬는 초 (기본 30분)')
    p.add_argument('--idle-minutes', type=float, default=60, help='옛날 레시피를 다 받은 뒤 새 레시피 확인 간격')
    p.add_argument('--daily-at', default='', help='HH:MM. 하루 한 번 이 시각 뒤에 daily_pipeline.sh 실행 (예: 18:00)')
    p = sub.add_parser('daily', help='update → detail → backfill 을 한 번에 (카프카 주기 작업)')
    p.add_argument('--groups', default='전체,상황별,테마별,종류별,재료별,방법별')
    p.add_argument('--workers', type=int, default=2, help='상세 · 과거로 받기 일꾼 수 (1~3)')
    p.add_argument('--backfill-minutes', type=float, default=120)
    p.add_argument('--tags-minutes', type=float, default=30, help='④ 옛날 레시피 분류 붙이기 시간')
    p.add_argument('--tag-groups', default='상황별,종류별', help='④ 에서 붙일 분류 (정제에서 쓰는 것: 상황별 → situation, 종류별 → dish_type)')
    p.add_argument('--total', action='store_true', help='--backfill-minutes 를 ①②까지 포함한 전체 시간으로')
    p.add_argument('--stop-date', default='')
    p.add_argument('--rest-every', type=int, default=200)
    p.add_argument('--rest-sec', type=int, default=60)
    p.add_argument('--max-missing', type=int, default=300)
    ap.add_argument('--delay', type=float, default=2.0, help='요청 사이 최소 초 (기본 2초, 1초 아래로는 내리지 말 것)')
    a = ap.parse_args()
    DELAY = (max(a.delay, 1.0), max(a.delay, 1.0) + 1.0)
    if a.cmd in ('detail', 'daily', 'backfill', 'run') and not 1 <= a.workers <= 3:
        sys.exit('--workers 는 1~3 사이로 해 주세요 (사이트 부담)')
    take_lock()
    try:
        rc = {'list': run_list, 'update': run_update, 'detail': run_detail,
              'backfill': run_backfill, 'tags': run_tags, 'daily': run_daily, 'run': run_forever}[a.cmd](a)
        sys.exit(rc or 0)
    except KeyboardInterrupt:
        sys.exit('멈췄어요. 다시 실행하면 이어서 받아요.')
    except Blocked as e:
        sys.exit(f'접속이 막혔어요 (HTTP {e}). 멈춥니다. 다시 실행하면 이어서 받아요.')
    finally:
        K.flush()
        drop_lock()
