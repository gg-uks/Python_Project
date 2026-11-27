"""모든 스크립트가 같이 쓰는 폴더 · 파일 위치 (어느 폴더에서 실행해도 같은 곳을 봄)

omm_10000recipe/
  config.ini                API 키 (공유 금지)
  collect/ clean/ price/ nutrition/   스크립트
  dict/                     사람이 고치는 사전 · 매핑표 (+ tables/ 단위 · 무게 · 밀도 · 별칭)
  data/raw/                 수집 원본 (손대지 않음)
  data/clean/               정제 결과
  data/price/               가격 결과 (KAMIS · 참가격 · 재료비)
  data/nutrition/           영양 결과 (식약처 음식 영양성분)
  data/youtube/             유튜브 결과
"""
import os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(ROOT, 'config.ini')

DICT = os.path.join(ROOT, 'dict')
TABLES = os.path.join(DICT, 'tables')
MENU_SEED = os.path.join(DICT, 'menu_seed.csv')
KAMIS_MAP = os.path.join(DICT, 'kamis_item_map.csv')
KAMIS_CODE_XLSX = os.path.join(DICT, 'kamis_code_table.xlsx')
CATEGORY_CODES = os.path.join(DICT, '10000recipe_categories.csv')
YOUTUBE_QUERIES = os.path.join(DICT, 'youtube_queries.csv')

DATA = os.path.join(ROOT, 'data')
RAW = os.path.join(DATA, 'raw')
CLEAN = os.path.join(DATA, 'clean')
PRICE = os.path.join(DATA, 'price')
NUTRITION = os.path.join(DATA, 'nutrition')
YOUTUBE = os.path.join(DATA, 'youtube')

RECIPES_JSONL = os.path.join(RAW, 'recipes.jsonl')
REVIEWS_RAW = os.path.join(RAW, 'reviews.csv')
CATEGORIES_RAW = os.path.join(RAW, 'recipe_categories.csv')
KAMIS_CACHE = os.path.join(RAW, 'kamis_cache')
CHAMGAGYEOK_RAW = os.path.join(RAW, 'chamgagyeok_raw')

for _d in (DICT, TABLES, RAW, CLEAN, PRICE, NUTRITION, YOUTUBE):
    os.makedirs(_d, exist_ok=True)

for _sub in ('clean', 'price', 'nutrition', 'collect'):          # 다른 폴더 스크립트끼리 import (ingredient_clean 등)
    _p = os.path.join(ROOT, _sub)
    if _p not in sys.path:
        sys.path.insert(0, _p)


def raw(name):
    return os.path.join(RAW, name)


def clean(name):
    return os.path.join(CLEAN, name)


def price(name):
    return os.path.join(PRICE, name)


def nutrition(name):
    return os.path.join(NUTRITION, name)
