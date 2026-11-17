CREATE TABLE IF NOT EXISTS architecture_project_links (
  analysis_id CHAR(36) PRIMARY KEY,
  project_id VARCHAR(190) NOT NULL,
  INDEX idx_practice_project (project_id),
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_case_publications (
  analysis_id CHAR(36) PRIMARY KEY,
  title VARCHAR(200) NOT NULL,
  FOREIGN KEY (analysis_id) REFERENCES architecture_cases(analysis_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
