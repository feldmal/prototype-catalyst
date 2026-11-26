import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app import storage
from app.workflows.clean_table import EmptyInputFileError, InvalidCsvStructureError
from app.workflows.registry import WORKFLOWS, get_workflow

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx"}
MAX_FILES_PER_JOB = 10

app = FastAPI(title="Prototype Catalyst Automation Engine", version="0.4.0",
              description="Local development API for reusable file-based automation workflows.")


@app.middleware("http")
async def protect_deployed_api(request, call_next):
    """Require the Worker-to-API bearer token when enabled for hosted deployments."""
    if request.url.path == "/health":
        return await call_next(request)
    if os.getenv("REQUIRE_API_TOKEN", "false").lower() != "true":
        return await call_next(request)
    expected = os.getenv("R2_UPLOAD_API_TOKEN", "")
    supplied = request.headers.get("authorization", "")
    if not expected:
        return JSONResponse({"detail": "API authentication is not configured."}, status_code=503)
    if not secrets.compare_digest(supplied, f"Bearer {expected}"):
        return JSONResponse({"detail": "Unauthorized."}, status_code=401)
    return await call_next(request)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
def startup() -> None:
    storage.initialize_storage()


def _input_paths(job: dict) -> list[Path]:
    stored = job["input_path"]
    try:
        values = json.loads(stored)
        if isinstance(values, list):
            return [Path(value) for value in values]
    except (json.JSONDecodeError, TypeError):
        pass
    return [Path(stored)]


def public_job(job: dict) -> dict:
    def parse_json(key):
        try: return json.loads(job.get(key) or "{}")
        except (json.JSONDecodeError, TypeError): return {}
    return {
        "id": job["id"], "workflow": job["workflow"], "filename": job["original_filename"],
        "options": parse_json("workflow_options"), "metrics": parse_json("result_metrics"),
        "status": job["status"], "error": job["error"], "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "download_url": f"/jobs/{job['id']}/download" if job["status"] == "completed" else None,
    }


def process_job_from_paths(job: dict, input_paths: list[Path], output_path: Path) -> dict:
    workflow = get_workflow(job["workflow"])
    if workflow is None:
        raise ValueError("Unknown workflow.")
    options = json.loads(job.get("workflow_options") or "{}")
    return workflow.run(input_paths, output_path, options=options)


def process_job(job_id: str) -> None:
    job = storage.get_job(job_id)
    if not job: return
    storage.update_job(job_id, status="processing", updated_at=utc_now())
    try:
        workflow = get_workflow(job["workflow"])
        if workflow is None: raise ValueError("Unknown workflow.")
        input_paths = _input_paths(job)
        if not input_paths: raise ValueError("No input files were stored.")
        if workflow.output_format == "xlsx":
            suffix = ".xlsx"
        elif job["workflow"] == "combine_files":
            suffix = ".csv" if all(p.suffix.lower() == ".csv" for p in input_paths) else ".xlsx"
        else:
            suffix = input_paths[0].suffix.lower()
        output_path = storage.OUTPUT_DIR / f"{job_id}{suffix}"
        metrics = process_job_from_paths(job, input_paths, output_path)
        storage.update_job(job_id, output_path=str(output_path), status="completed",
                           error=None, result_metrics=json.dumps(metrics), updated_at=utc_now())
    except EmptyInputFileError as exc:
        storage.update_job(job_id, status="failed", error=str(exc), updated_at=utc_now())
    except InvalidCsvStructureError as exc:
        storage.update_job(job_id, status="failed", error=str(exc), updated_at=utc_now())
    except Exception:
        storage.update_job(job_id, status="failed",
                           error="The files could not be processed. Check the workflow options, file formats, headers, and contents, then try again.",
                           updated_at=utc_now())


from app.r2_api import router as r2_upload_router
app.include_router(r2_upload_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "prototype-catalyst-automation"}


@app.get("/workflows")
def list_workflows() -> dict:
    return {"workflows": [{"name": w.name, "description": w.description,
                            "min_files": w.min_files, "max_files": w.max_files,
                            "output_format": w.output_format} for w in WORKFLOWS.values()]}


@app.post("/jobs", status_code=202)
async def submit_job(
    background_tasks: BackgroundTasks,
    workflow: str = Form("clean_table"),
    cleanup: bool = Form(False),
    options_json: str = Form("{}"),
    files: list[UploadFile] = File(...),
) -> dict:
    selected = get_workflow(workflow)
    if selected is None: raise HTTPException(status_code=400, detail="Unknown workflow. See GET /workflows.")
    try:
        options = json.loads(options_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="options_json must contain valid JSON.")
    if not isinstance(options, dict):
        raise HTTPException(status_code=400, detail="options_json must be a JSON object.")
    if workflow == "combine_files":
        if "cleanup" in options and not isinstance(options["cleanup"], bool):
            raise HTTPException(status_code=400, detail="cleanup must be true or false.")
        options["cleanup"] = cleanup or options.get("cleanup", False)
    elif cleanup:
        raise HTTPException(status_code=400, detail="The cleanup option is only available for combine_files.")
    if not selected.min_files <= len(files) <= selected.max_files or len(files) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=400, detail=f"{workflow} requires between {selected.min_files} and {selected.max_files} file(s).")
    suffixes = [Path(f.filename or "").suffix.lower() for f in files]
    if any(s not in ALLOWED_SUFFIXES for s in suffixes):
        raise HTTPException(status_code=415, detail="Upload CSV or XLSX files only.")

    job_id, saved_paths, safe_names, total_size = str(uuid.uuid4()), [], [], 0
    try:
        for index, upload in enumerate(files, 1):
            suffix = Path(upload.filename or "").suffix.lower()
            name = Path(upload.filename or f"upload_{index}{suffix}").name[:180]
            target = storage.UPLOAD_DIR / f"{job_id}_{index}{suffix}"
            size = 0
            with target.open("wb") as dest:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk); total_size += len(chunk)
                    if total_size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail=f"Combined upload size exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
                    dest.write(chunk)
            if not size: raise HTTPException(status_code=400, detail=f"{name} is empty.")
            saved_paths.append(target); safe_names.append(name)
    except Exception:
        for path in storage.UPLOAD_DIR.glob(f"{job_id}_*"): path.unlink(missing_ok=True)
        raise
    finally:
        for upload in files: await upload.close()

    now = utc_now()
    display_name = safe_names[0] if len(safe_names) == 1 else f"{len(safe_names)} files: " + ", ".join(safe_names)
    storage.create_job({"id": job_id, "workflow": workflow, "original_filename": display_name[:500],
                        "input_path": json.dumps([str(p) for p in saved_paths]), "output_path": None,
                        "status": "queued", "error": None, "created_at": now, "updated_at": now,
                        "workflow_options": json.dumps(options), "result_metrics": "{}"})
    background_tasks.add_task(process_job, job_id)
    return {"job": public_job(storage.get_job(job_id))}


@app.get("/jobs")
def list_jobs(limit: int = 50, offset: int = 0, status: str | None = None, workflow: str | None = None) -> dict:
    if limit < 1 or limit > 200 or offset < 0:
        raise HTTPException(status_code=400, detail="limit must be 1–200 and offset must be zero or greater.")
    if status and status not in {"queued", "processing", "completed", "failed"}:
        raise HTTPException(status_code=400, detail="Invalid job status.")
    if workflow and get_workflow(workflow) is None:
        raise HTTPException(status_code=400, detail="Unknown workflow.")
    return {"jobs": [public_job(job) for job in storage.list_jobs(limit, offset, status, workflow)],
            "limit": limit, "offset": offset}


@app.post("/workflow-configs", status_code=201)
def save_workflow_config(name: str = Form(...), workflow: str = Form(...), options_json: str = Form("{}")) -> dict:
    if not name.strip() or len(name) > 120: raise HTTPException(status_code=400, detail="Provide a name up to 120 characters.")
    if get_workflow(workflow) is None: raise HTTPException(status_code=400, detail="Unknown workflow.")
    try: options = json.loads(options_json)
    except json.JSONDecodeError: raise HTTPException(status_code=400, detail="options_json must contain valid JSON.")
    if not isinstance(options, dict): raise HTTPException(status_code=400, detail="options_json must be a JSON object.")
    now, config_id = utc_now(), str(uuid.uuid4())
    storage.create_workflow_config({"id": config_id, "name": name.strip(), "workflow": workflow,
                                     "options": json.dumps(options), "created_at": now, "updated_at": now})
    return {"config": {"id": config_id, "name": name.strip(), "workflow": workflow, "options": options, "created_at": now}}


@app.get("/workflow-configs")
def list_workflow_configs() -> dict:
    return {"configs": storage.list_workflow_configs()}


@app.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    job = storage.get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    return {"job": public_job(job)}


@app.get("/jobs/{job_id}/download")
def download_result(job_id: str):
    job = storage.get_job(job_id)
    if not job: raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(status_code=409, detail="The job has no completed output yet.")
    if job["output_path"].startswith("r2://"):
        from app.r2_storage import R2Storage, R2ConfigurationError
        try:
            key = job["output_path"][5:]
            return RedirectResponse(R2Storage().create_download_url(key), status_code=307)
        except R2ConfigurationError:
            raise HTTPException(status_code=503, detail="R2 storage is not configured.")
    path = Path(job["output_path"])
    if not path.is_file(): raise HTTPException(status_code=404, detail="The output file is no longer available.")
    prefix = {"combine_files": "combined", "validate_data": "validation_report"}.get(job["workflow"], job["workflow"])
    return FileResponse(path, filename=f"{prefix}_{job_id}{path.suffix}", media_type="application/octet-stream")
