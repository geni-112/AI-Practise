CREATE TABLE IF NOT EXISTS project_report_states (
  project_id VARCHAR(190) NOT NULL,
  project_version INTEGER NOT NULL,
  effective_month CHAR(7) NOT NULL,
  payload LONGTEXT NOT NULL CHECK (JSON_VALID(payload)),
  PRIMARY KEY (project_id,project_version),
  INDEX report_month (effective_month,project_id),
  FOREIGN KEY (project_id) REFERENCES records(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
