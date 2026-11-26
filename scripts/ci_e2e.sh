#!/usr/bin/env bash
# End-to-end check on a small generated sample, no warehouse credentials needed:
#   generator -> Postgres / mock API / files -> dlt -> DuckDB -> dbt build -> MetricFlow reconciliation
# Used by .github/workflows/ci.yml. Locally it can run in a sandbox that never touches dev data:
#   POSTGRES_DB=najm_pos_ci GEN_OUTPUT_DIR=data/landing_ci GEN_STATE_PATH=data/generator_state/ci.pkl \
#   DUCKDB_PATH=data/warehouse/najm_ci.duckdb DLT_PIPELINES_DIR=data/dlt_pipelines_ci \
#   MOCK_API_PORT=8002 scripts/ci_e2e.sh
set -euo pipefail
cd "$(dirname "$0")/.."

export DUCKDB_PATH="${DUCKDB_PATH:-data/warehouse/najm_ci.duckdb}"
export DBT_DUCKDB_PATH="$PWD/$DUCKDB_PATH"
export DLT_PIPELINES_DIR="${DLT_PIPELINES_DIR:-data/dlt_pipelines_ci}"
export GEN_OUTPUT_DIR="${GEN_OUTPUT_DIR:-data/landing_ci}"
export ONLINE_DATA_DIR="$PWD/$GEN_OUTPUT_DIR/online"
port="${MOCK_API_PORT:-8000}"
export MOCK_API_BASE_URL="http://127.0.0.1:$port"
rm -rf "$DUCKDB_PATH" "$DLT_PIPELINES_DIR"

echo "::group::Generate a 5-week sample"
python -m najm_gen backfill --profile ci
echo "::endgroup::"

echo "::group::Load it with dlt"
python -m uvicorn mock_api.main:app --app-dir generator --port "$port" --log-level warning &
api=$!
trap 'kill $api 2>/dev/null || true' EXIT
for _ in $(seq 1 30); do curl -sf "$MOCK_API_BASE_URL/health" >/dev/null && break; sleep 1; done
python -m najm_ingest all
echo "::endgroup::"

echo "::group::dbt: freshness, build, test"
cd dbt
dbt deps --quiet
dbt source freshness
dbt build
cd ..
echo "::endgroup::"

echo "::group::Semantic layer: validate and reconcile"
(cd dbt && mf validate-configs)
python scripts/reconcile_metrics.py
echo "::endgroup::"
