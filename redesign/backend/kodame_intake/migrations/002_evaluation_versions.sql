CREATE TABLE IF NOT EXISTS evaluation_versions (
 id uuid PRIMARY KEY,
 project_id uuid NOT NULL DEFAULT NULLIF(current_setting('kodame.project_id',true),'')::uuid REFERENCES projects(id) ON DELETE CASCADE,
 revision text NOT NULL, payload jsonb NOT NULL,
 reviewer_id uuid REFERENCES accounts(id) ON DELETE SET NULL,
 reviewer_name text NOT NULL, review jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(project_id,revision)
);
CREATE OR REPLACE FUNCTION protect_evaluation_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.payload IS DISTINCT FROM OLD.payload OR NEW.revision IS DISTINCT FROM OLD.revision
    OR NEW.review IS DISTINCT FROM OLD.review OR NEW.reviewer_name IS DISTINCT FROM OLD.reviewer_name
    OR NEW.project_id IS DISTINCT FROM OLD.project_id OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
   RAISE EXCEPTION 'Approved evaluation versions are immutable';
 END IF;
 RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS evaluation_version_immutable ON evaluation_versions;
CREATE TRIGGER evaluation_version_immutable BEFORE UPDATE ON evaluation_versions
 FOR EACH ROW EXECUTE FUNCTION protect_evaluation_version();
CREATE TABLE IF NOT EXISTS foundation_changes (
 id bigserial PRIMARY KEY,
 project_id uuid NOT NULL DEFAULT NULLIF(current_setting('kodame.project_id',true),'')::uuid REFERENCES projects(id) ON DELETE CASCADE,
 document_id uuid REFERENCES intake_documents(id) ON DELETE CASCADE,
 previous_document_id uuid REFERENCES intake_documents(id) ON DELETE SET NULL,
 role text NOT NULL, reason text NOT NULL, approved_by uuid REFERENCES accounts(id) ON DELETE SET NULL,
 impact jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
