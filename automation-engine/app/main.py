import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import storage
from app.workflows.registry import get_workflow

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx"}
MAX_FILES_PER_JOB = 10

app = FastAPI(
    title="Prototype Catalyst Automation Engine",
    version="0.2.0",
    description="Local development API for file-based automation workflows.",
)


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
    # Backward compatibility for jobs created before multi-file support.
    return [Path(stored)]


def public_job(job: dict) -> dict:
    return {
        "id": job["id"],
        "workflow": job["workflow"],
        "filename": job["original_filename"],
        "status": job["status"],
        "error": job["error"],
        "created_at": job["created_at"],
        "updated_at": job["updated_at"],
        "download_url": f"/jobs/{job['id']}/download" if job["status"] == "completed" else None,
    }


def process_job(job_id: str) -> None:
    job = storage.get_job(job_id)
    if not job:
        return

    storage.update_job(job_id, status="processing", updated_at=utc_now())
    try:
        workflow = get_workflow(job["workflow"])
        if workflow is None:
            raise ValueError("Unknown workflow.")

        input_paths = _input_paths(job)
        if not input_paths:
            raise ValueError("No input files were stored.")

        if job["workflow"] == "combine_files":
            output_suffix = ".csv" if all(path.suffix.lower() == ".csv" for path in input_paths) else ".xlsx"
        else:
            output_suffix = input_paths[0].suffix.lower()

        output_path = storage.OUTPUT_DIR / f"{job_id}{output_suffix}"
        workflow.run(input_paths, output_path)
        storage.update_job(
            job_id,
            output_path=str(output_path),
            status="completed",
            error=None,
            updated_at=utc_now(),
        )
    except Exception:
        storage.update_job(
            job_id,
            status="failed",
            error="The files could not be processed. Check their formats, headers, and contents, then try again.",
            updated_at=utc_now(),
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "prototype-catalyst-automation"}


@app.get("/workflows")
def list_workflows() -> dict:
    return {
        "workflows": [
            {
                "name": workflow.name,
                "description": workflow.description,
                "min_files": workflow.min_files,
                "max_files": workflow.max_files,
            }
            for workflow in get_registered_workflows()
        ]
    }


def get_registered_workflows():
    from app.workflows.registry import WORKFLOWS
    return WORKFLOWS.values()


@app.post("/jobs", status_code=202)
async def submit_job(
    background_tasks: BackgroundTasks,
    workflow: str = Form("clean_table"),
    files: list[UploadFile] = File(...),
) -> dict:
    selected_workflow = get_workflow(workflow)
    if selected_workflow is None:
        raise HTTPException(status_code=400, detail="Unknown workflow. See GET /workflows.")

    if not selected_workflow.min_files <= len(files) <= selected_workflow.max_files:
        raise HTTPException(
            status_code=400,
            detail=f"{workflow} requires between {selected_workflow.min_files} and {selected_workflow.max_files} file(s).",
        )
    if len(files) > MAX_FILES_PER_JOB:
        raise HTTPException(status_code=400, detail=f"A job may contain at most {MAX_FILES_PER_JOB} files.")

    suffixes = [Path(upload.filename or "").suffix.lower() for upload in files]
    if any(suffix not in ALLOWED_SUFFIXES for suffix in suffixes):
        raise HTTPException(status_code=415, detail="Upload CSV or XLSX files only.")

    job_id = str(uuid.uuid4())
    saved_paths: list[Path] = []
    safe_names: list[str] = []
    total_size = 0

    try:
        for index, upload in enumerate(files, start=1):
            suffix = Path(upload.filename or "").suffix.lower()
            safe_name = Path(upload.filename or f"upload_{index}{suffix}").name[:180]
            input_path = storage.UPLOAD_DIR / f"{job_id}_{index}{suffix}"
            size = 0
            with input_path.open("wb") as destination:
                while chunk := await upload.read(1024 * 1024):
                    size += len(chunk)
                    total_size += len(chunk)
                    if total_size > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Combined upload size exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.",
                        )
                    destination.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail=f"{safe_name} is empty.")
            saved_paths.append(input_path)
            safe_names.append(safe_name)
    except Exception:
        for path in saved_paths:
            path.unlink(missing_ok=True)
        for path in storage.UPLOAD_DIR.glob(f"{job_id}_*"):
            path.unlink(missing_ok=True)
        raise
    finally:
        for upload in files:
            await upload.close()

    now = utc_now()
    display_filename = safe_names[0] if len(safe_names) == 1 else f"{len(safe_names)} files: " + ", ".join(safe_names)
    storage.create_job({
        "id": job_id,
        "workflow": workflow,
        "original_filename": display_filename[:500],
        "input_path": json.dumps([str(path) for path in saved_paths]),
        "output_path": None,
        "status": "queued",
        "error": None,
        "created_at": now,
        "updated_at": now,
    })
    background_tasks.add_task(process_job, job_id)
    return {"job": public_job(storage.get_job(job_id))}


@app.get("/jobs/{job_id}")
def read_job(job_id: str) -> dict:
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return {"job": public_job(job)}


@app.get("/jobs/{job_id}/download")
def download_result(job_id: str):
    job = storage.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    if job["status"] != "completed" or not job["output_path"]:
        raise HTTPException(status_code=409, detail="The job has no completed output yet.")
    output_path = Path(job["output_path"])
    if not output_path.is_file():
        raise HTTPException(status_code=404, detail="The output file is no longer available.")
    prefix = "combined" if job["workflow"] == "combine_files" else "cleaned"
    return FileResponse(
        output_path,
        filename=f"{prefix}_{job_id}{output_path.suffix}",
        media_type="application/octet-stream",
    )
