CREATE TABLE IF NOT EXISTS project_diagram_submissions (
  analysis_id CHAR(36) PRIMARY KEY,
  request_digest CHAR(64) NOT NULL,
  original_image MEDIUMBLOB NOT NULL,
  FOREIGN KEY (analysis_id) REFERENCES architecture_project_links(analysis_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
