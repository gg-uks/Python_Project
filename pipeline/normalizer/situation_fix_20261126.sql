-- 기존 상황 테이블(omm_situation_tags · keywords · targets) 보강 — API 담당자 승인 (2026-11-26)
BEGIN;

-- 1) 만개 분류뿐인 태그에 글자 규칙 추가 (만개 상황 분류는 레시피의 3%에만 있음)
INSERT INTO omm_situation_targets (target_id, sit_tag_id, rule_type, ref_id, ref_text)
SELECT (SELECT max(target_id) FROM omm_situation_targets) + row_number() OVER (), v.*
FROM (VALUES
  (2, 'RULE_TEXT', NULL::int, '야식|출출|떡볶이|라면|닭발|족발|곱창'),
  (3, 'RULE_TEXT', NULL::int, '안주|술안주|맥주|소주|골뱅이|쥐포|노가리'),
  (5, 'RULE_TEXT', NULL::int, '손님|집들이|파티|초대|잡채|갈비찜|수육|월남쌈'),
  (6, 'RULE_TEXT', NULL::int, '명절|추석|설날|차례|제사|잡채|동그랑땡|산적|송편|식혜|떡국'),
  (7, 'RULE_TEXT', NULL::int, '도시락|김밥|주먹밥|유부초밥|소풍'),
  (9, 'RULE_TEXT', NULL::int, '간단|초간단|전자레인지|원팬|10분|5분|후다닥')
) v(sit_tag_id, rule_type, ref_id, ref_text);

-- 2) '시원하게' 글자 규칙에서 '시원한' 빼기 (뜨거운 해장국까지 걸림)
UPDATE omm_situation_targets SET ref_text = '여름|더운 ?날|냉국|차갑게|냉면|콩국수|물회|빙수|냉모밀|화채'
WHERE sit_tag_id = 13 AND rule_type = 'RULE_TEXT';

-- 3) 새 태그 '속편한' (위에 부담 적은 · 소화 잘되는)
INSERT INTO omm_situation_tags (sit_tag_id, name, title, avoid_share, sort_order, use_yn)
VALUES (20, '속편한', '속 편하고 부드러운 메뉴', 0.50, 14, 'Y')
ON CONFLICT (sit_tag_id) DO NOTHING;
UPDATE omm_situation_keywords SET sit_tag_id = 20
WHERE sit_tag_id = 1 AND keyword IN ('속편한', '속이편', '속이불편', '속쓰', '더부룩');
INSERT INTO omm_situation_keywords (keyword, sit_tag_id, source, created_at)
SELECT k, 20, 'ADMIN', now()
FROM unnest(ARRAY['속이안좋', '속안좋', '위에부담', '위가안좋', '소화잘', '소화가잘', '부드러운', '아플때', '아파서', '죽먹']) AS u(k)
ON CONFLICT DO NOTHING;
INSERT INTO omm_situation_targets (target_id, sit_tag_id, rule_type, ref_id, ref_text)
SELECT (SELECT max(target_id) FROM omm_situation_targets) + row_number() OVER (), v.*
FROM (VALUES
  (20, 'RULE_TASTE_GROUP',     NULL::int, '담백함'),
  (20, 'RULE_DISH_TYPE',       NULL::int, '밥·죽'),
  (20, 'RULE_RECIPE_CATEGORY', 9,         NULL),
  (20, 'RULE_TEXT',            NULL::int, '죽|미음|계란찜|맑은|누룽지|부드러운|속편한|순한')
) v(sit_tag_id, rule_type, ref_id, ref_text);

-- target_id 가 SERIAL 이면 번호표를 맞춤
SELECT setval(pg_get_serial_sequence('omm_situation_targets', 'target_id'), (SELECT max(target_id) FROM omm_situation_targets));

COMMIT;