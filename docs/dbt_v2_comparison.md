# dbt v1.11 vs dbt v2 (OSS) on this project

dbt v2 parses this project about 7× faster than v1.11. A full build takes the same time,
because the warehouse does the work. Both engines produced identical tables once two small
incompatibilities were fixed. The project stays on dbt Core 1.11 for now, because MetricFlow
and the Lightdash CLI read the v1 semantic-model YAML that v2 has deprecated.

Tested 2026-11-26 with **dbt-oss 2.0.11** (the Apache-2.0 Rust engine, GA at dbt Summit 2026,
DuckDB adapter built in) against **dbt-core 1.11.17 + dbt-duckdb 1.11.1**. Target: DuckDB dev,
about 3 months of data and 490k sales lines, on a Windows laptop. Both engines were run
alternately under the same background load. Snowflake was not tested, to save trial credits.

## Speed

| Step | dbt 1.11 | dbt v2 | Note |
|---|---|---|---|
| Parse, cold (v1 `--no-partial-parse`) | 20.5 s / 23.7 s | 3.7 s / 2.8 s | two runs each; about 7× faster |
| Parse, v1 partial parse | 9.9 s | – | v1's cache still leaves v2 about 3× ahead |
| First v2 parse | – | 56 s | one-off: installs packages, downloads the DuckDB driver |
| `dbt build --full-refresh` (351 nodes) | 271 s | 262 s | same: time is spent in DuckDB running the SQL |

## Results: identical

Each engine built its own copy of the warehouse, and all 47 relations were compared on row
count, an order-independent hash of every row, and column types:

- 46 of 47 relations are identical.
- `fct_sales_lines` has the same rows, keys and business values. Only the `dbt_loaded_at`
  audit timestamp differs, which is the time of each build.
- Tests: v1 PASS=349, WARN=2; v2 349 success, 2 warn. The same 2 known warnings in both.

## What v2 caught

| Finding | Severity | What happened | Fix |
|---|---|---|---|
| Jinja in YAML metadata | error | A generated Lightdash description quoted MetricFlow's `{{ Dimension('…') }}` filter. v1 never renders `meta`; v2 renders every YAML string and fails on the unknown function. | `scripts/semantic_export.py` describes the filter in words |
| Seed type inference | error | v2 loads seeds with Arrow, which reads `hijri_date` values like `1440-02-30` (valid Umm al-Qura, not Gregorian) as `DATE` and fails. v1 fell back to text. | `hijri_date: varchar` in the seed's `column_types` |
| Legacy semantic-model YAML | warning | v2 deprecates the `semantic_models:` / `metrics:` format that MetricFlow 0.16 and this project use. | Not migrated (see below) |
| Contract types on `dim_date` | warning (8) | v2's static analysis infers `character varying(256)` where the contract says `varchar`. v1 never compares them. | None needed: equivalent types in DuckDB |

Everything else ran unchanged on v2: dbt_utils and dbt_expectations, YAML snapshots, unit tests,
model contracts, incremental `delete+insert`, `adapter.dispatch` macros, and custom generic tests.

## Decision

The project stays on dbt Core 1.11 for three reasons:

- **Semantic layer:** the MetricFlow CLI (`mf`), the Lightdash export and its reconciliation
  are built on the v1 semantic-model YAML. Moving to v2 means migrating that YAML first.
- **Certification:** the dbt Analytics Engineering certification is on 1.11.
- **No real time saving:** build time, which dominates CI and the daily run, is the same on
  both engines.

The two fixes above are kept, so the project builds on v2 today. When the semantic-layer YAML
is migrated, switching is a change to `requirements.txt` and the CI install step.

Sources: [dbt-oss on PyPI](https://pypi.org/project/dbt-oss/) · [DuckDB: DuckDB now ships inside dbt v2](https://duckdb.org/2026/09/22/dbt-fusion) · [Datacoves: dbt 2.0 and dbt Fusion](https://datacoves.com/post/dbt-fusion) · [The Information Lab: dbt v2](https://www.theinformationlab.co.uk/community/blog/introduction-to-dbt-v2/)
