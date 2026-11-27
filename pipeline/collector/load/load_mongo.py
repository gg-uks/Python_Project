"""수집 원본 → MongoDB(omm-rs 레플리카셋, OMM DB) 적재

    python load/load_mongo.py                 # 6개 컬렉션 전부
    python load/load_mongo.py recipes reviews # 골라서
    python load/load_mongo.py --dry-run       # 접속 없이 문서만 만들어 건수 · 첫 문서 확인

- 레플리카셋 주소로 접속하므로 드라이버가 프라이머리를 찾아 씀 (세컨더리는 자동 복제)
- 모두 _id 기준 ReplaceOne upsert → 여러 번 돌려도 중복 없음
- w=majority: 배치마다 세컨더리 1대 이상 복제될 때까지 기다림 (oplog 밀림 방지)

| 이름 | 컬렉션 | 원본 | _id |
| recipes     | OMM_mangae_recipes_raw  | data/raw/recipes.jsonl         | recipe_id |
| reviews     | OMM_mangae_reviews_raw  | data/raw/reviews.csv           | review_id |
| nutrition   | OMM_nutrition_foods_raw | data/raw/nutrition_foods.jsonl | FOOD_CD |
| kamis       | OMM_kamis_prices_raw    | data/raw/kamis_cache/*.json    | 캐시파일이름#행번호 |
| chamgagyeok | OMM_chamgagyeok_raw     | data/raw/chamgagyeok_raw/*.csv | 조사일|판매업소|상품명 |
| youtube     | OMM_youtube_videos      | data/youtube/trend_videos.csv  | run_date|query|period|video_id |

KAMIS 는 kamis_raw.csv 대신 캐시 json 을 넣음: 응답에 매장 구분값이 없어 (ingredient, date, cls, market) 이
겹치고, kamis_raw.csv 는 같은 코드를 쓰는 재료마다 행을 복제한 파일이라서. 캐시 1개 = 품목 × 월 API 응답이고,
같은 캐시를 다시 넣으면 행 번호가 같은 문서를 덮어쓰고 줄어든 행은 지움 (이번 달 캐시는 매일 새로 받으므로).

OMM_ingredient_dictionary 는 PG 에서 ingredient_id 가 정해진 뒤 넣으므로 여기서 다루지 않음.
"""
import argparse
import configparser
import csv
import datetime
import getpass
import glob
import json
import math
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import paths as P  # noqa: E402

import pandas as pd  # noqa: E402

NOW = datetime.datetime.now(datetime.timezone.utc)


def clean(v):
    """pandas NaN → None"""
    if isinstance(v, float) and math.isnan(v):
        return None
    return v


def to_int(v):
    v = clean(v)
    if v is None or v == '':
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


# ───────────── 문서 1개 만들기 (카프카 싱크 load/kafka_to_mongo.py 와 같이 씀 → 두 길로 넣어도 같은 문서) ─────────────
def doc_recipe(d):
    return {'_id': d['recipe_id'], **d, 'loaded_at': NOW}


def doc_review(r):
    rid = to_int(r.get('review_id'))
    if rid is None:
        return None
    return {'_id': rid, 'review_id': rid, 'recipe_id': to_int(r.get('recipe_id')),
            'written_at': clean(r.get('written_at')), 'stars': to_int(r.get('stars')), 'text': clean(r.get('text')),
            'loaded_at': NOW}


def doc_youtube(r):
    foods = clean(r.get('foods'))
    if isinstance(foods, list):
        foods = '|'.join(foods)
    return {'_id': f"{r['run_date']}|{r['query']}|{r['period']}|{r['video_id']}",
            'run_date': r['run_date'], 'query': r['query'], 'period': r['period'], 'video_id': r['video_id'],
            'title': clean(r.get('title')), 'channel': clean(r.get('channel')), 'published_at': clean(r.get('published_at')),
            'views': to_int(r.get('views')), 'likes': to_int(r.get('likes')), 'comments': to_int(r.get('comments')),
            'title_menu': clean(r.get('title_menu')), 'foods': foods.split('|') if foods else [],
            'loaded_at': NOW}


# ───────────── 컬렉션별 문서 만들기 ─────────────
def docs_recipes():
    with open(P.RECIPES_JSONL, encoding='utf-8') as f:
        for line in f:
            if line.strip():
                try:
                    d = json.loads(line)
                except ValueError:                       # 수집 중 끊긴 마지막 줄
                    continue
                yield doc_recipe(d)


def docs_reviews():
    df = pd.read_csv(P.REVIEWS_RAW, encoding='utf-8-sig', dtype=str)
    for r in df.to_dict('records'):
        d = doc_review(r)
        if d:
            yield d


def docs_nutrition():
    with open(P.raw('nutrition_foods.jsonl'), encoding='utf-8') as f:
        for line in f:
            if line.strip():
                d = json.loads(line)
                yield {'_id': d['FOOD_CD'], **d, 'loaded_at': NOW}


def kamis_code_map():
    """(category, item, kind, rank) → 그 코드를 쓰는 재료 이름들. 캐시의 kind 'all' 은 품종 전체"""
    m = pd.read_csv(P.KAMIS_MAP, encoding='utf-8-sig', dtype=str).fillna('')
    out = {}
    for r in m.itertuples(index=False):
        out.setdefault((r.category_code, r.item_code, r.kind_code, r.rank_code), set()).add(r.ingredient)
        out.setdefault((r.category_code, r.item_code, 'all', r.rank_code), set()).add(r.ingredient)
    return out


KAMIS_STAMP = os.path.join(os.path.dirname(P.KAMIS_CACHE), '.kamis_loaded_at')   # 마지막으로 성공한 kamis 적재 시작 시각
KAMIS_PICK = None      # None = 캐시 전부, set = 이 캐시 이름(stem)만 — main 에서 pick_kamis 로 정함


def kamis_files():
    files = sorted(glob.glob(os.path.join(P.KAMIS_CACHE, '*.json')))
    if KAMIS_PICK is None:
        return files
    return [f for f in files if os.path.basename(f)[:-5] in KAMIS_PICK]


def pick_kamis(coll, full):
    """2026-11-25: 지난달 이전 캐시는 안 바뀜 → 매일 전부(수백만 건) 다시 쓰지 않고
    몽고에 없는 캐시 + 지난 적재 뒤 바뀐 캐시(이번 달 · 다시 받은 지난달)만 넣음.
    기준 시각 파일이 없으면 이번 달 캐시를 바뀐 것으로 봄"""
    if full:
        return None
    have = set(coll.distinct('src'))
    try:
        since = float(open(KAMIS_STAMP).read().strip())
    except (OSError, ValueError):
        since = None
    if since is not None and os.path.getmtime(P.KAMIS_MAP) > since:   # 2026-11-25: 사전이 바뀌면 문서의 ingredients 칸이 낡음
        print('  재료↔코드 사전(kamis_item_map)이 지난 적재 뒤 바뀜 → 전부 다시 넣음 (ingredients 칸 맞추기)')
        return None
    this_ym = datetime.date.today().strftime('%Y%m')
    new = changed = total = 0
    pick = set()
    for f in glob.glob(os.path.join(P.KAMIS_CACHE, '*.json')):
        total += 1
        stem = os.path.basename(f)[:-5]
        if stem not in have:
            new += 1; pick.add(stem)
        elif (os.path.getmtime(f) > since) if since is not None else stem.endswith('_' + this_ym):
            changed += 1; pick.add(stem)
    print(f'  캐시 {total:,}개 중 {len(pick):,}개만 넣음 (몽고에 없음 {new:,} · 바뀜 {changed:,})'
          + ('' if since is not None else ' — 기준 시각 파일 없음: 이번 달 캐시를 바뀐 것으로 봄'))
    return pick


def save_kamis_stamp(t):
    with open(KAMIS_STAMP, 'w') as f:
        f.write(f'{t}\n')


def docs_kamis():
    cmap = kamis_code_map()
    for path in kamis_files():
        stem = os.path.basename(path)[:-5]
        cat, item, kind, rank, ym = stem.split('_')
        ings = sorted(cmap.get((cat, item, kind, rank), ()))
        with open(path, encoding='utf-8') as f:
            rows = json.load(f)
        for i, x in enumerate(rows):
            yield {'_id': f'{stem}#{i:05d}', 'src': stem, 'row': i,
                   'category_code': cat, 'item_code': item, 'kind_code': kind, 'rank_code': rank,
                   'month': f'{ym[:4]}-{ym[4:]}', 'ingredients': ings,
                   'date': x.get('date'), 'cls': x.get('cls'), 'price': x.get('price'),
                   'market': x.get('market') or None, 'unit': x.get('unit'), 'loaded_at': NOW}


def kamis_row_counts():
    """캐시 파일별 행 수 (줄어든 행 지우기용)"""
    out = {}
    for path in kamis_files():
        with open(path, encoding='utf-8') as f:
            out[os.path.basename(path)[:-5]] = len(json.load(f))
    return out


CHAMGA_COLS = {'상품명': 'product', '조사일': 'survey_date', '판매가격': 'price', '판매업소': 'store',
               '제조사': 'maker', '세일여부': 'sale', '원플러스원': 'one_plus_one'}


def read_chamga(path):
    for enc in ('cp949', 'utf-8-sig'):
        try:
            return pd.read_csv(path, encoding=enc, dtype=str)
        except UnicodeDecodeError:
            continue
    raise ValueError(f'인코딩을 알 수 없음: {path}')


CHAMGA_SKIP = set()    # 2026-11-25: 이미 몽고에 들어간 CSV(src_file)는 건너뜀 — main 에서 채움


def docs_chamgagyeok():
    for path in sorted(glob.glob(os.path.join(P.CHAMGAGYEOK_RAW, '*'))):
        if not path.lower().endswith('.csv'):
            continue
        if os.path.basename(path) in CHAMGA_SKIP:
            continue
        df = read_chamga(path).rename(columns=CHAMGA_COLS)
        name = os.path.basename(path)
        for r in df.itertuples(index=False):
            yield {'_id': f'{r.survey_date}|{r.store}|{r.product}', 'product': r.product,
                   'survey_date': r.survey_date, 'price': to_int(r.price), 'store': r.store,
                   'maker': clean(r.maker), 'sale': clean(r.sale), 'one_plus_one': clean(r.one_plus_one),
                   'src_file': name, 'loaded_at': NOW}


def docs_youtube():
    df = pd.read_csv(os.path.join(P.YOUTUBE, 'trend_videos.csv'), encoding='utf-8-sig', dtype=str)
    for r in df.to_dict('records'):
        yield doc_youtube(r)


def docs_categories():
    """2026-11-25: 만개 분류(상황별 등)는 수집기가 recipe_categories.csv 에 따로 모음 → 레시피 1개 = 문서 1개.
    레시피 원본과 섞지 않음: 싱크가 ReplaceOne 이라 같은 레시피가 다시 오면 분류가 지워짐"""
    if not os.path.exists(P.CATEGORIES_RAW):
        return
    by = {}
    with open(P.CATEGORIES_RAW, encoding='utf-8-sig') as f:
        for r in csv.DictReader(f):
            rid, grp, name = to_int(r.get('recipe_id')), (r.get('group') or '').strip(), (r.get('name') or '').strip()
            if rid is None or not grp or grp == '전체' or not name:
                continue
            d = by.setdefault(rid, {})
            if name not in d.setdefault(grp, []):
                d[grp].append(name)
    for rid, groups in by.items():
        yield {'_id': rid, 'recipe_id': rid, **groups, 'loaded_at': NOW}


# (이름, 컬렉션, 문서 생성기, 보조 인덱스)
TARGETS = {
    'recipes': ('OMM_mangae_recipes_raw', docs_recipes, [['published_at']]),
    'reviews': ('OMM_mangae_reviews_raw', docs_reviews, [['recipe_id']]),
    'nutrition': ('OMM_nutrition_foods_raw', docs_nutrition, [['FOOD_NM_KR']]),
    'kamis': ('OMM_kamis_prices_raw', docs_kamis, [['src', 'row'], ['ingredients', 'date', 'cls']]),
    'chamgagyeok': ('OMM_chamgagyeok_raw', docs_chamgagyeok, [['product', 'survey_date'], ['src_file']]),
    'youtube': ('OMM_youtube_videos', docs_youtube, [['video_id'], ['run_date']]),
    'categories': ('OMM_recipe_categories_raw', docs_categories, [['상황별']]),
}


# ───────────── 접속 · 쓰기 ─────────────
def connect():
    from pymongo import MongoClient

    cfg = configparser.ConfigParser()
    cfg.read(P.CONFIG, encoding='utf-8')
    if not cfg.has_section('mongo'):  # noqa
        sys.exit('config.ini 에 [mongo] 섹션이 없어요. 이 파일 맨 위 설명을 보고 추가해 주세요.')
    c = cfg['mongo']
    pw = c.get('password', '').strip() or getpass.getpass(f"{c.get('user')} 비밀번호: ")
    client = MongoClient(
        [h.strip() for h in c.get('hosts').split(',')],
        replicaSet=c.get('replica_set', 'omm-rs'),
        username=c.get('user'), password=pw, authSource=c.get('auth_source', 'OMM'),
        w='majority', retryWrites=True, serverSelectionTimeoutMS=15000,
    )
    client.admin.command('ping')
    print(f"접속: 프라이머리 {client.primary[0]}:{client.primary[1]} · 세컨더리 "
          f"{', '.join(f'{h}:{p}' for h, p in client.secondaries) or '없음'}")
    return client[c.get('db', 'OMM')]


def write(coll, docs, batch, pause=0.0):
    from pymongo import ReplaceOne
    from pymongo.errors import BulkWriteError

    n = ins = upd = 0
    t0 = time.time()
    ops = []

    def flush():
        nonlocal ins, upd
        try:
            res = coll.bulk_write(ops, ordered=False)
        except BulkWriteError as e:
            print(f'  배치 오류 {len(e.details.get("writeErrors", []))}건, 첫 오류: {e.details["writeErrors"][0]}')
            raise
        if pause:                                  # 2026-11-25: DB1(프라이머리) CPU 80% 넘지 않게 배치마다 쉼
            time.sleep(pause)
        ins += res.upserted_count
        upd += res.modified_count
        ops.clear()

    for d in docs:
        ops.append(ReplaceOne({'_id': d['_id']}, d, upsert=True))
        n += 1
        if len(ops) >= batch:
            flush()
            if n % (batch * 20) == 0:
                print(f'  {n:,}건 · {n / (time.time() - t0):,.0f}건/초')
    if ops:
        flush()
    print(f'  끝: {n:,}건 (새로 {ins:,} · 바뀜 {upd:,}) · {time.time() - t0:,.0f}초')
    return n


def prune_kamis(coll):
    """다시 받은 캐시가 짧아졌으면 그 뒤 행 문서를 지움"""
    removed = 0
    for stem, n in kamis_row_counts().items():
        removed += coll.delete_many({'src': stem, 'row': {'$gte': n}}).deleted_count
    if removed:
        print(f'  줄어든 캐시 행 {removed:,}건 지움')


def main():
    global KAMIS_PICK
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('targets', nargs='*', help=f'{" ".join(TARGETS)} 중 골라서 (비우면 전부)')
    ap.add_argument('--batch', type=int, default=5000)
    ap.add_argument('--sleep', type=float, default=0.7, help='배치(5000건)마다 쉬는 초 (DB1 CPU 부하 줄이기, 0 = 안 쉼)')
    ap.add_argument('--dry-run', action='store_true', help='접속 없이 문서만 만들어 봄')
    ap.add_argument('--chamga-full', action='store_true', help='참가격 CSV 전부 다시 넣기 (기본: 몽고에 없는 CSV만)')
    ap.add_argument('--kamis-full', action='store_true', help='kamis 캐시 전부 다시 넣기 (기본: 몽고에 없거나 지난 적재 뒤 바뀐 캐시만)')
    a = ap.parse_args()
    names = a.targets or list(TARGETS)
    bad = [n for n in names if n not in TARGETS]
    if bad:
        sys.exit(f'모르는 이름: {", ".join(bad)} (가능: {", ".join(TARGETS)})')

    if a.dry_run:
        for name in names:
            coll, gen, _ = TARGETS[name]
            first, n, ids = None, 0, set()
            for d in gen():
                first = first or d
                n += 1
                ids.add(d['_id'])
            dup = n - len(ids)
            print(f'[{coll}] {n:,}건 · _id 중복 {dup:,}' + ('  ← 확인 필요' if dup else ''))
            print('  ' + json.dumps(first, ensure_ascii=False, default=str)[:300])
        return

    db = connect()
    for name in names:
        coll_name, gen, indexes = TARGETS[name]
        coll = db[coll_name]
        print(f'[{coll_name}]')
        for keys in indexes:                       # 인덱스 먼저 (kamis 의 src · row 는 지우기에 필요)
            coll.create_index([(k, 1) for k in keys])
        if name == 'chamgagyeok' and not a.chamga_full:   # 2026-11-25: 새 CSV만 (손으로 추가할 때만 바뀜, 354만 건)
            CHAMGA_SKIP.update(coll.distinct('src_file'))
            print(f'  이미 넣은 CSV {len(CHAMGA_SKIP)}개는 건너뜀')
        if name == 'kamis':                        # 2026-11-25: 증분 적재
            t_start = time.time()
            KAMIS_PICK = pick_kamis(coll, a.kamis_full)
        n = write(coll, gen(), a.batch, a.sleep)
        if name == 'kamis':
            prune_kamis(coll)                      # 고른 캐시만 확인
            save_kamis_stamp(t_start)              # 성공했을 때만 기록
        print(f'  컬렉션 문서 수 {coll.estimated_document_count():,} (이번 원본 {n:,})')


if __name__ == '__main__':
    main()
