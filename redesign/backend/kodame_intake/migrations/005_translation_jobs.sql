CREATE TABLE IF NOT EXISTS translation_jobs (
 id uuid PRIMARY KEY, project_id uuid NOT NULL DEFAULT NULLIF(current_setting('kodame.project_id',true),'')::uuid REFERENCES projects(id) ON DELETE CASCADE,
 locale text NOT NULL, source_locale text NOT NULL, digest text NOT NULL, views jsonb NOT NULL,
 status text NOT NULL DEFAULT 'queued', error_message text,
 created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
 UNIQUE(project_id,locale,digest)
);
