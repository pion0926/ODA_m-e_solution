ALTER TABLE intake_documents ADD COLUMN evaluation_excluded boolean NOT NULL DEFAULT false;
ALTER TABLE intake_documents ADD COLUMN evaluation_scope jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE intake_documents ADD COLUMN normalized_text_sha256 text;
ALTER TABLE intake_documents ADD CONSTRAINT foundation_always_evaluable
 CHECK (upload_role='evidence' OR NOT evaluation_excluded);
CREATE OR REPLACE VIEW active_intake_documents WITH (security_invoker=true) AS
 SELECT * FROM intake_documents WHERE superseded_at IS NULL;
CREATE VIEW evaluation_intake_documents WITH (security_invoker=true) AS
 SELECT * FROM active_intake_documents WHERE NOT evaluation_excluded;
CREATE INDEX intake_text_fingerprint ON intake_documents(project_id,normalized_text_sha256)
 WHERE superseded_at IS NULL AND NOT evaluation_excluded;
