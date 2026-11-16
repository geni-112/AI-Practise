CREATE TABLE IF NOT EXISTS architecture_translations (
  analysis_id CHAR(36) NOT NULL,
  language CHAR(2) NOT NULL,
  status VARCHAR(12) NOT NULL DEFAULT 'queued',
  result_json LONGTEXT CHECK (result_json IS NULL OR JSON_VALID(result_json)),
  progress_json LONGTEXT CHECK (progress_json IS NULL OR JSON_VALID(progress_json)),
  error_code VARCHAR(80),
  failures SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  run_id CHAR(36),
  lease_until DATETIME,
  available_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (analysis_id,language),
  INDEX translation_queue (status,available_at),
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_translation_errors (
  id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
  analysis_id CHAR(36) NOT NULL,
  language CHAR(2) NOT NULL,
  started_at DATETIME NOT NULL,
  failed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  model VARCHAR(200),
  error_code VARCHAR(80) NOT NULL,
  timeout_seconds INT UNSIGNED,
  http_status SMALLINT UNSIGNED,
  provider_request_id VARCHAR(128),
  INDEX translation_failure_history (analysis_id,failed_at),
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_language_drawings (
  analysis_id CHAR(36) NOT NULL,
  language CHAR(2) NOT NULL,
  diagram_xml MEDIUMTEXT NOT NULL,
  preview_png MEDIUMBLOB NOT NULL,
  version INT NOT NULL DEFAULT 1,
  updated_by VARCHAR(190) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (analysis_id,language),
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO architecture_language_drawings(analysis_id,language,diagram_xml,preview_png,version,updated_by,updated_at)
SELECT d.analysis_id,a.language,d.diagram_xml,d.preview_png,d.version,d.updated_by,d.updated_at
FROM architecture_drawings d JOIN architecture_analyses a ON a.id=d.analysis_id;

INSERT IGNORE INTO architecture_translations(analysis_id,language)
SELECT id,CASE WHEN language='en' THEN 'zh' ELSE 'en' END FROM architecture_analyses
WHERE status='succeeded' AND result_json IS NOT NULL;
