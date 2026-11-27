-- omm_youtube_trend_foods 추가 (이미 만든 DB용. 새로 만들 때는 omm_schema_v4.sql 에 들어 있음) — 2026-11-27
BEGIN;

-- YouTube 요즘 뜨는 음식 · 회차(수집일)별. 최근 30일 vs 그 전 150일, 기간마다 표본 안 비중끼리 비교 (collector youtube_trend.py 의 trend_foods.csv 와 같은 계산)
CREATE TABLE omm_youtube_trend_foods (
    run_date             DATE NOT NULL,
    food                 VARCHAR(50) NOT NULL,
    menu_id              INT,
    recent_videos        INT NOT NULL DEFAULT 0,
    before_videos        INT NOT NULL DEFAULT 0,
    recent_channels      INT NOT NULL DEFAULT 0,
    recent_total         INT NOT NULL,
    before_total         INT NOT NULL,
    growth               NUMERIC(8,2) NOT NULL,
    recent_views         BIGINT NOT NULL DEFAULT 0,
    example_title        VARCHAR(300),
    CONSTRAINT pk_omm_youtube_trend_foods PRIMARY KEY (run_date, food)
);
COMMENT ON TABLE omm_youtube_trend_foods IS 'YouTube 요즘 뜨는 음식 - 회차별. 최근 기간 vs 이전 기간, 기간마다 표본 안 비중끼리 비교';
COMMENT ON COLUMN omm_youtube_trend_foods.run_date IS '수집 회차 (수집한 날)';
COMMENT ON COLUMN omm_youtube_trend_foods.food IS '영상 제목 · 해시태그에서 찾은 음식 이름';
COMMENT ON COLUMN omm_youtube_trend_foods.menu_id IS '메뉴 사전에 있으면 메뉴 (없으면 NULL = 새 음식 후보)';
COMMENT ON COLUMN omm_youtube_trend_foods.recent_videos IS '최근 기간 영상 수';
COMMENT ON COLUMN omm_youtube_trend_foods.before_videos IS '이전 기간 영상 수';
COMMENT ON COLUMN omm_youtube_trend_foods.recent_channels IS '최근 영상을 올린 채널 수';
COMMENT ON COLUMN omm_youtube_trend_foods.recent_total IS '그 회차 최근 기간 표본 전체 영상 수';
COMMENT ON COLUMN omm_youtube_trend_foods.before_total IS '그 회차 이전 기간 표본 전체 영상 수';
COMMENT ON COLUMN omm_youtube_trend_foods.growth IS '증가 배수 = ((최근 + 0.5) / recent_total) / ((이전 + 0.5) / before_total)';
COMMENT ON COLUMN omm_youtube_trend_foods.recent_views IS '최근 영상 조회수 합 (수집 시점)';
COMMENT ON COLUMN omm_youtube_trend_foods.example_title IS '최근 영상 제목 예시';
CREATE INDEX ix_youtube_trend_foods_menu ON omm_youtube_trend_foods(menu_id, run_date);

ALTER TABLE omm_youtube_trend_foods ADD CONSTRAINT fk_omm_youtube_trend_foods_menu_id FOREIGN KEY (menu_id) REFERENCES omm_menus(menu_id) ON DELETE SET NULL;

COMMIT;
