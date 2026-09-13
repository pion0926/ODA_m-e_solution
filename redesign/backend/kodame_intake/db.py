from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

import psycopg
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from .security import hash_password, normalize_email
from .translations import translation_seed
from .settings import (
    ADMIN_DATABASE_URL,
    BOOTSTRAP_ADMIN_NAME,
    BOOTSTRAP_ADMIN_PASSWORD,
    BOOTSTRAP_PROJECT_NAME,
    SEED_DEMO_ACCOUNTS,
    DATABASE_URL,
)


pool = ConnectionPool(DATABASE_URL, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, open=False)

_project_id: ContextVar[str] = ContextVar("kodame_project_id", default="")
_account_id: ContextVar[str] = ContextVar("kodame_account_id", default="")
_system_access: ContextVar[bool] = ContextVar("kodame_system_access", default=False)


AUTH_SCHEMA = r"""
CREATE TABLE IF NOT EXISTS accounts (
  id uuid PRIMARY KEY,
  email text NOT NULL,
  password_hash text NOT NULL,
  display_name text NOT NULL,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_admin boolean NOT NULL DEFAULT false;
ALTER TABLE accounts ADD COLUMN IF NOT EXISTS menu_permissions jsonb NOT NULL DEFAULT '{}'::jsonb;
CREATE UNIQUE INDEX IF NOT EXISTS accounts_email_unique_idx ON accounts(lower(email));

CREATE TABLE IF NOT EXISTS projects (
  id uuid PRIMARY KEY,
  owner_account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE RESTRICT,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  is_bootstrap boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS projects_owner_idx ON projects(owner_account_id, updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS projects_one_bootstrap_idx ON projects((1)) WHERE is_bootstrap;
ALTER TABLE projects ADD COLUMN IF NOT EXISTS default_locale text NOT NULL DEFAULT 'ko';
ALTER TABLE projects ADD COLUMN IF NOT EXISTS supported_locales text[] NOT NULL DEFAULT ARRAY['ko']::text[];

CREATE TABLE IF NOT EXISTS project_members (
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  role text NOT NULL DEFAULT 'viewer',
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(project_id, account_id)
);
ALTER TABLE project_members ADD COLUMN IF NOT EXISTS preferred_locale text;
CREATE INDEX IF NOT EXISTS project_members_account_idx ON project_members(account_id, created_at);

CREATE TABLE IF NOT EXISTS project_translations (
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  locale text NOT NULL,
  translations jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(project_id, locale)
);
CREATE INDEX IF NOT EXISTS project_translations_project_idx ON project_translations(project_id, locale);

CREATE TABLE IF NOT EXISTS project_content_translations (
  project_id uuid NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  locale text NOT NULL,
  scope text NOT NULL,
  source_digest char(64) NOT NULL,
  payload jsonb NOT NULL,
  model text NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(project_id, locale, scope, source_digest)
);
CREATE INDEX IF NOT EXISTS project_content_translations_lookup_idx
  ON project_content_translations(project_id, locale, scope, updated_at DESC);

CREATE TABLE IF NOT EXISTS auth_sessions (
  token_hash char(64) PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  last_seen_at timestamptz NOT NULL DEFAULT now(),
  user_agent text,
  ip_address text
);
CREATE INDEX IF NOT EXISTS auth_sessions_account_idx ON auth_sessions(account_id, expires_at DESC);
CREATE INDEX IF NOT EXISTS auth_sessions_expiry_idx ON auth_sessions(expires_at);
ALTER TABLE auth_sessions ADD COLUMN IF NOT EXISTS selected_project_id uuid REFERENCES projects(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS login_events (
  id bigserial PRIMARY KEY,
  account_id uuid NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  logged_in_at timestamptz NOT NULL DEFAULT now(),
  ip_address text,
  user_agent text
);
CREATE INDEX IF NOT EXISTS login_events_account_idx ON login_events(account_id, logged_in_at DESC);

CREATE TABLE IF NOT EXISTS token_usage_events (
  id bigserial PRIMARY KEY,
  account_id uuid REFERENCES accounts(id) ON DELETE SET NULL,
  project_id uuid REFERENCES projects(id) ON DELETE SET NULL,
  model text NOT NULL DEFAULT '',
  prompt_tokens bigint NOT NULL DEFAULT 0,
  completion_tokens bigint NOT NULL DEFAULT 0,
  total_tokens bigint NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS token_usage_account_idx ON token_usage_events(account_id, created_at DESC);

CREATE TABLE IF NOT EXISTS account_settings (
  account_id uuid PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE,
  llm_model text NOT NULL,
  locale text NOT NULL DEFAULT 'ko-KR',
  timezone text NOT NULL DEFAULT 'Asia/Seoul',
  preferences jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
"""


SCHEMA = r"""
CREATE TABLE IF NOT EXISTS intake_documents (
  id uuid PRIMARY KEY,
  original_name text NOT NULL,
  stored_path text NOT NULL,
  extracted_path text,
  media_type text,
  extension text NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
  sha256 char(64) NOT NULL,
  status text NOT NULL DEFAULT 'queued',
  stage text NOT NULL DEFAULT 'queued',
  progress smallint NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  queue_position bigint GENERATED ALWAYS AS IDENTITY,
  attempts integer NOT NULL DEFAULT 0,
  available_at timestamptz NOT NULL DEFAULT now(),
  lease_until timestamptz,
  worker_id text,
  extraction_method text,
  extracted_chars integer,
  summary text,
  analysis jsonb,
  error_code text,
  error_message text,
  uploaded_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS intake_documents_queue_idx ON intake_documents(status, available_at, queue_position);
CREATE INDEX IF NOT EXISTS intake_documents_uploaded_idx ON intake_documents(uploaded_at DESC);
ALTER TABLE intake_documents ADD COLUMN IF NOT EXISTS analysis_model text;
ALTER TABLE intake_documents ADD COLUMN IF NOT EXISTS uploaded_by_account_id uuid REFERENCES accounts(id) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS processing_events (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES intake_documents(id) ON DELETE CASCADE,
  stage text NOT NULL,
  status text NOT NULL,
  message text,
  details jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS slot_suggestions (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES intake_documents(id) ON DELETE CASCADE,
  section_id text NOT NULL,
  section_number integer NOT NULL,
  section_title text NOT NULL,
  dac_criterion text,
  category text,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  rationale text NOT NULL,
  evidence_quote text,
  taxonomy_version text NOT NULL,
  review_status text NOT NULL DEFAULT 'pending',
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(document_id, section_id)
);
CREATE INDEX IF NOT EXISTS slot_suggestions_review_idx ON slot_suggestions(review_status, created_at DESC);

CREATE TABLE IF NOT EXISTS document_slot_assignments (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES intake_documents(id) ON DELETE CASCADE,
  criterion text NOT NULL,
  criterion_name text NOT NULL,
  slot_id text NOT NULL,
  slot_title text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  rationale text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(document_id, criterion)
);
CREATE INDEX IF NOT EXISTS document_slot_assignments_slot_idx
  ON document_slot_assignments(criterion, slot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS pdm_models (
  id uuid PRIMARY KEY,
  source_document_id uuid REFERENCES intake_documents(id) ON DELETE SET NULL,
  source_file_name text NOT NULL,
  pdm_version text NOT NULL DEFAULT 'source-table-v1',
  model jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS pdm_models_created_idx ON pdm_models(created_at DESC);

CREATE TABLE IF NOT EXISTS pdm_document_assignments (
  id bigserial PRIMARY KEY,
  document_id uuid NOT NULL REFERENCES intake_documents(id) ON DELETE CASCADE,
  indicator_id text NOT NULL,
  tier text NOT NULL,
  requirement_title text NOT NULL,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  rationale text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(document_id, indicator_id)
);
CREATE INDEX IF NOT EXISTS pdm_document_assignments_indicator_idx
  ON pdm_document_assignments(indicator_id, created_at DESC);

CREATE TABLE IF NOT EXISTS evaluation_runs (
  id uuid PRIMARY KEY,
  status text NOT NULL DEFAULT 'running',
  model text NOT NULL,
  document_count integer NOT NULL,
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz
);
ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS input_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS project_overviews (
  id uuid PRIMARY KEY,
  run_id uuid REFERENCES evaluation_runs(id) ON DELETE SET NULL,
  model text NOT NULL,
  document_count integer NOT NULL,
  overview jsonb NOT NULL,
  source_document_ids jsonb NOT NULL,
  conflicts jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS project_overviews_created_idx ON project_overviews(created_at DESC);

CREATE TABLE IF NOT EXISTS report_sections (
  part_id text PRIMARY KEY,
  section_number integer NOT NULL,
  section_id text NOT NULL,
  title text NOT NULL,
  prompt text NOT NULL,
  required_inputs jsonb NOT NULL DEFAULT '[]'::jsonb,
  content text NOT NULL DEFAULT '',
  status text NOT NULL DEFAULT 'empty',
  source_document_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  generation_model text,
  error_message text,
  generated_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_sections_number_idx ON report_sections(section_number);
ALTER TABLE report_sections ADD COLUMN IF NOT EXISTS generation_metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE report_sections ADD COLUMN IF NOT EXISTS quality_score numeric(5,2);
ALTER TABLE report_sections ADD COLUMN IF NOT EXISTS quality_report jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS report_reference_sources (
  id uuid PRIMARY KEY,
  file_name text NOT NULL UNIQUE,
  project_title text NOT NULL,
  source_path text NOT NULL,
  page_count integer NOT NULL,
  content_sha256 char(64) NOT NULL,
  extraction_method text NOT NULL DEFAULT 'pypdf',
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  ingested_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_reference_examples (
  id bigserial PRIMARY KEY,
  source_id uuid NOT NULL REFERENCES report_reference_sources(id) ON DELETE CASCADE,
  part_id text NOT NULL,
  section_title text NOT NULL,
  page_start integer NOT NULL,
  page_end integer NOT NULL,
  content text NOT NULL,
  structure_notes text NOT NULL,
  quality_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
  relevance_score numeric(6,2) NOT NULL DEFAULT 0,
  content_sha256 char(64) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(source_id,part_id,content_sha256)
);
CREATE INDEX IF NOT EXISTS report_reference_examples_part_idx
  ON report_reference_examples(part_id,relevance_score DESC);

CREATE TABLE IF NOT EXISTS report_generation_runs (
  id uuid PRIMARY KEY,
  status text NOT NULL DEFAULT 'queued',
  total_sections integer NOT NULL DEFAULT 27,
  completed_sections integer NOT NULL DEFAULT 0,
  failed_sections integer NOT NULL DEFAULT 0,
  current_part_id text,
  message text NOT NULL DEFAULT '',
  error_message text,
  started_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report_exports (
  id uuid PRIMARY KEY,
  status text NOT NULL DEFAULT 'queued',
  progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  stage text NOT NULL DEFAULT 'queued',
  message text NOT NULL DEFAULT '',
  error_message text,
  output_path text,
  file_name text,
  validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS report_exports_created_idx ON report_exports(created_at DESC);

CREATE TABLE IF NOT EXISTS presentation_exports (
  id uuid PRIMARY KEY,
  status text NOT NULL DEFAULT 'queued',
  progress integer NOT NULL DEFAULT 0 CHECK (progress BETWEEN 0 AND 100),
  stage text NOT NULL DEFAULT 'queued',
  message text NOT NULL DEFAULT '',
  error_message text,
  output_path text,
  file_name text,
  model text NOT NULL,
  validation jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  completed_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS presentation_exports_created_idx ON presentation_exports(created_at DESC);
ALTER TABLE presentation_exports ADD COLUMN IF NOT EXISTS slide_count integer;
ALTER TABLE report_generation_runs ADD COLUMN IF NOT EXISTS model text;

CREATE TABLE IF NOT EXISTS criterion_evaluations (
  id bigserial PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES evaluation_runs(id) ON DELETE CASCADE,
  criterion_id text NOT NULL,
  criterion_name text NOT NULL,
  score numeric(3,1) NOT NULL CHECK (score BETWEEN 1 AND 4),
  summary text NOT NULL,
  score_reason text NOT NULL,
  question_assessments jsonb NOT NULL,
  evidence_document_ids jsonb NOT NULL,
  evidence_gaps jsonb NOT NULL,
  source_document_count integer NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(run_id,criterion_id)
);
CREATE INDEX IF NOT EXISTS criterion_evaluations_run_idx
  ON criterion_evaluations(run_id,criterion_id);
"""


TENANT_MIGRATION = r"""
ALTER TABLE intake_documents ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE processing_events ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE slot_suggestions ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE document_slot_assignments ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE pdm_models ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE pdm_document_assignments ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE project_overviews ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE report_sections ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE report_generation_runs ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE report_exports ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE presentation_exports ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE criterion_evaluations ADD COLUMN IF NOT EXISTS project_id uuid REFERENCES projects(id) ON DELETE CASCADE;

UPDATE intake_documents SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE processing_events e SET project_id=d.project_id FROM intake_documents d WHERE e.document_id=d.id AND e.project_id IS NULL;
UPDATE slot_suggestions s SET project_id=d.project_id FROM intake_documents d WHERE s.document_id=d.id AND s.project_id IS NULL;
UPDATE slot_suggestions SET review_status='approved',reviewed_at=COALESCE(reviewed_at,created_at,now()) WHERE review_status='pending';
UPDATE document_slot_assignments a SET project_id=d.project_id FROM intake_documents d WHERE a.document_id=d.id AND a.project_id IS NULL;
UPDATE pdm_models m SET project_id=COALESCE(d.project_id,current_setting('kodame.bootstrap_project_id')::uuid) FROM intake_documents d WHERE m.source_document_id=d.id AND m.project_id IS NULL;
UPDATE pdm_models SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE pdm_document_assignments a SET project_id=d.project_id FROM intake_documents d WHERE a.document_id=d.id AND a.project_id IS NULL;
UPDATE evaluation_runs SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE project_overviews o SET project_id=COALESCE(r.project_id,current_setting('kodame.bootstrap_project_id')::uuid) FROM evaluation_runs r WHERE o.run_id=r.id AND o.project_id IS NULL;
UPDATE project_overviews SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE report_sections SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE report_generation_runs SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE report_exports SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE presentation_exports SET project_id=current_setting('kodame.bootstrap_project_id')::uuid WHERE project_id IS NULL;
UPDATE criterion_evaluations c SET project_id=r.project_id FROM evaluation_runs r WHERE c.run_id=r.id AND c.project_id IS NULL;

ALTER TABLE intake_documents ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE processing_events ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE slot_suggestions ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE document_slot_assignments ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE pdm_models ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE pdm_document_assignments ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE evaluation_runs ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE project_overviews ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE report_sections ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE report_generation_runs ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE report_exports ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE presentation_exports ALTER COLUMN project_id SET NOT NULL;
ALTER TABLE criterion_evaluations ALTER COLUMN project_id SET NOT NULL;

ALTER TABLE intake_documents ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE processing_events ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE slot_suggestions ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE document_slot_assignments ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE pdm_models ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE pdm_document_assignments ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE evaluation_runs ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE project_overviews ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE report_sections ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE report_generation_runs ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE report_exports ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE presentation_exports ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;
ALTER TABLE criterion_evaluations ALTER COLUMN project_id SET DEFAULT NULLIF(current_setting('kodame.project_id', true),'')::uuid;

DROP INDEX IF EXISTS intake_documents_source_dedupe_idx;
CREATE UNIQUE INDEX intake_documents_source_dedupe_idx ON intake_documents(project_id, original_name, sha256);
DROP INDEX IF EXISTS evaluation_runs_one_active_idx;
CREATE UNIQUE INDEX evaluation_runs_one_active_idx ON evaluation_runs(project_id) WHERE status IN ('queued','running');
DROP INDEX IF EXISTS report_generation_runs_one_active_idx;
CREATE UNIQUE INDEX report_generation_runs_one_active_idx ON report_generation_runs(project_id) WHERE status IN ('queued','running');
DROP INDEX IF EXISTS report_exports_one_active_idx;
CREATE UNIQUE INDEX report_exports_one_active_idx ON report_exports(project_id) WHERE status IN ('queued','running');
DROP INDEX IF EXISTS presentation_exports_one_active_idx;
CREATE UNIQUE INDEX presentation_exports_one_active_idx ON presentation_exports(project_id) WHERE status IN ('queued','running');
ALTER TABLE report_sections DROP CONSTRAINT IF EXISTS report_sections_pkey;
ALTER TABLE report_sections ADD PRIMARY KEY(project_id, part_id);
CREATE INDEX IF NOT EXISTS intake_documents_project_idx ON intake_documents(project_id, uploaded_at DESC);
CREATE INDEX IF NOT EXISTS pdm_models_project_idx ON pdm_models(project_id, created_at DESC);
CREATE INDEX IF NOT EXISTS pdm_document_assignments_project_idx ON pdm_document_assignments(project_id, indicator_id);
CREATE INDEX IF NOT EXISTS evaluation_runs_project_idx ON evaluation_runs(project_id, started_at DESC);
CREATE INDEX IF NOT EXISTS report_sections_project_idx ON report_sections(project_id, section_number);
"""


TENANT_TABLES = (
    "project_translations",
    "project_content_translations",
    "intake_documents",
    "processing_events",
    "slot_suggestions",
    "document_slot_assignments",
    "pdm_models",
    "pdm_document_assignments",
    "evaluation_runs",
    "project_overviews",
    "report_sections",
    "report_generation_runs",
    "report_exports",
    "presentation_exports",
    "criterion_evaluations",
)


def _ensure_project_translations(conn) -> None:
    projects = conn.execute("SELECT id,supported_locales FROM projects").fetchall()
    for project in projects:
        for locale in project.get("supported_locales") or ["ko"]:
            conn.execute(
                """INSERT INTO project_translations(project_id,locale,translations)
                   VALUES (%s,%s,%s::jsonb) ON CONFLICT(project_id,locale) DO UPDATE
                   SET translations=EXCLUDED.translations || project_translations.translations,updated_at=now()""",
                (project["id"], locale, json.dumps(translation_seed(locale), ensure_ascii=False)),
            )


def _ensure_bootstrap(conn) -> tuple[uuid.UUID, uuid.UUID]:
    email = normalize_email("admin@kodame.local")
    account = conn.execute("SELECT id FROM accounts WHERE lower(email)=lower(%s)", (email,)).fetchone()
    if account:
        account_id = account["id"]
    else:
        account_id = uuid.uuid4()
        conn.execute(
            "INSERT INTO accounts(id,email,password_hash,display_name,is_admin) VALUES (%s,%s,%s,%s,true)",
            (account_id, email, hash_password(BOOTSTRAP_ADMIN_PASSWORD, validate=False), BOOTSTRAP_ADMIN_NAME.strip() or "KODAME 관리자"),
        )
    # Startup is a migration, never a credential reset or account reactivation.
    # Existing administrator choices must survive API/worker/evaluation startup.
    project = conn.execute("SELECT id FROM projects WHERE is_bootstrap=true").fetchone()
    if project:
        project_id = project["id"]
    else:
        project_id = uuid.uuid4()
        conn.execute(
            "INSERT INTO projects(id,owner_account_id,name,is_bootstrap) VALUES (%s,%s,%s,true)",
            (project_id, account_id, BOOTSTRAP_PROJECT_NAME),
        )
    conn.execute(
        """INSERT INTO project_members(project_id,account_id,role) VALUES (%s,%s,'owner')
           ON CONFLICT(project_id,account_id) DO UPDATE SET role='owner'""",
        (project_id, account_id),
    )
    default_menus = {
        "dashboard": True, "evidence_upload": True, "evidence_pdm": True,
        "evidence_dac": True, "evidence_coverage": True, "project_overview": True,
        "project_indicators": True, "project_gaps": True, "evaluation_overview": True,
        "evaluation_board": True, "evaluation_results": True, "evaluation_report": True,
    }
    for number in (range(1, 11) if SEED_DEMO_ACCOUNTS else ()):
        test_email = f"test{number}@kodame.local"
        test = conn.execute("SELECT id FROM accounts WHERE lower(email)=lower(%s)", (test_email,)).fetchone()
        if test:
            test_id = test["id"]
        else:
            test_id = uuid.uuid4()
            conn.execute(
                """INSERT INTO accounts(id,email,password_hash,display_name,menu_permissions)
                   VALUES (%s,%s,%s,%s,%s::jsonb)""",
                (test_id, test_email, hash_password(f"KODAME-Test{number:02d}!2026"), f"테스트 사용자 {number}", json.dumps(default_menus)),
            )
        conn.execute(
            """INSERT INTO project_members(project_id,account_id,role) VALUES (%s,%s,'viewer')
               ON CONFLICT(project_id,account_id) DO NOTHING""",
            (project_id, test_id),
        )
    return account_id, project_id


def _enable_rls(conn) -> None:
    predicate = "(current_setting('kodame.system_access', true)='on' OR project_id::text=current_setting('kodame.project_id', true))"
    for table in TENANT_TABLES:
        conn.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        conn.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        conn.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {table}")
        conn.execute(f"CREATE POLICY tenant_isolation ON {table} USING {predicate} WITH CHECK {predicate}")


def open_pool() -> None:
    with psycopg.connect(ADMIN_DATABASE_URL, row_factory=dict_row) as conn:
        conn.execute(AUTH_SCHEMA)
        _, bootstrap_project_id = _ensure_bootstrap(conn)
        _ensure_project_translations(conn)
        conn.execute(SCHEMA)
        conn.execute("SELECT set_config('kodame.bootstrap_project_id',%s,false)", (str(bootstrap_project_id),))
        conn.execute(TENANT_MIGRATION)
        _enable_rls(conn)
        conn.execute("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO kodame_app")
        conn.execute("GRANT USAGE,SELECT,UPDATE ON ALL SEQUENCES IN SCHEMA public TO kodame_app")
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= now()")
        conn.commit()
    if pool.closed:
        pool.open(wait=True)


@contextmanager
def tenant_context(project_id: uuid.UUID | str | None = None, *, account_id: uuid.UUID | str | None = None, system: bool = False):
    project_token = _project_id.set(str(project_id or ""))
    account_token = _account_id.set(str(account_id) if account_id is not None else _account_id.get())
    system_token = _system_access.set(system)
    try:
        yield
    finally:
        _system_access.reset(system_token)
        _account_id.reset(account_token)
        _project_id.reset(project_token)


def current_project_id() -> uuid.UUID | None:
    value = _project_id.get()
    return uuid.UUID(value) if value else None


def current_account_id() -> uuid.UUID | None:
    value = _account_id.get()
    return uuid.UUID(value) if value else None


@contextmanager
def connection():
    with pool.connection() as conn:
        conn.execute(
            "SELECT set_config('kodame.project_id',%s,false),set_config('kodame.system_access',%s,false)",
            (_project_id.get(), "on" if _system_access.get() else "off"),
        )
        yield conn
