-- 기존 projects 테이블에 URL 컬럼이 없는 환경에서 한 번만 실행하세요.
-- 이미 세 컬럼을 추가했다면 실행하지 마세요. 기존 프로젝트는 유지됩니다.
USE moeum;

ALTER TABLE projects
    ADD COLUMN github_url VARCHAR(2048) NULL,
    ADD COLUMN figma_url VARCHAR(2048) NULL,
    ADD COLUMN notion_url VARCHAR(2048) NULL;
