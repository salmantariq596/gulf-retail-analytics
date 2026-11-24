"""najm-ingest [all|pos|online|erp|catalog|marketing]

Runs the dlt pipelines one after another (DuckDB allows a single writer) and
prints how many rows each table received.
"""

from __future__ import annotations

import argparse
import time

from . import files, online, pos

PIPELINES = {
    "pos": pos.run,
    "online": online.run,
    "erp": files.run_erp,
    "catalog": files.run_catalog,
    "marketing": files.run_marketing,
}


def _row_counts(info_pipeline) -> dict:
    trace = info_pipeline.last_trace
    counts = trace.last_normalize_info.row_counts if trace and trace.last_normalize_info else {}
    return {k: v for k, v in counts.items() if not k.startswith("_dlt")}


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="najm-ingest")
    ap.add_argument("sources", nargs="*", default=["all"], choices=["all", *PIPELINES])
    args = ap.parse_args(argv)
    selected = list(PIPELINES) if "all" in args.sources else args.sources
    for name in selected:
        t0 = time.time()
        info = PIPELINES[name]()
        counts = _row_counts(info.pipeline)
        summary = ", ".join(f"{k}={v:,}" for k, v in sorted(counts.items())) or "no new rows"
        print(f"[{name:9}] {time.time() - t0:5.1f}s  {summary}", flush=True)


if __name__ == "__main__":
    main()
