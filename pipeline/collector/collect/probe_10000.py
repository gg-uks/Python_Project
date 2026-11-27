"""만개의레시피 구조 확인용 (레시피 1개 + 목록 1페이지)

실행
  python collect/probe_10000.py 레시피번호
  python collect/probe_10000.py 레시피번호 "브라우저에서 복사한 목록 주소"

하는 일
  0. robots.txt 에서 /recipe/ · 목록 · 테마 경로가 허용되는지 확인
  1. 레시피 페이지를 받아 probe_recipe_<번호>.html 로 저장
  2. 페이지 안의 구조화 데이터(JSON-LD)가 있으면 출력 (제목 · 등록일 · 별점 · 재료가 들어 있는 경우가 많음)
  3. [재료] / [양념 재료] 같은 묶음과 재료 줄, 후기로 보이는 부분을 찾아 앞부분만 출력
  4. 목록 주소를 주면 그 페이지의 레시피 번호를 뽑아 출력 (분류 · 테마 수집 방식 확인용)
결과 화면 출력과 저장된 html 파일을 보내 주면 수집 코드를 맞춰 짤 수 있음
"""
import os, re, sys, json, time
from urllib.robotparser import RobotFileParser
import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P

from bs4 import BeautifulSoup

BASE = 'https://www.10000recipe.com'
UA = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}


def check_robots(extra_url=None):
    rp = RobotFileParser(f'{BASE}/robots.txt'); rp.read()
    urls = [f'{BASE}/recipe/6912345', f'{BASE}/recipe/list.html?order=date&page=1', f'{BASE}/theme/list.html?t1=101014']
    if extra_url:
        urls.append(extra_url)
    print('== robots.txt')
    for u in urls:
        print(' ', rp.can_fetch('*', u), u)
    print('  crawl_delay:', rp.crawl_delay('*'))


def show(label, text, n=400):
    text = re.sub(r'\s+', ' ', text or '').strip()
    print(f'  {label}: {text[:n]}')


def probe_recipe(no):
    r = requests.get(f'{BASE}/recipe/{no}', headers=UA, timeout=30)
    print(f'\n== 레시피 {no}  HTTP {r.status_code}  {len(r.text):,}자')
    open(os.path.join(P.RAW, f'probe_recipe_{no}.html'), 'w', encoding='utf-8').write(r.text)
    print(f'  저장: probe_recipe_{no}.html')
    soup = BeautifulSoup(r.text, 'html.parser')

    print('\n== 구조화 데이터 (JSON-LD)')
    found = False
    for s in soup.find_all('script', type='application/ld+json'):
        try:
            d = json.loads(s.string or '')
        except ValueError:
            continue
        found = True
        for k in ('@type', 'name', 'description', 'datePublished', 'dateModified', 'aggregateRating', 'recipeIngredient', 'recipeCategory', 'keywords'):
            if isinstance(d, dict) and k in d:
                print(f'  {k}: {json.dumps(d[k], ensure_ascii=False)[:300]}')
    if not found:
        print('  없음')

    print('\n== 제목 · 소개 · 메타')
    show('title 태그', soup.title.string if soup.title else '')
    for prop in ('og:title', 'og:description', 'og:image'):
        m = soup.find('meta', property=prop)
        show(prop, m.get('content') if m else '')

    print('\n== 재료 묶음 ([재료] / [양념 재료] 등)')
    for b in soup.find_all(string=re.compile(r'^\s*\[.*재료.*\]\s*$'))[:6]:
        box = b.find_parent(['div', 'ul', 'section']) or b.parent
        cls = ' '.join(box.get('class', [])) if box else ''
        print(f"  묶음 '{b.strip()}'  ← 부모 태그 <{box.name} id='{box.get('id', '')}' class='{cls}'>")
        lis = box.find_all('li')[:4] if box else []
        for li in lis:
            show('    줄', li.get_text(' | ', strip=True), 120)

    print('\n== 날짜로 보이는 것 (등록일 · 후기 날짜 후보)')
    dates = re.findall(r'20\d\d[-./]\d{1,2}[-./]\d{1,2}(?:\s+\d{1,2}:\d{2})?', r.text)
    print('  ', sorted(set(dates))[:15], f'... 총 {len(set(dates))}개')

    print('\n== 후기로 보이는 부분')
    for kw in ('후기', '요리후기', '댓글'):
        hits = soup.find_all(string=re.compile(kw))[:3]
        for h in hits:
            p = h.find_parent(['div', 'section'])
            if p:
                cls = ' '.join(p.get('class', []))
                show(f"'{kw}' ← <{p.name} id='{p.get('id', '')}' class='{cls}'>", p.get_text(' ', strip=True), 200)

    print('\n== 별점으로 보이는 것')
    for el in soup.find_all(class_=re.compile(r'star|rating|grade', re.I))[:5]:
        show(f"<{el.name} class='{' '.join(el.get('class', []))}'>", el.get_text(' ', strip=True) or str(el)[:150], 150)


def probe_list(url):
    time.sleep(2)
    r = requests.get(url, headers=UA, timeout=30)
    ids = list(dict.fromkeys(re.findall(r'/recipe/(\d{5,})', r.text)))
    print(f'\n== 목록 {url}\n  HTTP {r.status_code} · 레시피 번호 {len(ids)}개: {ids[:10]}')
    open(os.path.join(P.RAW, 'probe_list.html'), 'w', encoding='utf-8').write(r.text)
    print('  저장: probe_list.html')


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__); sys.exit()
    list_url = sys.argv[2] if len(sys.argv) > 2 else None
    check_robots(list_url)
    probe_recipe(sys.argv[1])
    if list_url:
        probe_list(list_url)
