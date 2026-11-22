# Integration Testing Runbook

This runbook verifies the five workflows through the FastAPI upload, job-status, and download endpoints. It also checks job history, saved workflow configurations, and common invalid requests.

These tests use generated in-memory sample files and a temporary SQLite database. They do not use customer data and do not change your normal local data directory.

## 1. Get the latest code

From a terminal:

```bash
git pull
```

If you have not cloned the repository yet:

```bash
git clone https://github.com/feldmal/prototype-catalyst.git
cd prototype-catalyst/automation-engine
```

If the repository is already cloned, go to its `automation-engine` directory:

```bash
cd path/to/prototype-catalyst/automation-engine
```

## 2. Run the existing automated suite plus the new API integration tests

### Recommended: Docker

Make sure Docker Desktop is running, then run:

```bash
docker compose run --rm --build automation-api pytest -q
```

This rebuilds the API image if needed, runs all tests, and removes the temporary test container afterward. It does not start or expose the API service.

### Alternative: local Python environment

Use Python 3.12. From the `automation-engine` directory:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux:

```bash
source .venv/bin/activate
```

Install dependencies and run the suite:

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

## 3. What the new integration tests cover

| Test area | What it verifies |
|---|---|
| Clean table | Upload, processing, downloaded output, cleaned values and output metrics |
| Combine files | Two-file upload, cleanup option, combined output and metrics |
| Validate data | Excel report download and detection of invalid numbers, dates, duplicates and missing required columns |
| Transform data | Rename, filter, type conversion, calculated column and dropped column |
| Aggregate data | Multiple grouping columns, sum, average and count |
| API validation | Invalid JSON, unknown workflow, unsupported extension and incorrect file count |
| Job/config support | Filtered job history and saved workflow configuration |

The API currently uses FastAPI in-process background tasks. With the test client, these tasks finish as part of the request lifecycle, so the tests can immediately check for a completed job. This does not test durable processing across API restarts; that requires the future worker/queue implementation.

## 4. Expected result

The test count will be higher than the previous 19 tests because this run includes the new integration tests. A successful run ends with output similar to:

```text
... passed
```

The exact number can change as tests are added. Warnings about the existing FastAPI startup-event deprecation are not test failures, but should be addressed during a later maintenance pass.

If a test fails, copy the complete failure output, including the failing test name and traceback, and share it before changing code. Do not ignore failures or treat a partial test run as a pass.

## 5. Optional manual API smoke test

If you also want to inspect the API interactively:

```bash
docker compose up --build
```

Open [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), then:

1. Call `GET /health`; expect `status: ok`.
2. Call `GET /workflows`; confirm all five workflow names are listed.
3. Use `POST /jobs` to upload a small test CSV and select a workflow.
4. Open the returned job ID with `GET /jobs/{job_id}`.
5. When the status is `completed`, open `GET /jobs/{job_id}/download` and inspect the result.
6. Stop the API with `Ctrl+C`.

Use only synthetic test data for this local prototype.

## 6. Safety boundary

Passing these tests verifies the current local prototype's workflow and API behavior. It does **not** make the service ready for real customer data. Authentication, business/tenant isolation, private production file storage, malware scanning, durable job processing, retention controls, and production security testing are still outstanding. Keep the API bound to localhost and do not expose it publicly.
