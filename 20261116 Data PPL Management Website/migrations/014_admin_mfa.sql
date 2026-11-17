CREATE TABLE IF NOT EXISTS account_mfa (
 email VARCHAR(190) PRIMARY KEY,
 user_id VARCHAR(190) NOT NULL,
 secret_cipher TEXT,
 pending_cipher TEXT,
 pending_token_hash VARCHAR(190),
 pending_expires DATETIME,
 enabled_at DATETIME,
 version INTEGER NOT NULL DEFAULT 1,
 last_counter BIGINT NOT NULL DEFAULT -1,
 recovery_hashes TEXT,
 FOREIGN KEY (email) REFERENCES accounts(email) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS session_mfa (
 token_hash VARCHAR(190) PRIMARY KEY,
 mfa_version INTEGER NOT NULL,
 verified_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 FOREIGN KEY (token_hash) REFERENCES sessions(token_hash) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
