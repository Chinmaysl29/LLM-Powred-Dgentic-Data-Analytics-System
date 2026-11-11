
CREATE TABLE learning_audit (
	id VARCHAR(36) NOT NULL, 
	actor_id UUID NOT NULL, 
	action VARCHAR(80) NOT NULL, 
	entity_id VARCHAR(36) NOT NULL, 
	summary JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_audit_workspace_id ON learning_audit (workspace_id);

CREATE TABLE learning_bundles (
	id VARCHAR(36) NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, content_hash), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_bundles_workspace_id ON learning_bundles (workspace_id);

CREATE TABLE learning_cases (
	id VARCHAR(36) NOT NULL, 
	actor_id UUID NOT NULL, 
	scenario_group VARCHAR(100) NOT NULL, 
	split VARCHAR(20) NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_cases_scenario_group ON learning_cases (scenario_group);
CREATE INDEX ix_learning_cases_workspace_id ON learning_cases (workspace_id);

CREATE TABLE learning_definitions (
	id VARCHAR(36) NOT NULL, 
	key VARCHAR(64) NOT NULL, 
	version INTEGER NOT NULL, 
	actor_id UUID NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	active BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, key, version), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_definitions_workspace_id ON learning_definitions (workspace_id);

CREATE TABLE learning_controls (
	workspace_id UUID NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	active_bundle_id VARCHAR(36), 
	previous_bundle_id VARCHAR(36), 
	rollout_percent INTEGER NOT NULL, 
	generation INTEGER NOT NULL, 
	actor_id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (workspace_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(active_bundle_id) REFERENCES learning_bundles (id), 
	FOREIGN KEY(previous_bundle_id) REFERENCES learning_bundles (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;

CREATE TABLE learning_evaluations (
	id VARCHAR(36) NOT NULL, 
	actor_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	bundle_id VARCHAR(36) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	manifest JSON NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	result JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, idempotency_key), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES background_jobs (id), 
	FOREIGN KEY(bundle_id) REFERENCES learning_bundles (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_evaluations_workspace_id ON learning_evaluations (workspace_id);

CREATE TABLE learning_runs (
	id VARCHAR(36) NOT NULL, 
	owner_id UUID NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	task JSON, 
	budget JSON NOT NULL, 
	schema_hash VARCHAR(64), 
	source_hash VARCHAR(64), 
	memory_cutoff TIMESTAMP WITH TIME ZONE NOT NULL, 
	lesson_snapshot JSON NOT NULL, 
	applied_lessons JSON NOT NULL, 
	bundle_id VARCHAR(36), 
	repairs INTEGER NOT NULL, 
	actions JSON NOT NULL, 
	repair_reservations JSON NOT NULL, 
	plan JSON, 
	outcome JSON, 
	error_code VARCHAR(80), 
	started_at TIMESTAMP WITH TIME ZONE, 
	finished_at TIMESTAMP WITH TIME ZONE, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(id) REFERENCES analysis_runs (id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_runs_workspace_id ON learning_runs (workspace_id);

CREATE TABLE learning_attempts (
	id VARCHAR(36) NOT NULL, 
	run_id VARCHAR(36) NOT NULL, 
	stage INTEGER NOT NULL, 
	number INTEGER NOT NULL, 
	evidence JSON NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (run_id, stage, number), 
	FOREIGN KEY(run_id, workspace_id) REFERENCES learning_runs (id, workspace_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_attempts_workspace_id ON learning_attempts (workspace_id);

CREATE TABLE learning_feedback (
	id VARCHAR(36) NOT NULL, 
	run_id VARCHAR(36) NOT NULL, 
	actor_id UUID NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	payload JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, actor_id, idempotency_key), 
	FOREIGN KEY(run_id, workspace_id) REFERENCES learning_runs (id, workspace_id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_feedback_workspace_id ON learning_feedback (workspace_id);

CREATE TABLE learning_lessons (
	id VARCHAR(36) NOT NULL, 
	source_run_id VARCHAR(36) NOT NULL, 
	source_dataset_id VARCHAR(36) NOT NULL, 
	dedup_key VARCHAR(64) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	revision INTEGER NOT NULL, 
	schema_hash VARCHAR(64) NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	verified_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	invalid_reason VARCHAR(200), 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id, workspace_id), 
	UNIQUE (workspace_id, dedup_key), 
	FOREIGN KEY(source_run_id, workspace_id) REFERENCES learning_runs (id, workspace_id), 
	FOREIGN KEY(source_dataset_id) REFERENCES datasets (dataset_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_lessons_schema_hash ON learning_lessons (schema_hash);
CREATE INDEX ix_learning_lessons_workspace_id ON learning_lessons (workspace_id);

CREATE TABLE learning_revisions (
	id VARCHAR(36) NOT NULL, 
	lesson_id VARCHAR(36) NOT NULL, 
	number INTEGER NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	actor_id UUID NOT NULL, 
	reason VARCHAR(500) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (lesson_id, number), 
	FOREIGN KEY(lesson_id, workspace_id) REFERENCES learning_lessons (id, workspace_id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_revisions_workspace_id ON learning_revisions (workspace_id);

CREATE TABLE learning_verifications (
	id VARCHAR(36) NOT NULL, 
	lesson_id VARCHAR(36) NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	verifier_version VARCHAR(80) NOT NULL, 
	evidence JSON NOT NULL, 
	passed BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (lesson_id, content_hash, verifier_version), 
	FOREIGN KEY(lesson_id, workspace_id) REFERENCES learning_lessons (id, workspace_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_learning_verifications_workspace_id ON learning_verifications (workspace_id);