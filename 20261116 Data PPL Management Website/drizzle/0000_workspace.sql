CREATE TABLE records (id TEXT PRIMARY KEY NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL, version INTEGER NOT NULL DEFAULT 1);
--> statement-breakpoint
CREATE INDEX records_kind_idx ON records(kind);
--> statement-breakpoint
CREATE TABLE members (email TEXT PRIMARY KEY NOT NULL, user_id TEXT UNIQUE, role_id TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1);
--> statement-breakpoint
CREATE TABLE audit (id TEXT PRIMARY KEY NOT NULL, actor TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL, at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS project_report_states(project_id TEXT NOT NULL, project_version INTEGER NOT NULL, effective_month TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(project_id,project_version));
