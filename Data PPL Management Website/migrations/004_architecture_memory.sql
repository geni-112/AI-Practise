CREATE TABLE IF NOT EXISTS architecture_inputs (
  analysis_id CHAR(36) PRIMARY KEY,
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE,
  input_mode VARCHAR(12) NOT NULL,
  image_digest CHAR(64),
  reference_requested TINYINT NOT NULL DEFAULT 0,
  evidence_json LONGTEXT CHECK (evidence_json IS NULL OR JSON_VALID(evidence_json)),
  sources_json TEXT CHECK (sources_json IS NULL OR JSON_VALID(sources_json))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_cases (
  analysis_id CHAR(36) PRIMARY KEY,
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE,
  image_digest CHAR(64) NOT NULL UNIQUE,
  summary TEXT NOT NULL,
  reviewed_by VARCHAR(190) NOT NULL,
  reviewed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_case_terms (
  term VARCHAR(80) NOT NULL,
  analysis_id CHAR(36) NOT NULL,
  FOREIGN KEY (analysis_id) REFERENCES architecture_cases(analysis_id) ON DELETE CASCADE,
  PRIMARY KEY (term,analysis_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_case_mappings (
  analysis_id CHAR(36) NOT NULL,
  FOREIGN KEY (analysis_id) REFERENCES architecture_cases(analysis_id) ON DELETE CASCADE,
  product VARCHAR(100) NOT NULL,
  service_id VARCHAR(64) NOT NULL,
  PRIMARY KEY (analysis_id,product,service_id),
  INDEX case_mapping_lookup(product,service_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS architecture_drawings (
  analysis_id CHAR(36) PRIMARY KEY,
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE,
  diagram_xml MEDIUMTEXT NOT NULL,
  preview_png MEDIUMBLOB NOT NULL,
  version INT NOT NULL DEFAULT 1,
  updated_by VARCHAR(190) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
