CREATE TABLE IF NOT EXISTS account_password_state (
  email VARCHAR(190) PRIMARY KEY,
  FOREIGN KEY (email) REFERENCES accounts(email),
  must_change_password INTEGER NOT NULL DEFAULT 1 CHECK (must_change_password IN (0,1))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

UPDATE invitations SET used_at=CURRENT_TIMESTAMP WHERE used_at IS NULL;
