-- TiDB: use the database configured in the backend. The existing DB is moeum_db.
-- Preserve existing credentials. NULL means OAuth approval is required again.
ALTER TABLE `moeum_db`.`figma_accounts`
    ADD COLUMN IF NOT EXISTS `figma_user_id` VARCHAR(128) NULL AFTER `user_id`;
