-- 사전 원본을 PostgreSQL 로 전환 (메뉴 키워드 · 재료 별칭 · 관리자 삭제 지원)
-- db1 에서 한 번만 실행:  sudo -u postgres psql -d omm -v ON_ERROR_STOP=1 -f dict_source_pg.sql
-- 여러 번 실행해도 안전 (IF NOT EXISTS)

BEGIN;

-- 1) 별칭 "지움" 표시. 행을 지우지 않고 is_active = false 로 남겨야
--    다음 적재 때 CSV(raw_std) · 팀 데이터에서 같은 표기가 다시 살아나지 않음
ALTER TABLE omm_ingredient_aliases ADD COLUMN IF NOT EXISTS is_active  BOOLEAN   NOT NULL DEFAULT true;
ALTER TABLE omm_ingredient_aliases ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT now();
COMMENT ON COLUMN omm_ingredient_aliases.is_active  IS '사용 여부 (false = 관리자가 지운 별칭. 적재 때 다시 추가되지 않음)';
COMMENT ON COLUMN omm_ingredient_aliases.updated_at IS '마지막 수정 시각';
COMMENT ON COLUMN omm_menus.match_keywords IS '제목에서 메뉴를 찾는 키워드 (사전 원본. 관리자 API 로 수정, 다음 적재 때 반영)';

-- 2) API 계정 쓰기 권한 (별칭 추가 · 지움 · 다시 살림)
GRANT INSERT ON omm_ingredient_aliases TO omm_api;
GRANT UPDATE (ingredient_id, source, is_active, updated_at) ON omm_ingredient_aliases TO omm_api;
GRANT UPDATE (match_keywords) ON omm_menus TO omm_api;

COMMIT;

-- 확인
SELECT is_active, source, count(*) FROM omm_ingredient_aliases GROUP BY 1, 2 ORDER BY 1 DESC, 2;
