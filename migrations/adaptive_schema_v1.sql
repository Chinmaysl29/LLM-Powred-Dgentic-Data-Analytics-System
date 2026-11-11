
CREATE TABLE adaptive_cases (
	id VARCHAR(36) NOT NULL, 
	actor_id UUID NOT NULL, 
	scenario_group VARCHAR(100) NOT NULL, 
	split VARCHAR(20) NOT NULL, 
	content JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	input_hashes JSON NOT NULL, 
	available BOOLEAN NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (id, workspace_id), 
	UNIQUE (workspace_id, content_hash), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_cases_scenario_group ON adaptive_cases (scenario_group);
CREATE INDEX ix_adaptive_cases_workspace_id ON adaptive_cases (workspace_id);

CREATE TABLE adaptive_skills (
	id VARCHAR(36) NOT NULL, 
	skill_id VARCHAR(80) NOT NULL, 
	version INTEGER NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	manifest JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	test_result JSON, 
	actor_id UUID NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	activated_at TIMESTAMP WITH TIME ZONE, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, skill_id, version), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_skills_workspace_id ON adaptive_skills (workspace_id);

CREATE TABLE adaptive_skill_revisions (
	id VARCHAR(36) NOT NULL, 
	skill_id VARCHAR(36) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	actor_id UUID NOT NULL, 
	evidence JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(skill_id, workspace_id) REFERENCES adaptive_skills (id, workspace_id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_skill_revisions_workspace_id ON adaptive_skill_revisions (workspace_id);

CREATE TABLE adaptive_work (
	id VARCHAR(36) NOT NULL, 
	owner_id UUID NOT NULL, 
	job_id UUID NOT NULL, 
	kind VARCHAR(25) NOT NULL, 
	idempotency_key VARCHAR(128) NOT NULL, 
	manifest JSON NOT NULL, 
	state VARCHAR(30) NOT NULL, 
	result JSON, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, kind, idempotency_key), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	UNIQUE (job_id), 
	FOREIGN KEY(job_id) REFERENCES background_jobs (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_work_workspace_id ON adaptive_work (workspace_id);

CREATE TABLE adaptive_models (
	id VARCHAR(36) NOT NULL, 
	work_id VARCHAR(36) NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	state VARCHAR(20) NOT NULL, 
	bundle JSON NOT NULL, 
	content_hash VARCHAR(64) NOT NULL, 
	invalid_reason VARCHAR(200), 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, work_id, kind), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(work_id) REFERENCES adaptive_work (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_models_workspace_id ON adaptive_models (workspace_id);

CREATE TABLE adaptive_contexts (
	run_id VARCHAR(36) NOT NULL, 
	content JSON NOT NULL, 
	input_hashes JSON NOT NULL, 
	skill_snapshot JSON NOT NULL, 
	model_id VARCHAR(36), 
	selector_mode VARCHAR(20) NOT NULL, 
	generation INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (run_id), 
	FOREIGN KEY(run_id, workspace_id) REFERENCES learning_runs (id, workspace_id), 
	FOREIGN KEY(model_id) REFERENCES adaptive_models (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_contexts_workspace_id ON adaptive_contexts (workspace_id);

CREATE TABLE adaptive_controls (
	workspace_id UUID NOT NULL, 
	mode VARCHAR(20) NOT NULL, 
	active_model_id VARCHAR(36), 
	previous_model_id VARCHAR(36), 
	generation INTEGER NOT NULL, 
	actor_id UUID NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (workspace_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id), 
	FOREIGN KEY(active_model_id) REFERENCES adaptive_models (id), 
	FOREIGN KEY(previous_model_id) REFERENCES adaptive_models (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id)
)

;

CREATE TABLE adaptive_decisions (
	id VARCHAR(36) NOT NULL, 
	owner_id UUID NOT NULL, 
	run_id VARCHAR(36), 
	case_id VARCHAR(36), 
	dedup_key VARCHAR(64) NOT NULL, 
	content JSON NOT NULL, 
	features JSON NOT NULL, 
	input_hash VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (workspace_id, dedup_key), 
	UNIQUE (id, workspace_id), 
	FOREIGN KEY(run_id, workspace_id) REFERENCES learning_runs (id, workspace_id), 
	FOREIGN KEY(case_id, workspace_id) REFERENCES adaptive_cases (id, workspace_id), 
	FOREIGN KEY(owner_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_decisions_workspace_id ON adaptive_decisions (workspace_id);

CREATE TABLE adaptive_outcomes (
	id VARCHAR(36) NOT NULL, 
	decision_id VARCHAR(36) NOT NULL, 
	content JSON NOT NULL, 
	label_status VARCHAR(20) NOT NULL, 
	revision INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(decision_id, workspace_id) REFERENCES adaptive_decisions (id, workspace_id), 
	UNIQUE (decision_id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_outcomes_workspace_id ON adaptive_outcomes (workspace_id);

CREATE TABLE adaptive_label_revisions (
	id VARCHAR(36) NOT NULL, 
	outcome_id VARCHAR(36) NOT NULL, 
	number INTEGER NOT NULL, 
	actor_id UUID NOT NULL, 
	content JSON NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	workspace_id UUID NOT NULL, 
	PRIMARY KEY (id), 
	UNIQUE (outcome_id, number), 
	FOREIGN KEY(outcome_id) REFERENCES adaptive_outcomes (id), 
	FOREIGN KEY(actor_id) REFERENCES users (id), 
	FOREIGN KEY(workspace_id) REFERENCES workspaces (id)
)

;
CREATE INDEX ix_adaptive_label_revisions_workspace_id ON adaptive_label_revisions (workspace_id);