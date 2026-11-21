-- Run in the same database as projects/users. Existing tables and activities stay.
USE moeum_db;
CREATE TABLE IF NOT EXISTS figma_plugin_connections (
    project_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    user_id BIGINT UNSIGNED NOT NULL,
    resource_id VARCHAR(128) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    pairing_hash VARCHAR(64) NULL UNIQUE,
    pairing_expires_at DATETIME NULL,
    token_hash VARCHAR(64) NULL UNIQUE,
    expires_at DATETIME NULL,
    last_sequence INT NOT NULL DEFAULT 0,
    last_received_at DATETIME NULL,
    CONSTRAINT fk_figma_plugin_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    CONSTRAINT fk_figma_plugin_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS project_figma_snapshots (
    project_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    resource_id VARCHAR(128) NOT NULL,
    revision INT NOT NULL,
    fingerprint VARCHAR(64) NOT NULL,
    content JSON NOT NULL,
    received_at DATETIME NOT NULL,
    CONSTRAINT fk_figma_snapshot_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
