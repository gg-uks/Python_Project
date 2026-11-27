"""사전 · 규칙을 고친 뒤 결과가 어떻게 바뀌었는지 확인 (menu_group.py · nutrition_fetch.py build 가 씀)

결과 파일을 덮어쓰기 전에 지난 결과와 비교해서 바뀐 줄만 *_changes.csv 로 남김
  표기 통일   달걀찜 → 계란찜 처럼 spelling_norm.csv 로 이름만 바뀐 것 (괜찮음)
  새로 묶임   전에는 메뉴 없음 → 이번에 메뉴 생김
  묶임 풀림   전에는 메뉴 있음 → 이번에 없음          ← 확인
  다른 메뉴   메뉴가 다른 메뉴로 바뀜                ← 확인
"""
import os
import pandas as pd


def classify(old, new, spell=lambda x: x):
    o, n = (None if pd.isna(old) else str(old)), (None if pd.isna(new) else str(new))
    if o == n:
        return None
    if o is None:
        return '새로 묶임'
    if n is None:
        return '묶임 풀림'
    if spell(o) == n:
        return '표기 통일'
    return '다른 메뉴'


def compare(path, new, key, col, out, show=(), spell=lambda x: x, label='레시피'):
    """path 의 지난 결과와 new(DataFrame) 를 key 로 맞춰 col 비교 → out 에 바뀐 줄 저장, 요약 출력. 처음이면 건너뜀"""
    if not os.path.exists(path):
        return None
    try:
        old = pd.read_csv(path, encoding='utf-8-sig')
    except Exception:
        return None
    if key not in old or col not in old:
        return None
    o = old[[key, col]].drop_duplicates(key).rename(columns={col: f'{col}_before'})
    m = new[[key, col, *[c for c in show if c in new]]].drop_duplicates(key).merge(o, on=key, how='outer')
    m['change'] = [classify(a, b, spell) for a, b in zip(m[f'{col}_before'], m[col])]
    ch = m[m['change'].notna()].rename(columns={col: f'{col}_after'})
    order = {'다른 메뉴': 0, '묶임 풀림': 1, '새로 묶임': 2, '표기 통일': 3}
    ch = ch.sort_values('change', key=lambda s: s.map(order))
    ch[[key, *[c for c in show if c in ch], f'{col}_before', f'{col}_after', 'change']].to_csv(out, index=False, encoding='utf-8-sig')
    if len(ch):
        cnt = ch['change'].value_counts()
        print(f"  지난 결과와 비교: {label} {len(ch):,}개 바뀜 (" + ' · '.join(f'{k} {cnt[k]:,}' for k in order if k in cnt)
              + f") → {os.path.basename(out)}" + ('  ← 다른 메뉴 · 묶임 풀림 먼저 확인' if cnt.get('다른 메뉴', 0) + cnt.get('묶임 풀림', 0) else ''))
    else:
        print(f'  지난 결과와 비교: {label} 바뀐 것 없음')
    return ch
