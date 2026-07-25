#!/usr/bin/env bash
# Quick smoke test after `docker compose up --build -d`. Confirms telemetry is
# flowing, the detector is scoring/alerting, and the agent is producing
# diagnoses. Safe to re-run.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "== compose service status =="
docker compose ps

run_sql() {
  docker compose exec -T postgres psql -U "${POSTGRES_USER:-sentinel}" -d "${POSTGRES_DB:-sentinel}" -c "$1"
}

echo
echo "== metrics rows written =="
run_sql "SELECT count(*) AS metrics_rows FROM metrics;"

echo
echo "== most recent alerts =="
run_sql "SELECT alert_id, host_id, severity, status, triggered_at FROM alerts ORDER BY triggered_at DESC LIMIT 5;"

echo
echo "== most recent agent diagnoses =="
run_sql "SELECT alert_id, llm_provider, confidence, left(root_cause, 80) AS root_cause FROM agent_runs ORDER BY created_at DESC LIMIT 5;"

echo
echo "Grafana:  http://localhost:3000  (admin/admin by default)"
