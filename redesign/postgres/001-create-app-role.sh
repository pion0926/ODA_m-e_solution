#!/bin/sh
set -eu

psql -v ON_ERROR_STOP=1 \
  --username "$POSTGRES_USER" \
  --dbname "$POSTGRES_DB" \
  --set=app_password="${APP_DATABASE_PASSWORD:-$POSTGRES_PASSWORD}" \
  --set=app_database="$POSTGRES_DB" \
  --set=bootstrap_user="$POSTGRES_USER" <<-'EOSQL'
SELECT format(
  'CREATE ROLE kodame_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_password'
)
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='kodame_app') \gexec

SELECT format(
  'ALTER ROLE kodame_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD %L',
  :'app_password'
) \gexec

SELECT format('GRANT CONNECT ON DATABASE %I TO kodame_app', :'app_database') \gexec
GRANT USAGE ON SCHEMA public TO kodame_app;
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO kodame_app',
  :'bootstrap_user'
) \gexec
SELECT format(
  'ALTER DEFAULT PRIVILEGES FOR ROLE %I IN SCHEMA public GRANT USAGE,SELECT,UPDATE ON SEQUENCES TO kodame_app',
  :'bootstrap_user'
) \gexec
EOSQL
