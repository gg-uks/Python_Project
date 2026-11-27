# OMM 사전 관리 (normalizer, admina)

정제는 매일 20:30 daily.sh → run_all.sh 가 돌림. 아래를 고친 뒤 기다리거나 바로 반영하려면:
  cd /opt/pipeline/normalizer && nice -n 10 ./daily.sh   # 정제 → PG → 몽고 → ES 까지 전부

## 무엇을 고칠 때 어디를 고치나
| 하고 싶은 것 | 고칠 곳 | 비고 |
|---|---|---|
| 재료 별칭 추가·수정 (원문 표기 → 재료) | PG omm_ingredient_aliases | 원본은 PG. 적재 때 덮어쓰지 않음 |
| 재료가 아닌 별칭 끄기 | PG omm_ingredient_aliases.is_active = false | 지우지 말고 끄기 |
| 별칭에 없는 원문 표기 → 표준명 | omm_dict/raw_std.csv | CRLF 파일. sed 말고 파이썬 csv로 고칠 것 |
| 표기 정리 규칙 (양·메모·괄호·보이지 않는 문자 제거) | clean_name.py | |
| 재료 단위 무게 (양파 1개 = 200g 등) | omm_dict/unit_grams.csv | 팀 사전 기본값(마리 300·봉지 200·통 500·포기 1000·개 200) 의심 |
| KAMIS 가격 단위 → g (고등어 1손 = 700g 등) | omm_dict/kamis_unit_g.csv | 같은 품목끼리 같은 값인지 확인 |
| 재료 ↔ KAMIS 품목 연결 | omm_dict/kamis_item_map.csv | |
| 새 메뉴 추가 | omm_dict/menu_seed.csv | 다음 정제 때 PG omm_menus 로 들어감 |
| 메뉴 키워드 추가 | PG omm_menus.match_keywords | 원본은 PG |
| 메뉴 분류(dish_type) 직접 지정 | load_team.py 의 DISH_FIX | |
| 양념으로 볼 재료 (재료비에서 뺌) | load_team.py 양념 목록, omm_dict/seasoning.csv | |
| 재료비 계산 규칙 (밥 = 쌀 × 0.43, 인분 보정, 1인분 1.5kg 상한) | mart_build_v4.sql ②, mongo_extract.py | |
| 메뉴 대표 레시피 기준 (조회수 → 후기 → 평점 → 최신) | mart_build_v4.sql ③ | |

## 자주 쓰는 SQL
-- 별칭 추가 (이미 있으면 다른 재료로 옮김)
INSERT INTO omm_ingredient_aliases (alias, ingredient_id, source)
VALUES ('생굴', (SELECT ingredient_id FROM omm_ingredients WHERE name = '굴'), 'SRC_MANUAL')
ON CONFLICT (alias) DO UPDATE SET ingredient_id = EXCLUDED.ingredient_id, is_active = true, updated_at = now();

-- 별칭 끄기
UPDATE omm_ingredient_aliases SET is_active = false, updated_at = now() WHERE alias = '고기';

-- 메뉴 키워드 추가
UPDATE omm_menus SET match_keywords = array_append(coalesce(match_keywords, '{}'), '묵사발') WHERE name = '도토리묵무침';

## 점검 (재료비가 이상할 때)
-- 3만원 초과 레시피 / 재료 줄별 재료비는 backups/20261124/tmp/over30k*.txt 참고 쿼리 사용
-- 개수 단위 중 재료비 영향 큰 조합: backups/20261124/tmp/unit_suspect.txt

## 동기화
PG → 몽고(OMM_ingredient_dictionary · OMM_menus): sync_mongo_dict.py (daily.sh 가 매일 실행)
몽고 → ES: es 서버 Monstache 실시간 + es_reload.py 가 매일 한 번 더 (재료·메뉴·레시피·후기)
수정 이력: backups/20261124/ (bak · scripts · tmp)

## 사전은 한 곳(normalizer/omm_dict)만 고칠 것
collector/dict/menu_seed.csv · kamis_item_map.csv 는 omm_dict 파일을 가리키는 링크(2026-11-25).
→ 유튜브 메뉴 찾기 · 영양 수집 · KAMIS 수집도 omm_dict 를 같이 씀. collector 쪽을 따로 고치지 말 것.
collector 에서 안 쓰는 정제 스크립트(clean/)와 사전은 collector/_unused/20261125/ 에 있음.

## 주기 점검: 지저분한 재료 합치기 (일주일에 한 번 정도)
python merge_junk.py            # 시험: 합칠 목록 확인 (잘못 합쳐지는 진짜 재료는 KEEP에 추가)
python merge_junk.py --apply    # 별칭 추가 · raw_std 교체 (기록: logs/merge_junk_날짜.csv)
nice -n 10 ./daily.sh           # 정제 다시 → 레시피 재료 줄이 새 재료로 연결
python merge_junk.py --cleanup  # 안 쓰게 된 재료 행 삭제
python sync_mongo_dict.py --apply   # 몽고·ES에서도 지움 (안 하면 다음 날 20:30에 반영)

## 안 쓰는 파일 (2026-11-25)
자체 수집 모드(OMM_SOURCE=own)·팀 데이터 모드용 스크립트는 _unused/20261125/ 로 옮김 (수집은 collector가 함).
모드를 바꾸려면 거기서 되돌릴 것. omm_schema_v4.sql(적재)·queries_v4.sql(백엔드 API가 읽음)은 옮기면 안 됨.
