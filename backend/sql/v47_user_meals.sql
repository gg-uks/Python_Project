-- v4.7 회원 식사 기록 (omm_user_meals) + 공통코드 MEAL_TYPE + API 계정 권한
-- db1 에서 한 번만 실행:  sudo -u postgres psql -d omm -v ON_ERROR_STOP=1 -f v47_user_meals.sql
-- 기존 테이블은 건드리지 않음. 다시 실행해도 안전 (IF NOT EXISTS / ON CONFLICT)

BEGIN;

-- 1) 공통코드: 끼니
INSERT INTO omm_common_codes (code_id, group_code, group_nm, code, code_nm, group_sort, sort, description) VALUES
  ('MEAL_BREAKFAST', 'MEAL_TYPE', '끼니', 'BREAKFAST', '아침', 17, 1, NULL),
  ('MEAL_LUNCH', 'MEAL_TYPE', '끼니', 'LUNCH', '점심', 17, 2, NULL),
  ('MEAL_DINNER', 'MEAL_TYPE', '끼니', 'DINNER', '저녁', 17, 3, NULL),
  ('MEAL_SNACK', 'MEAL_TYPE', '끼니', 'SNACK', '간식', 17, 4, NULL)
ON CONFLICT (code_id) DO UPDATE SET code_nm = EXCLUDED.code_nm, group_nm = EXCLUDED.group_nm, sort = EXCLUDED.sort;

-- 2) 테이블
CREATE TABLE IF NOT EXISTS omm_user_meals (
    meal_id              SERIAL NOT NULL,
    user_id              INT NOT NULL,
    menu_id              INT,
    recipe_id            INT,
    eaten_on             DATE NOT NULL DEFAULT CURRENT_DATE,
    meal_type            VARCHAR(30),
    servings             NUMERIC(3,1) NOT NULL DEFAULT 1 CHECK (servings > 0 AND servings <= 20),
    memo                 VARCHAR(200),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT pk_omm_user_meals PRIMARY KEY (meal_id)
);
COMMENT ON TABLE omm_user_meals IS '회원 식사 기록 - 회원이 먹었다고 체크한 메뉴 · 레시피 (v4.7). 메뉴 · 레시피 중 하나는 API가 꼭 채움 (원본이 지워지면 NULL로 남고 기록은 유지). 마이페이지 먹은 기록 · 주간 영양/재료비 요약 · 최근 먹은 메뉴 추천 제외에 씀';
COMMENT ON COLUMN omm_user_meals.meal_id IS '번호';
COMMENT ON COLUMN omm_user_meals.user_id IS '회원';
COMMENT ON COLUMN omm_user_meals.menu_id IS '먹은 메뉴 (레시피만 고르면 레시피의 메뉴로 채움)';
COMMENT ON COLUMN omm_user_meals.recipe_id IS '보고 만든 레시피 (없으면 NULL)';
COMMENT ON COLUMN omm_user_meals.eaten_on IS '먹은 날';
COMMENT ON COLUMN omm_user_meals.meal_type IS '아침 / 점심 / 저녁 / 간식 · 공통코드(MEAL_TYPE)';
COMMENT ON COLUMN omm_user_meals.servings IS '먹은 양 (인분)';
COMMENT ON COLUMN omm_user_meals.memo IS '한 줄 메모';
COMMENT ON COLUMN omm_user_meals.created_at IS '기록 일시';
CREATE INDEX IF NOT EXISTS ix_omm_user_meals_user_day ON omm_user_meals(user_id, eaten_on DESC);

-- 3) 외래키 (이미 있으면 건너뜀)
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_omm_user_meals_user_id') THEN
    ALTER TABLE omm_user_meals ADD CONSTRAINT fk_omm_user_meals_user_id FOREIGN KEY (user_id) REFERENCES omm_users(user_id);
    ALTER TABLE omm_user_meals ADD CONSTRAINT fk_omm_user_meals_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE SET NULL;
    ALTER TABLE omm_user_meals ADD CONSTRAINT fk_omm_user_meals_recipe_id FOREIGN KEY (recipe_id) REFERENCES omm_recipes(recipe_id) ON DELETE SET NULL;
    ALTER TABLE omm_user_meals ADD CONSTRAINT fk_omm_user_meals_meal_type FOREIGN KEY (meal_type) REFERENCES omm_common_codes(code_id);
  END IF;
END $$;

-- 4) API 계정 권한 (읽기 · 추가 · 삭제)
GRANT SELECT, INSERT, DELETE ON omm_user_meals TO omm_api;
GRANT USAGE ON SEQUENCE omm_user_meals_meal_id_seq TO omm_api;

COMMIT;

-- 확인: omm_api=ard 가 보이면 됨
\dp omm_user_meals
SELECT code_id, code_nm FROM omm_common_codes WHERE group_code = 'MEAL_TYPE' ORDER BY sort;
