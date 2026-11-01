-- Minimal tables for GitHub dashboard. Full app setup: sql/schema.sql
-- Existing tables are preserved; this does not migrate existing columns.
CREATE DATABASE IF NOT EXISTS moeum CHARACTER SET utf8mb4;
USE moeum;

CREATE TABLE IF NOT EXISTS users (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL UNIQUE,
    name VARCHAR(50) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    account_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS projects (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    owner_id BIGINT UNSIGNED NOT NULL,
    project_name VARCHAR(100) NOT NULL,
    description TEXT NULL,
    github_url VARCHAR(2048) NULL,
    figma_url VARCHAR(2048) NULL,
    notion_url VARCHAR(2048) NULL,
    project_status VARCHAR(20) NOT NULL DEFAULT 'active',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX fk_projects_owner (owner_id),
    CONSTRAINT fk_projects_owner FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;

SHOW COLUMNS FROM projects;
