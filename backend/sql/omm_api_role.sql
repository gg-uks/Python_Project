-- API 전용 PostgreSQL 계정 (db1 에서 postgres 로 실행)
--   sudo -u postgres psql -d omm -v pw="'여기에_비밀번호'" -f omm_api_role.sql
--
-- 원칙: 분석 · 수집 테이블은 읽기만, 회원 · 관리 기능에 필요한 곳만 쓰기.
--       normalizer 가 쓰는 omm 계정과 분리해서, API 버그가 마트를 지우는 일을 막습니다.

DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'omm_api') THEN
    CREATE ROLE omm_api LOGIN;
  END IF;
END $$;
ALTER ROLE omm_api PASSWORD :pw;

GRANT CONNECT ON DATABASE omm TO omm_api;
GRANT USAGE ON SCHEMA public TO omm_api;

-- 1) 전체 읽기
GRANT SELECT ON ALL TABLES IN SCHEMA public TO omm_api;

-- 2) 회원 (가입 · 내 정보 수정 · 탈퇴 · 관리자 상태 변경)
GRANT INSERT ON omm_users TO omm_api;
GRANT UPDATE (nickname, household_size, status) ON omm_users TO omm_api;
GRANT USAGE ON SEQUENCE omm_users_user_id_seq TO omm_api;
GRANT INSERT, DELETE ON omm_user_preferences TO omm_api;

-- 3) 관리자 (공통코드 · 메뉴 키워드 · 재료 별칭)
GRANT UPDATE (code_nm, sort, use_yn) ON omm_common_codes TO omm_api;
GRANT UPDATE (match_keywords) ON omm_menus TO omm_api;
GRANT INSERT ON omm_ingredient_aliases TO omm_api;
-- 별칭 지움 · 다시 살림 (is_active 칸은 dict_source_pg.sql 로 추가된 뒤에만 아래 줄이 성공)
GRANT UPDATE (ingredient_id, source, is_active, updated_at) ON omm_ingredient_aliases TO omm_api;

-- 4) normalizer(omm 계정)가 나중에 새로 만드는 테이블도 자동으로 읽기 허용
--    테이블 주인이 omm 이 아니면 아래 FOR ROLE 을 실제 주인으로 바꾸세요:  \dt 로 Owner 확인
ALTER DEFAULT PRIVILEGES FOR ROLE omm IN SCHEMA public GRANT SELECT ON TABLES TO omm_api;
