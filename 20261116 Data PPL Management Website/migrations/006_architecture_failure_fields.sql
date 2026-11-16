CREATE TABLE IF NOT EXISTS architecture_failure_fields (
  analysis_id CHAR(36) NOT NULL,
  failure_version INTEGER NOT NULL,
  field_path VARCHAR(160) NOT NULL,
  issue VARCHAR(32) NOT NULL,
  PRIMARY KEY (analysis_id, failure_version),
  FOREIGN KEY (analysis_id, failure_version) REFERENCES architecture_failures(analysis_id, failure_version) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
