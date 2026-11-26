-- Inspect first; use the idempotent Python inspector/applicator when possible:
-- python -m scripts.setup_figma_plugin_db
-- python -m scripts.setup_figma_plugin_db --apply
-- This file targets the existing production database; no rows are deleted.
USE moeum_db;

SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'figma_plugin_connections'
ORDER BY ORDINAL_POSITION;

-- Run each ALTER ONLY if its column is absent in the inspection above.
-- Do not rerun blindly; TiDB DDL can commit independently of a transaction.
ALTER TABLE figma_plugin_connections ADD COLUMN last_seen_at DATETIME NULL;
ALTER TABLE figma_plugin_connections ADD COLUMN collection_state VARCHAR(24) NULL;

-- Post-migration inspection: both columns must exist and be nullable.
SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = DATABASE()
  AND TABLE_NAME = 'figma_plugin_connections'
  AND COLUMN_NAME IN ('last_seen_at', 'collection_state');

-- Preferred rollback: redeploy the known-good application and KEEP these columns.
-- Old code ignores nullable additions. Existing users/projects/stories/activities,
-- pairing secrets, tokens and snapshots stay intact. Do not roll back to a source
-- commit containing unresolved conflict markers (52e6ab3).
-- Before applying, record table row counts and SHOW CREATE TABLE for the two plugin
-- tables in a secure operator record; do not expose hashes or snapshot contents.
-- If application rollback has finished and removal is explicitly needed later:
-- ALTER TABLE figma_plugin_connections DROP COLUMN collection_state;
-- ALTER TABLE figma_plugin_connections DROP COLUMN last_seen_at;
-- Removing these columns discards status timestamps; it is not required for rollback.
