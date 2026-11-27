-- 기존 식사 기록 테이블 omm_user_meals: 주인을 omm 으로 + API 권한
-- db1 에서 postgres 로 한 번:  sudo -u postgres psql -d omm -v ON_ERROR_STOP=1 -f user_meals_owner.sql
--
-- 왜: 주인이 postgres 라서
--   ① normalizer --full 이 레시피를 지우기 전에 omm_user_meals.recipe_id 를 비우려다 권한 오류로 멈춤
--   ② omm 계정의 pg_dump 가 실패함
--   ③ API(omm_api) 가 식사 기록을 읽고 쓸 수 없음

BEGIN;
ALTER TABLE omm_user_meals OWNER TO omm;                 -- 일련번호(meal_id) 시퀀스도 같이 옮겨짐
GRANT SELECT, INSERT, DELETE ON omm_user_meals TO omm_api;
GRANT USAGE ON SEQUENCE omm_user_meals_meal_id_seq TO omm_api;
CREATE INDEX IF NOT EXISTS ix_omm_user_meals_user_date ON omm_user_meals (user_id, eaten_on);   -- 최근 N일 먹은 메뉴
COMMIT;

-- 확인: 주인 omm, omm_api 권한
SELECT tableowner FROM pg_tables WHERE tablename = 'omm_user_meals';
SELECT privilege_type FROM information_schema.role_table_grants WHERE table_name = 'omm_user_meals' AND grantee = 'omm_api';
-- 끼니 종류(meal_type) 로 쓸 수 있는 공통코드
SELECT c.code_id, c.code_nm FROM omm_common_codes c
WHERE c.group_code = (SELECT group_code FROM omm_common_codes WHERE code_id = (SELECT meal_type FROM omm_user_meals WHERE meal_type IS NOT NULL LIMIT 1))
   OR c.code_id LIKE 'MEAL%' ORDER BY c.sort;
