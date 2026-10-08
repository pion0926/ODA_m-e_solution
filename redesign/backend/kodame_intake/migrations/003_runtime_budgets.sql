CREATE TABLE IF NOT EXISTS ai_request_reservations (
 id uuid PRIMARY KEY, key_hash text NOT NULL, account_id uuid REFERENCES accounts(id) ON DELETE SET NULL,
 project_id uuid REFERENCES projects(id) ON DELETE CASCADE, task_id text NOT NULL,
 model text NOT NULL, tokens bigint NOT NULL, cost_usd numeric NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), lease_until timestamptz NOT NULL,
 finished_at timestamptz, usage_confirmed boolean NOT NULL DEFAULT false
);
CREATE INDEX IF NOT EXISTS ai_budget_key_day ON ai_request_reservations(key_hash,created_at);
CREATE INDEX IF NOT EXISTS ai_budget_task ON ai_request_reservations(task_id,created_at);
