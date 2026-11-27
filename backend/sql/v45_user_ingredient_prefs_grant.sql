-- v4.5 회원 취향 재료(omm_user_ingredient_prefs)를 API 계정이 쓰게 권한 주기
-- db1 에서 한 번만 실행:  sudo -u postgres psql -d omm -v ON_ERROR_STOP=1 -f v45_user_ingredient_prefs_grant.sql
-- (테이블은 v45_user_ingredient_prefs.sql 로 이미 만들어져 있어야 함)

BEGIN;
GRANT SELECT, INSERT, DELETE ON omm_user_ingredient_prefs TO omm_api;
GRANT USAGE ON SEQUENCE omm_user_ingredient_prefs_pref_id_seq TO omm_api;
COMMIT;

-- 확인: Access privileges 칸에 omm_api=ard 가 보이면 됨 (a=INSERT, r=SELECT, d=DELETE)
\dp omm_user_ingredient_prefs
