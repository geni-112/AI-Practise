CREATE TABLE IF NOT EXISTS architecture_failures (
  analysis_id CHAR(36) NOT NULL,
  failure_version INTEGER NOT NULL,
  started_at DATETIME,
  failed_at DATETIME NOT NULL,
  stage VARCHAR(24) NOT NULL,
  error_code VARCHAR(80) NOT NULL,
  model VARCHAR(200),
  timeout_seconds INTEGER UNSIGNED,
  model_elapsed_ms INTEGER UNSIGNED,
  ocr_labels SMALLINT UNSIGNED,
  ocr_connections SMALLINT UNSIGNED,
  http_status SMALLINT UNSIGNED,
  provider_request_id VARCHAR(128),
  PRIMARY KEY (analysis_id, failure_version),
  FOREIGN KEY (analysis_id) REFERENCES architecture_analyses(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT IGNORE INTO architecture_failures
  (analysis_id,failure_version,started_at,failed_at,stage,error_code,model,timeout_seconds,ocr_labels,ocr_connections)
SELECT a.id,a.version,a.started_at,a.updated_at,
  CASE WHEN LEFT(a.error_code,4)='OCR_' THEN 'ocr'
       WHEN a.error_code IN ('INVALID_MODEL_RESPONSE','MODEL_OUTPUT_TRUNCATED') THEN 'validation'
       WHEN LEFT(a.error_code,5)='MAAS_' THEN 'model'
       WHEN a.error_code='INVALID_IMAGE' THEN 'image'
       ELSE 'worker' END,
  a.error_code,a.model,CASE WHEN a.error_code='MAAS_TIMEOUT' THEN 150 ELSE NULL END,
  JSON_LENGTH(i.evidence_json,'$.labels'),JSON_LENGTH(i.evidence_json,'$.connections')
FROM architecture_analyses a LEFT JOIN architecture_inputs i ON i.analysis_id=a.id
WHERE a.status='failed' AND a.error_code IS NOT NULL;

UPDATE integration_settings SET payload=JSON_SET(payload,'$.analysisTimeoutMinutes',10),version=version+1
WHERE id='maas' AND JSON_CONTAINS_PATH(payload,'one','$.analysisTimeoutMinutes')=0;
