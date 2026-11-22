# Prototype Catalyst Automation Engine

A local-first starter for the reusable file-processing service behind Prototype Catalyst.

## Current scope

- Accept CSV and XLSX uploads through an API (25 MB combined per job; up to 10 files).
- Track jobs and expose status, metrics, and downloadable results.
- Run five workflows: cleanup, consolidation, validation, transformation, and aggregation.
- Save reusable workflow configurations for repeat processing.
- Keep uploads and outputs on local disk for development.\n- Use SQLite by default, with an optional PostgreSQL backend for local infrastructure testing.

**This is an internal development prototype, not a public customer upload service.** It has no customer authentication, tenant isolation, malware scanning, durable distributed queue, production object storage, or production scheduler. Do not expose it publicly or upload real customer/confidential data.

## Run locally

Requirements: Docker Desktop with Docker Compose.

```bash
cd automation-engine
docker compose up --build
```

Open http://127.0.0.1:8000/docs for interactive API documentation.

## Database configuration

The default local setup continues to use SQLite. The storage layer now uses SQLAlchemy and can connect to PostgreSQL through `DATABASE_URL`.

To run the API and PostgreSQL together locally:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml up --build
```

The PostgreSQL development database is exposed on localhost port 5433. Its credentials in `compose.postgres.yaml` are for local development only; do not reuse them outside your machine.

To run the test suite against the default isolated SQLite test databases:

```bash
docker compose run --rm --build automation-api pytest -q
```

To stop the PostgreSQL development stack:

```bash
docker compose -f compose.yaml -f compose.postgres.yaml down
```

This initial database step creates the existing jobs and workflow configuration tables in PostgreSQL and preserves the existing SQLite default. It does not yet migrate historical SQLite records into PostgreSQL. Keep your existing Docker volume and SQLite data until a separate, verified data migration is planned.

## Cloudflare R2 storage foundation (initial integration)

The codebase now includes an S3-compatible R2 storage adapter in `app/r2_storage.py`.
It supports private-bucket multipart initiation, short-lived presigned part URLs,
multipart completion/abort, and short-lived download URLs. The default configured
maximum object size is 1,024 MiB (1 GiB), adjustable with `R2_MAX_UPLOAD_MB`.
Multipart parts default to 16 MiB; the adapter enforces S3/R2's 5 MiB minimum
(except the final part) and 10,000-part ceiling.

The R2 multipart API is now connected to job creation and processing for
single-file workflows. Routes are:
- `POST /r2/uploads` — create a multipart session (filename, size_bytes, workflow, options).
- `POST /r2/uploads/{upload_id}/parts/{part_number}/url` — request a short-lived part URL.
- `POST /r2/uploads/{upload_id}/complete` — verify uploaded size, create a job, and start processing.
- `DELETE /r2/uploads/{upload_id}` — abort an unfinished multipart upload.

These routes require `Authorization: Bearer <R2_UPLOAD_API_TOKEN>`. Configure
R2 credentials and a long random token in a local `.env` file. Never commit
`.env`, put the token in browser JavaScript, or paste credentials into chat.
The token is a temporary shared-secret gate, not per-customer authentication.
Keep this API private; do not expose it to customers until user sessions,
tenant ownership checks, and authorization on job status/download routes exist.

The completed upload is downloaded to temporary local disk for processing and
the output is written back to R2. Ensure the host has enough temporary disk and
memory for the file and selected workflow. Processing still uses FastAPI's
in-process background task, so it is not durable across restarts. The legacy
`POST /jobs` remains local-disk based with its existing 25 MiB limit.

Configure the private R2 bucket's CORS policy to allow PUT from the exact
frontend origin and expose the `ETag` response header. The browser must obtain
upload URLs from a trusted backend; it must never receive the shared API token.
The API does not yet provide that authenticated browser-facing proxy/session layer.

The R2 adapter's unit tests use a mocked S3 client, so they do not require an
R2 account or incur storage charges.

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
| POST | `/r2/uploads` | Start authenticated R2 multipart upload |
| POST | `/r2/uploads/{upload_id}/parts/{part_number}/url` | Create presigned part URL |
| POST | `/r2/uploads/{upload_id}/complete` | Complete upload and create processing job |
| DELETE | `/r2/uploads/{upload_id}` | Abort unfinished R2 upload |
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
- `app/storage.py`: SQLAlchemy-backed job history and workflow presets (SQLite by default; PostgreSQL via `DATABASE_URL`).
- `app/workflows/registry.py`: workflow definitions and file-count rules.
- `app/workflows/`: individual workflow implementations.
- `tests/`: workflow and API regression tests.
- `data/`: local working files (git-ignored).

## Production roadmap

Before handling customer data, add authentication and tenant ownership, PostgreSQL, private object storage, a durable queue and scheduler, malware scanning, retention/deletion controls, audit events, quotas, monitoring, and security testing. Keep processing behind an authenticated API, separate from the Cloudflare marketing Worker.
