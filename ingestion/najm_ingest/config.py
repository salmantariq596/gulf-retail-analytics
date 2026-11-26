from __future__ import annotations

import os
from pathlib import Path

import dlt
from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")
os.environ.setdefault("RUNTIME__DLTHUB_TELEMETRY", "false")


def _repo_path(env: str, default: str) -> Path:
    p = Path(os.getenv(env, default))
    return p if p.is_absolute() else (REPO_ROOT / p).resolve()


DUCKDB_PATH = _repo_path("DUCKDB_PATH", "data/warehouse/najm_dev.duckdb")
LANDING_DIR = _repo_path("GEN_OUTPUT_DIR", "data/landing")
# pipeline state (incremental watermarks); separate dirs keep separate datasets apart
PIPELINES_DIR = _repo_path("DLT_PIPELINES_DIR", "data/dlt_pipelines")
# 127.0.0.1, not localhost: on Windows "localhost" tries IPv6 first and adds ~2s per request
API_BASE_URL = os.getenv("MOCK_API_BASE_URL", "http://127.0.0.1:8000")


def postgres_url() -> str:
    return (f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'najm')}:{os.getenv('POSTGRES_PASSWORD', 'najm_local_pw')}"
            f"@{os.getenv('POSTGRES_HOST', 'localhost')}:{os.getenv('POSTGRES_PORT', '5432')}"
            f"/{os.getenv('POSTGRES_DB', 'najm_pos')}")


# NAJM_WAREHOUSE=duckdb (default, local dev) | snowflake (Phase 5: RAW database, key-pair auth)
WAREHOUSE = os.getenv("NAJM_WAREHOUSE", "duckdb").lower()


def destination():
    if WAREHOUSE == "snowflake":
        return dlt.destinations.snowflake(credentials={
            "host": os.environ["SNOWFLAKE_ACCOUNT"],
            "username": os.getenv("SNOWFLAKE_LOADER_USER", "dlt_user"),
            "private_key_path": os.environ["SNOWFLAKE_LOADER_PRIVATE_KEY_PATH"],
            "private_key_passphrase": os.getenv("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE"),
            "database": "RAW",
            "warehouse": "LOAD_WH",
            "role": "LOADER",
        })
    DUCKDB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return dlt.destinations.duckdb(str(DUCKDB_PATH))


def pipeline(name: str, dataset: str) -> dlt.Pipeline:
    """Every source gets its own pipeline (own state) and its own raw schema.
    Pipeline state is kept per warehouse so dev (DuckDB) and prod (Snowflake)
    watermarks never mix."""
    return dlt.pipeline(
        pipeline_name=f"{name}_{WAREHOUSE}" if WAREHOUSE != "duckdb" else name,
        destination=destination(),
        dataset_name=dataset,
        pipelines_dir=str(PIPELINES_DIR),
    )
