-- 회원가입 및 로그인에 필요한 DB와 테이블을 생성합니다.
-- 이미 존재하는 테이블의 구조나 데이터는 변경하지 않습니다.
CREATE DATABASE IF NOT EXISTS moeum
    CHARACTER SET utf8mb4;

USE moeum;

-- 회원가입 정보: 비밀번호는 원문 대신 해시로 저장합니다.
CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 로그인 세션: 토큰 해시와 UTC 기준 생성·만료 시간을 저장합니다.
CREATE TABLE IF NOT EXISTS auth_sessions (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL, -- users.id를 참조하는 숫자 회원 번호
    token_hash VARCHAR(64) NOT NULL UNIQUE,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,

    INDEX ix_auth_sessions_user_id (user_id),
    INDEX ix_auth_sessions_expires_at (expires_at),
    FOREIGN KEY (user_id) REFERENCES users(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

-- 이메일 인증번호와 일회성 비밀번호 재설정 권한 (회원당 최신 요청 1개)
CREATE TABLE IF NOT EXISTS password_resets (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    code_hash VARCHAR(255) NOT NULL,
    attempts INT NOT NULL DEFAULT 0,
    sent_at DATETIME NOT NULL,
    code_expires_at DATETIME NOT NULL,
    reset_token_hash VARCHAR(64) NULL UNIQUE,
    reset_expires_at DATETIME NULL,
    used_at DATETIME NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

SHOW TABLES;
