#!/usr/bin/env bash
set -euo pipefail

DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-motis}"
DB_USER="${DB_USER:-motis}"
DB_PASSWORD="${DB_PASSWORD:-motis}"
ADMIN_DB="${ADMIN_DB:-postgres}"

psql "postgresql://${DB_HOST}:${DB_PORT}/${ADMIN_DB}" \
  -v ON_ERROR_STOP=1 \
  -v db_name="${DB_NAME}" \
  -v db_user="${DB_USER}" \
  -v db_password="${DB_PASSWORD}" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L', :'db_user', :'db_password')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = :'db_user')\gexec

SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name')\gexec
SQL

echo "Postgres role/database ready: ${DB_USER}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
