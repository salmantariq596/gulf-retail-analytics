"""Prove the Lightdash export returns the same numbers as MetricFlow.

For every metric that scripts/semantic_export.py put on an mtr_* table, this compiles the
generated Lightdash definition to plain SQL, runs it per month on the DuckDB dev warehouse,
and compares the result with `mf query` for the same metric and months.

    python scripts/reconcile_metrics.py   # run after `dbt build` on the dev target
"""

from __future__ import annotations

import csv
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parent))
from semantic_export import EXPORTS, ROOT, SemanticLayer, expand_sql, translate  # noqa: E402

DBT_DIR = ROOT / "dbt"
# same variable as ingestion (najm_ingest.config); CI points it at its own sample warehouse
WAREHOUSE = Path(os.getenv("DUCKDB_PATH", "data/warehouse/najm_dev.duckdb"))
WAREHOUSE = WAREHOUSE if WAREHOUSE.is_absolute() else ROOT / WAREHOUSE
MF = Path(sys.executable).with_name("mf.exe" if sys.platform == "win32" else "mf")
# Both sides aggregate the same decimals in the same warehouse, so only float noise from the
# CSV round trip is allowed. An absolute tolerance would hide errors in small ratios.
TOLERANCE = 1e-6


def warehouse_query(sql: str) -> list[tuple]:
    with duckdb.connect(str(WAREHOUSE), read_only=True) as con:
        return con.execute(sql).fetchall()


def table_ref(name: str) -> str:
    rows = warehouse_query(
        f"select table_schema from information_schema.tables where table_name = '{name}'"
    )
    if len(rows) != 1:
        raise SystemExit(f"expected one {name} table in the dev warehouse, found {len(rows)}")
    return f'"{rows[0][0]}"."{name}"'


def mf_monthly(metrics: list[str], start: str, end: str) -> dict[str, dict[str, float]]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "mf.csv"
        subprocess.run(
            [str(MF), "query", "--metrics", ",".join(metrics), "--group-by", "metric_time__month",
             "--start-time", start, "--end-time", end, "--csv", str(out)],
            cwd=DBT_DIR, check=True, capture_output=True,
        )
        with out.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    return {
        row["metric_time__month"][:10]: {m: float(row[m]) if row[m] not in ("", None) else math.nan for m in metrics}
        for row in rows
    }


def close(a: float, b: float) -> bool:
    if math.isnan(a) or math.isnan(b):
        return math.isnan(a) and math.isnan(b)
    return abs(a - b) <= TOLERANCE + 1e-9 * max(abs(a), abs(b))


def main() -> int:
    layer = SemanticLayer.load()
    failures = 0
    for export in EXPORTS:
        metrics, _ = translate(export, layer)
        visible = [name for name, entry in metrics.items() if not entry.get("hidden")]
        table = table_ref(export.name)
        t = export.time_column
        selects = ",\n  ".join(f"{expand_sql(metrics, m, 'x')} as {m}" for m in visible)
        sql = (
            f"select strftime(date_trunc('month', x.{t}), '%Y-%m-%d') as month,\n  {selects}\n"
            f"from {table} as x group by 1 order by 1"
        )
        ours = {row[0]: dict(zip(visible, row[1:])) for row in warehouse_query(sql)}
        first = min(ours)
        last_month = max(ours)
        end = warehouse_query(f"select strftime(last_day(date '{last_month}'), '%Y-%m-%d')")[0][0]
        theirs = mf_monthly(visible, first, end)

        checked = 0
        for month, values in ours.items():
            for metric in visible:
                a = float(values[metric]) if values[metric] is not None else math.nan
                b = theirs.get(month, {}).get(metric, math.nan)
                checked += 1
                if not close(a, b):
                    failures += 1
                    print(f"  MISMATCH {export.name}.{metric} {month}: export={a} metricflow={b}")
        missing = set(theirs) - set(ours)
        for month in sorted(missing):
            if any(not math.isnan(v) and v != 0 for v in theirs[month].values()):
                failures += 1
                print(f"  MISSING  {export.name} {month}: MetricFlow has values, the export has no rows")
        print(f"{export.name}: {len(visible)} metrics x {len(ours)} months = {checked} values checked")

    print("OK: export matches MetricFlow" if not failures else f"FAILED: {failures} mismatches")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
