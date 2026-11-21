-- Existing figma_accounts tables are not changed. Inspect their columns first.
-- Each MOEUM user has one Figma account; projects.figma_url stores each file URL.
CREATE TABLE IF NOT EXISTS figma_accounts (
    user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    figma_user_id VARCHAR(128) NOT NULL,
    credentials TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    CONSTRAINT fk_figma_accounts_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
) ENGINE=InnoDB;
