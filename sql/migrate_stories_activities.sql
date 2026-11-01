-- Apply to the same database as projects. Existing rows are preserved.
CREATE TABLE IF NOT EXISTS stories (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT UNSIGNED NOT NULL,
    title VARCHAR(200) NOT NULL,
    content TEXT NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX ix_stories_project_created (project_id, created_at),
    CONSTRAINT fk_stories_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS project_activities (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    project_id BIGINT UNSIGNED NOT NULL,
    story_id BIGINT UNSIGNED NULL,
    external_id VARCHAR(255) NULL,
    branch_name VARCHAR(255) NULL,
    source VARCHAR(20) NOT NULL,
    activity_type VARCHAR(50) NOT NULL,
    title VARCHAR(200) NOT NULL,
    description TEXT NULL,
    source_url VARCHAR(2048) NULL,
    occurred_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_activities_story FOREIGN KEY (story_id) REFERENCES stories(id) ON DELETE SET NULL,
    INDEX idx_activities_unorganized (project_id, story_id, occurred_at),
    INDEX ix_project_activities_project_created (project_id, created_at),
    CONSTRAINT fk_project_activities_project FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- Existing TiDB tables missing project_activities.updated_at also need
-- migrate_project_activities_updated_at.sql (CREATE IF NOT EXISTS does not add columns).
