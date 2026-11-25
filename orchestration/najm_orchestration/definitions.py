"""Dagster definitions: one asset graph from the source systems to the governed metrics.

    source_systems_day                 the generator simulates the next business day
      -> pos/*, online/*, erp/*, ...   dlt loads each raw table (one asset per table)
      -> dbt seeds, snapshots, models  `dbt source freshness` gates `dbt build`
      -> metricflow_reconciliation     generated Lightdash metrics vs `mf query` (DuckDB dev)

Asset keys of the dlt tables equal the dbt source keys ([source, table]), so Dagster shows
one lineage graph from Postgres/API/files to the dashboards' metric tables.

    dagster dev                                # UI on http://localhost:3000 (pyproject: [tool.dagster])
    DBT_TARGET=prod NAJM_WAREHOUSE=snowflake   # run against Snowflake instead of DuckDB
"""

# No `from __future__ import annotations`: Dagster inspects the `context` annotation at
# definition time and cannot resolve it from a string.
import os
import re
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import dagster as dg
from dagster_dbt import (
    DagsterDbtTranslator,
    DagsterDbtTranslatorSettings,
    DbtCliResource,
    DbtProject,
    dbt_assets,
    get_asset_key_for_model,
)
from dagster_dlt import DagsterDltResource, DagsterDltTranslator, dlt_assets
from dagster_dlt.translator import DltResourceTranslatorData

from najm_ingest import files, online, pos
from najm_ingest.config import WAREHOUSE, pipeline

REPO_ROOT = Path(__file__).resolve().parents[2]
DBT_DIR = REPO_ROOT / "dbt"
DBT_TARGET = os.getenv("DBT_TARGET", "dev")
SOURCE_DAY = dg.AssetKey("source_systems_day")
# the generated metric tables that dashboards read; reconciled against MetricFlow
METRIC_TABLES = ["mtr_sales_daily", "mtr_merchandising_monthly", "mtr_online_orders_daily", "mtr_marketing_monthly"]


def _run(context: dg.AssetExecutionContext, args: list[str]) -> str:
    """Run a project command with this interpreter, stream its output to the Dagster log."""
    proc = subprocess.run([sys.executable, *args], cwd=REPO_ROOT, capture_output=True, text=True,
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    for line in (proc.stdout + proc.stderr).splitlines():
        if line.strip():
            context.log.info(line)
    if proc.returncode != 0:
        raise dg.Failure(f"`{' '.join(args)}` exited with {proc.returncode}")
    return proc.stdout


# ------------------------------------------------------------------------ sources
@dg.asset(
    key=SOURCE_DAY,
    group_name="sources",
    kinds={"python", "postgres"},
    description=(
        "Stands in for the source systems: the generator simulates the next business day and "
        "writes it to the POS database, the online store API and the ERP/catalog/marketing files."
    ),
)
def source_systems_day(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    out = _run(context, ["-m", "najm_gen", "run", "--days", "1"])
    match = re.search(r"Next day to simulate: (\S+)", out)
    return dg.MaterializeResult(metadata={"next_day": match.group(1) if match else "unknown"})


# ---------------------------------------------------------------------- ingestion
class NajmDltTranslator(DagsterDltTranslator):
    """Key each raw table like its dbt source ([source, table]) and hang it off the source day."""

    def get_asset_spec(self, data: DltResourceTranslatorData) -> dg.AssetSpec:
        spec = super().get_asset_spec(data)
        return spec.replace_attributes(
            key=dg.AssetKey([data.resource.source_name, data.resource.name]),
            deps=[SOURCE_DAY],
            group_name="ingestion",
        )


def _ingestion_assets(name: str, source, pipeline_name: str, dataset: str) -> dg.AssetsDefinition:
    @dlt_assets(
        dlt_source=source,
        dlt_pipeline=pipeline(pipeline_name, dataset),
        name=f"ingest_{name}",
        dagster_dlt_translator=NajmDltTranslator(),  # sets the group (ingestion)
    )
    def _assets(context: dg.AssetExecutionContext, dlt: DagsterDltResource):
        yield from dlt.run(context=context)

    return _assets


ingestion = [
    _ingestion_assets("pos", pos.pos_source(), "najm_pos", "raw_pos"),
    _ingestion_assets("online", online.online_source(), "najm_online", "raw_online"),
    _ingestion_assets("erp", files.erp_source(), "najm_erp", "raw_erp"),
    _ingestion_assets("catalog", files.catalog_source(), "najm_catalog", "raw_catalog"),
    _ingestion_assets("marketing", files.marketing_source(), "najm_marketing", "raw_marketing"),
]


# ---------------------------------------------------------------------------- dbt
dbt_project = DbtProject(project_dir=DBT_DIR, profiles_dir=DBT_DIR, target=DBT_TARGET)
dbt_project.prepare_if_dev()  # `dagster dev` re-parses the project; deployments ship a manifest


class NajmDbtTranslator(DagsterDbtTranslator):
    def get_asset_spec(self, manifest: Mapping[str, Any], unique_id: str, project) -> dg.AssetSpec:
        spec = super().get_asset_spec(manifest, unique_id, project)
        props = self.get_resource_props(manifest, unique_id)
        if props["resource_type"] == "source":
            # dlt writes orders__lines as a child table of the orders resource
            table = "orders" if props["name"] == "orders__lines" else props["name"]
            return spec.replace_attributes(key=dg.AssetKey([props["source_name"], table]))
        layer = props["fqn"][1] if len(props["fqn"]) > 2 else props["resource_type"]
        return spec.replace_attributes(group_name=f"dbt_{layer}")


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=NajmDbtTranslator(
        settings=DagsterDbtTranslatorSettings(enable_duplicate_source_asset_keys=True)),
)
def najm_dbt(context: dg.AssetExecutionContext, dbt: DbtCliResource):
    # Freshness gate: stale raw data stops the build instead of publishing stale numbers
    dbt.cli(["source", "freshness"], raise_on_error=True).wait()
    yield from dbt.cli(["build"], context=context).stream()


# ---------------------------------------------------------------------- governance
@dg.asset(
    group_name="governance",
    deps=[get_asset_key_for_model([najm_dbt], t) for t in METRIC_TABLES],
    kinds={"metricflow"},
    description=(
        "Proves the generated Lightdash metrics equal MetricFlow: every exported metric, per "
        "month, compared with `mf query` (scripts/reconcile_metrics.py). DuckDB dev target only."
    ),
)
def metricflow_reconciliation(context: dg.AssetExecutionContext) -> dg.MaterializeResult:
    if DBT_TARGET != "dev":
        context.log.info(f"Skipped: the reconciliation reads the DuckDB dev warehouse (target is {DBT_TARGET}).")
        return dg.MaterializeResult(metadata={"status": "skipped", "target": DBT_TARGET})
    out = _run(context, ["scripts/reconcile_metrics.py"])
    checked = sum(int(n) for n in re.findall(r"= (\d+) values checked", out))
    return dg.MaterializeResult(metadata={"status": "match", "values_checked": checked})


# ------------------------------------------------------------------ job + schedule
daily_refresh = dg.define_asset_job(
    "daily_refresh",
    selection=dg.AssetSelection.all(),
    description="Simulate the next business day, load it, gate on freshness, build and test, reconcile.",
    # DuckDB allows a single writer: run the steps one at a time
    executor_def=dg.in_process_executor,
)

daily_schedule = dg.ScheduleDefinition(
    job=daily_refresh,
    cron_schedule="0 6 * * *",
    execution_timezone="Asia/Dubai",  # head office; before the 10:00 store opening
    default_status=dg.DefaultScheduleStatus.STOPPED,  # switch on in the UI when wanted
)

defs = dg.Definitions(
    assets=[source_systems_day, *ingestion, najm_dbt, metricflow_reconciliation],
    jobs=[daily_refresh],
    schedules=[daily_schedule],
    resources={
        "dlt": DagsterDltResource(),
        "dbt": DbtCliResource(project_dir=dbt_project, profiles_dir=str(DBT_DIR), target=DBT_TARGET),
    },
)

if WAREHOUSE != "duckdb" and DBT_TARGET == "dev":
    raise RuntimeError("NAJM_WAREHOUSE=snowflake loads Snowflake RAW: set DBT_TARGET to sf_dev or prod as well")
