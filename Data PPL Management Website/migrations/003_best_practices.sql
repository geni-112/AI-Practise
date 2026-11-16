CREATE TABLE IF NOT EXISTS integration_settings (
  id VARCHAR(40) PRIMARY KEY,
  payload LONGTEXT NOT NULL CHECK (JSON_VALID(payload)),
  version INTEGER NOT NULL DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_analyses (
  id CHAR(36) PRIMARY KEY,
  owner_email VARCHAR(190) NOT NULL,
  FOREIGN KEY (owner_email) REFERENCES members(email),
  request_key CHAR(36) NOT NULL,
  title VARCHAR(200) NOT NULL,
  business_type VARCHAR(40) NOT NULL,
  context_text TEXT NOT NULL,
  target_region VARCHAR(120) NOT NULL,
  language VARCHAR(5) NOT NULL,
  image_key VARCHAR(80) NOT NULL,
  image_name VARCHAR(200) NOT NULL,
  image_mime VARCHAR(40) NOT NULL,
  image_size INTEGER NOT NULL,
  status VARCHAR(20) NOT NULL,
  result_json LONGTEXT CHECK (result_json IS NULL OR JSON_VALID(result_json)),
  error_code VARCHAR(80),
  model VARCHAR(200),
  usage_json TEXT,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at DATETIME,
  lease_until DATETIME,
  archived_at DATETIME,
  version INTEGER NOT NULL DEFAULT 1,
  UNIQUE KEY architecture_request_idx(owner_email,request_key),
  INDEX architecture_queue_idx(status,created_at),
  INDEX architecture_owner_idx(owner_email,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_usage (
  id CHAR(36) PRIMARY KEY,
  owner_email VARCHAR(190) NOT NULL,
  analysis_id CHAR(36),
  purpose VARCHAR(20) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  INDEX architecture_usage_date_idx(created_at),
  INDEX architecture_usage_owner_idx(owner_email,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
