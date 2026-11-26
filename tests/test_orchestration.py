"""The Dagster code location loads and forms one connected graph."""

from pathlib import Path

import pytest

MANIFEST = Path(__file__).resolve().parents[1] / "dbt" / "target" / "manifest.json"
pytestmark = [
    pytest.mark.slow,  # loads the whole code location; left out of the pre-commit hook
    pytest.mark.skipif(not MANIFEST.exists(), reason="run `dbt parse` first (needs dbt/target/manifest.json)"),
]


@pytest.fixture(scope="module")
def graph():
    from najm_orchestration.definitions import defs

    return defs.resolve_asset_graph()


def test_every_dependency_is_produced_by_an_asset(graph):
    # dlt tables must be keyed like the dbt sources, or lineage breaks into islands
    external = [k.to_user_string() for k in graph.get_all_asset_keys() if not graph.get(k).is_materializable]
    assert external == []


def test_staging_reads_the_ingested_tables(graph):
    stg = next(k for k in graph.get_all_asset_keys() if k.path[-1] == "stg_pos__sales")
    assert [k.to_user_string() for k in graph.get(stg).parent_keys] == ["pos/sales"]


def test_daily_job_and_schedule():
    from najm_orchestration.definitions import defs

    job = defs.resolve_job_def("daily_refresh")
    assert job is not None
    schedule = defs.resolve_schedule_def("daily_refresh_schedule")
    assert schedule.cron_schedule == "0 6 * * *"
    assert schedule.execution_timezone == "Asia/Dubai"
