# Prototype Catalyst Automation Engine

A local-first starter for the reusable file-processing service behind Prototype Catalyst.

## Current scope

- Accept CSV and Excel uploads through an API.
- Validate file type, file count, and combined upload size (25 MB maximum per job).
- Create a tracked processing job.
- Route work through a small workflow registry.
- Run `clean_table` on one CSV or XLSX file.
- Run `combine_files` on 2–10 CSV and/or XLSX files.
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

List available workflows:

```bash
curl http://127.0.0.1:8000/workflows
```

## Submit a job

The upload field is named `files`. For `clean_table`, upload exactly one file:

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=clean_table" \
  -F "files=@sample.csv"
```

For `combine_files`, upload at least two files (up to ten):

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -F "workflow=combine_files" \
  -F "files=@january.csv" \
  -F "files=@february.xlsx"
```

The consolidation workflow appends rows and aligns columns by header name. If every input is CSV, the result is CSV. If any input is XLSX, the result is XLSX. Columns that are absent from a particular input are blank for those rows. The workflow does not automatically clean or rename headers; it matches the header names as provided.

Check status using the returned job ID:

```bash
curl http://127.0.0.1:8000/jobs/JOB_ID
```

When status is `completed`, download the output:

```bash
curl -L -o combined.xlsx http://127.0.0.1:8000/jobs/JOB_ID/download
```

## Run automated tests

From the `automation-engine` directory:

```bash
docker compose run --rm --build automation-api pytest -q
```

The tests cover CSV and XLSX cleanup, empty and whitespace-only rows/columns, output format preservation, CSV consolidation, mixed CSV/XLSX consolidation, minimum file count, and workflow registry entries.

## Available workflows

| Workflow | Files | Behavior |
|---|---:|---|
| `clean_table` | 1 | Standardizes headers, trims text, and removes empty rows and columns. |
| `combine_files` | 2–10 | Appends records from multiple files and aligns columns by header name. |

New workflows should be implemented as separate modules and registered in `app/workflows/registry.py`. The API uses each registry entry's file-count rules and runner, so adding another workflow does not require hard-coding its processing logic into the job worker.

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
- `tests/`: workflow regression tests.
- `data/`: local working files (git-ignored).

## Next production steps

1. Add authenticated users and business/tenant ownership before any customer access.
2. Move metadata to PostgreSQL and files to private object storage.
3. Replace in-process background execution with a durable queue and separate worker.
4. Add malware scanning, retention/deletion controls, audit events, quotas, and operational monitoring.
5. Add per-customer workflow configuration and isolated execution.
6. Deploy behind an authenticated API; keep this service separate from the Cloudflare marketing Worker.
