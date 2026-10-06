-- users에 name 컬럼이 없는 기존 DB에서 한 번 실행합니다.
-- 기존 회원은 아이디를 초기 표시 이름으로 사용합니다.
USE moeum;
ALTER TABLE users ADD COLUMN name VARCHAR(50) NOT NULL DEFAULT '' AFTER user_id;
UPDATE users SET name = user_id WHERE name = '';
