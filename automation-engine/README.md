# Prototype Catalyst Automation Engine

A local-first starter for the reusable file-processing service behind Prototype Catalyst.

## Current scope

- Accept CSV and Excel uploads through an API.
- Validate file type, file count, and combined upload size (25 MB maximum per job).
- Create a tracked processing job and route it through the workflow registry.
- Run `clean_table` on one CSV or XLSX file.
- Run `combine_files` on 2–10 CSV and/or XLSX files, with optional cleanup.
- Make job status and output downloadable.
- Keep uploads and results on local disk for development.

This is an **internal development prototype**, not a public customer upload service. It has no customer authentication, tenant isolation, malware scanning, durable distributed queue, or production object storage yet. Do not expose it to the public internet or upload real customer/confidential data.

## Run locally with Docker

Requirements: Docker Desktop with Docker Compose.

```bash
cd automation-engine
docker compose up --build
```

Open the interactive API documentation at http://127.0.0.1:8000/docs.

## Available workflows

| Workflow | Files | Behavior |
|---|---:|---|
| `clean_table` | 1 | Standardizes headers, trims text, and removes empty rows and columns. |
| `combine_files` | 2–10 | Appends records and aligns columns by header name. Optional cleanup standardizes headers, trims text, and removes fully empty rows and columns before combining. |

List workflows at `GET /workflows`.

## Submit jobs

The upload field is named `files`. For `clean_table`, upload exactly one file:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=clean_table" \
  -F "files=@sample.csv"
```

For basic consolidation (cleanup off):

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=combine_files" \
  -F "cleanup=false" \
  -F "files=@january.csv" \
  -F "files=@february.xlsx"
```

For consolidation with cleanup:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=combine_files" \
  -F "cleanup=true" \
  -F "files=@january.csv" \
  -F "files=@february.xlsx"
```

Cleanup is off by default. When enabled, each input is cleaned before the rows are appended: headers become lowercase snake_case, text whitespace is trimmed, whitespace-only cells are treated as missing, and fully empty rows/columns are removed. If two headers normalize to the same name, numeric suffixes keep them unique (for example, `customer_name` and `customer_name_2`). Duplicate records are **not** removed.

The consolidation workflow matches columns by header name. Columns absent from one input are blank for that input's rows. If every input is CSV, output is CSV; if any input is XLSX, output is XLSX.

Check status using the returned job ID:

```bash
curl http://127.0.0.1:8000/jobs/JOB_ID
```

When status is `completed`, download the output using the returned `download_url`.

## Run the full automated test suite

From the `automation-engine` directory:

```bash
docker compose run --rm --build automation-api pytest -q
```

Tests cover CSV/XLSX cleanup, basic consolidation, mixed-format consolidation, optional cleanup on and off, duplicate normalized headers, API upload and download, and invalid option handling.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| GET | `/workflows` | List registered workflows and file-count requirements |
| POST | `/jobs` | Upload file(s) and start a workflow |
| GET | `/jobs/{job_id}` | Read job status and metadata |
| GET | `/jobs/{job_id}/download` | Download completed output |

## Project structure

- `app/main.py`: HTTP API and job lifecycle.
- `app/storage.py`: local SQLite job metadata and file paths.
- `app/workflows/registry.py`: workflow definitions and file-count rules.
- `app/workflows/clean_table.py`: single-file cleanup workflow.
- `app/workflows/combine_files.py`: multi-file consolidation workflow.
- `tests/`: workflow and API regression tests.
- `data/`: local working files (git-ignored).

The SQLite storage initializer adds the workflow-options column to an existing local database without deleting prior job history.

## Production limitations

This remains a local development prototype. It does not yet provide customer authentication, tenant isolation, malware scanning, a durable distributed queue, production object storage, retention/deletion controls, or operational monitoring. Do not expose it publicly or upload confidential/customer data.

Next production steps:
1. Add authenticated users and business/tenant ownership.
2. Move metadata to PostgreSQL and files to private object storage.
3. Replace in-process background execution with a durable queue and separate worker.
4. Add malware scanning, retention/deletion controls, audit events, quotas, and monitoring.
5. Add per-customer workflow configuration and isolated execution.
6. Deploy behind an authenticated API, separate from the Cloudflare marketing Worker.
