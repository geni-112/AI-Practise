CREATE TABLE IF NOT EXISTS content_translations (
 owner_id VARCHAR(190) NOT NULL,
 source_hash CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
 source_text MEDIUMTEXT NOT NULL,
 translated_text MEDIUMTEXT NULL,
 status VARCHAR(12) NOT NULL DEFAULT 'queued',
 failures INT NOT NULL DEFAULT 0,
 error_code VARCHAR(64) NULL,
 run_id CHAR(36) NULL,
 available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 lease_until DATETIME NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
 PRIMARY KEY(owner_id,source_hash),
 INDEX content_queue(status,available_at),
 INDEX content_expiry(owner_id,updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS content_translation_usage (
 id CHAR(36) PRIMARY KEY,
 owner_id VARCHAR(190) NOT NULL,
 created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
 INDEX content_usage(created_at,owner_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
