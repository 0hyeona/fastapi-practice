-- Add only the per-user OAuth connection table; preserve existing data.
CREATE TABLE IF NOT EXISTS user_notion_accounts (
    user_id BIGINT UNSIGNED NOT NULL,
    workspace_id VARCHAR(36) NOT NULL,
    workspace_name VARCHAR(255) NULL,
    credentials TEXT NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (user_id),
    CONSTRAINT fk_notion_account_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
);
