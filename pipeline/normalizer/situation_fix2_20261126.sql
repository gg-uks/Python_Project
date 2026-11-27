BEGIN;
-- 1) '시원한' 가르기
DELETE FROM omm_situation_keywords WHERE sit_tag_id = 13 AND keyword = '시원한';
INSERT INTO omm_situation_keywords (keyword, sit_tag_id, source, created_at)
SELECT k, 13, 'ADMIN', now()
FROM unnest(ARRAY['시원한거', '시원한게', '시원한걸', '시원한것', '시원한음식', '차가운', '차갑게']) AS u(k)
ON CONFLICT DO NOTHING;
INSERT INTO omm_situation_keywords (keyword, sit_tag_id, source, created_at)
SELECT k, 15, 'ADMIN', now()
FROM unnest(ARRAY['시원한국', '시원한탕', '시원한찌개', '국물이시원']) AS u(k)
ON CONFLICT DO NOTHING;
-- 2) 속편한: 메뉴 종류 '밥·죽' 규칙 삭제 (덮밥 · 김밥 · 카레까지 걸림)
DELETE FROM omm_situation_targets WHERE sit_tag_id = 20 AND rule_type = 'RULE_DISH_TYPE' AND ref_text = '밥·죽';
COMMIT;