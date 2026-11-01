-- TiDB: select the application database before running this migration.
-- Existing rows are preserved; their updated_at starts at migration time.
ALTER TABLE project_activities
    ADD COLUMN IF NOT EXISTS updated_at DATETIME NOT NULL
    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

SHOW COLUMNS FROM project_activities LIKE 'updated_at';
SELECT id, project_id, created_at, updated_at
FROM project_activities WHERE id = 1;
