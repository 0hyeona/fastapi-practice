-- Select your existing application database before running this statement.
-- Additive migration: no existing table or row is modified.
CREATE TABLE IF NOT EXISTS project_sync_runs (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    project_id BIGINT UNSIGNED NOT NULL,
    source VARCHAR(20) NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at DATETIME NOT NULL,
    finished_at DATETIME NULL,
    fetched INT NOT NULL DEFAULT 0,
    created INT NOT NULL DEFAULT 0,
    existing INT NOT NULL DEFAULT 0,
    error_code INT NULL,
    error_message VARCHAR(500) NULL,
    PRIMARY KEY (id),
    INDEX ix_sync_runs_project_source_started (project_id, source, started_at),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);
