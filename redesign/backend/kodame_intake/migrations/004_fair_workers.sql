ALTER TABLE workflow_tasks ADD COLUMN IF NOT EXISTS worker_slot integer NOT NULL DEFAULT 0;
CREATE INDEX IF NOT EXISTS workflow_tasks_fairness ON workflow_tasks(queue,project_id,started_at DESC);
