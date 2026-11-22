# Prototype Catalyst Automation Engine

A local-first starter for the reusable file-processing service behind Prototype Catalyst.

## Current scope

- Accept CSV and Excel uploads through an API.
- Validate file type and size (25 MB maximum).
- Create a tracked processing job.
- Run the built-in `clean_table` workflow.
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

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Submit a file:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=clean_table" \
  -F "file=@sample.csv"
```

Check status using the returned job ID:

```bash
curl http://127.0.0.1:8000/jobs/JOB_ID
```

When status is `completed`, download the output:

```bash
curl -L -o cleaned.csv http://127.0.0.1:8000/jobs/JOB_ID/download
```

## Run automated tests

From the `automation-engine` directory, run the regression tests inside the Docker image:

```bash
docker compose run --rm --build automation-api pytest -q
```

The tests cover both CSV and XLSX inputs, including whitespace-only rows and columns, fully blank rows, normalized headers, trimmed values, and output format preservation.

## Built-in workflow: clean_table

The starter workflow:
- Trims whitespace from column names and text cells.
- Converts column names to lowercase snake_case.
- Removes completely empty rows and columns.
- Preserves numeric values and dates where possible.
- Writes a cleaned CSV or Excel file matching the input type.

It is intentionally a small, predictable demonstration workflow. Client-specific transformations should be added as separate, tested workflow modules rather than hard-coded into the API.

## API

| Method | Route | Purpose |
|---|---|---|
| GET | `/health` | Service health |
| POST | `/jobs` | Upload a file and start a workflow |
| GET | `/jobs/{job_id}` | Read job status and metadata |
| GET | `/jobs/{job_id}/download` | Download completed output |

## Project structure

- `app/main.py`: HTTP API and job lifecycle.
- `app/storage.py`: local SQLite job metadata and file paths.
- `app/workflows/clean_table.py`: sample Pandas workflow.
- `tests/`: workflow and API tests.
- `data/`: local working files (git-ignored).

## Next production steps

1. Add authenticated users and business/tenant ownership before any customer access.
2. Move metadata to PostgreSQL and files to private object storage.
3. Replace in-process background execution with a durable queue and separate worker.
4. Add malware scanning, retention/deletion controls, audit events, quotas, and operational monitoring.
5. Add per-customer workflow configuration and isolated execution.
6. Deploy behind an authenticated API; keep this service separate from the Cloudflare marketing Worker.
