# Prototype Catalyst Automation Engine

A local-first starter for the reusable file-processing service behind Prototype Catalyst.

## Current scope

- Accept CSV and XLSX uploads through an API (25 MB combined per job; up to 10 files).
- Track jobs and expose status, metrics, and downloadable results.
- Run five workflows: cleanup, consolidation, validation, transformation, and aggregation.
- Save reusable workflow configurations for repeat processing.
- Keep uploads, outputs, and metadata on local disk for development.

**This is an internal development prototype, not a public customer upload service.** It has no customer authentication, tenant isolation, malware scanning, durable distributed queue, production object storage, or production scheduler. Do not expose it publicly or upload real customer/confidential data.

## Run locally

Requirements: Docker Desktop with Docker Compose.

```bash
cd automation-engine
docker compose up --build
```

Open http://127.0.0.1:8000/docs for interactive API documentation.

## Workflows

| Workflow | Files | Output | Behavior |
|---|---:|---|---|
| `clean_table` | 1 | Same format | Standardizes headers, trims text, removes fully empty rows/columns. |
| `combine_files` | 2–10 | CSV if all inputs CSV, otherwise XLSX | Appends rows and aligns columns by header. Optional `cleanup=true` cleans each input first. Duplicate records are not removed. |
| `validate_data` | 1 | XLSX report | Reports missing values and duplicate rows; optionally checks required, date, and numeric columns. Source file is not changed. |
| `transform_data` | 1 | Same format | Renames/drops columns, filters rows, converts types, and creates arithmetic columns. |
| `aggregate_data` | 1 | Same format | Groups by one or more columns and calculates sum, mean, count, min, max, or distinct count. |

### Workflow options

Pass workflow-specific options as JSON in the `options_json` multipart form field. For example:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=aggregate_data" \
  -F 'options_json={"group_by":["region"],"aggregations":{"sales":["sum","mean"],"order_id":"count"}}' \
  -F "files=@sales.csv"
```

Transformation example:

```json
{
  "rename_columns": {"Customer Name": "customer"},
  "filters": [{"column": "status", "operator": "eq", "value": "Complete"}],
  "column_types": {"amount": "float"},
  "calculated_columns": [{"name": "total", "left": "quantity", "operator": "multiply", "right": "unit_price"}],
  "drop_columns": ["internal_note"]
}
```

Filter operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `contains`, `is_null`, `not_null`. Calculated-column operators: `add`, `subtract`, `multiply`, `divide`. Calculations use column names or numeric constants; arbitrary Python code is not evaluated.

Validation options:

```json
{"required_columns":["customer_id"],"date_columns":["order_date"],"numeric_columns":["amount"],"check_duplicates":true}
```

Aggregation options:

```json
{"group_by":["region","product"],"aggregations":{"sales":["sum","mean"],"order_id":"count"}}
```

## Job history and reusable configurations

- `GET /jobs?limit=50&offset=0&status=completed&workflow=aggregate_data` lists recent jobs; filters are optional.
- `GET /jobs/{job_id}` returns status, options, and result metrics.
- `POST /workflow-configs` saves a named workflow and its JSON options.
- `GET /workflow-configs` lists saved configurations.

Saved configurations are reusable presets only. They do not yet trigger jobs automatically. Scheduled execution is deferred until a durable scheduler/worker is introduced; the current FastAPI background task runs in-process and is not durable.

## API routes

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| GET | `/workflows` | Registered workflows |
| POST | `/jobs` | Upload files and start a workflow |
| GET | `/jobs` | Filterable job history |
| GET | `/jobs/{job_id}` | Job status and metrics |
| GET | `/jobs/{job_id}/download` | Download completed output |
| POST | `/workflow-configs` | Save a reusable workflow preset |
| GET | `/workflow-configs` | List saved presets |

## Full test suite

From `automation-engine`:

```bash
docker compose run --rm --build automation-api pytest -q
```

The tests cover cleanup and consolidation, validation reports, transformation rules, aggregation, API upload/download, job history, and saved workflow configurations.

## Project structure

- `app/main.py`: HTTP API and job lifecycle.
- `app/storage.py`: SQLite job history and workflow presets.
- `app/workflows/registry.py`: workflow definitions and file-count rules.
- `app/workflows/`: individual workflow implementations.
- `tests/`: workflow and API regression tests.
- `data/`: local working files (git-ignored).

## Production roadmap

Before handling customer data, add authentication and tenant ownership, PostgreSQL, private object storage, a durable queue and scheduler, malware scanning, retention/deletion controls, audit events, quotas, monitoring, and security testing. Keep processing behind an authenticated API, separate from the Cloudflare marketing Worker.
