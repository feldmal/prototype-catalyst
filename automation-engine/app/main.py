import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app import storage
from app.workflows import clean_table

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "25")) * 1024 * 1024
ALLOWED_SUFFIXES = {".csv", ".xlsx"}

app = FastAPI(
    title="Prototype Catalyst Automation Engine",
    version="0.1.0",
    description="Local development API for file-based automation workflows.",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.on_event("startup")
def startup() -> None:
    storage.initialize_storage()


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
        input_path = Path(job["input_path"])
        output_path = storage.OUTPUT_DIR / f"{job_id}{input_path.suffix.lower()}"
        metrics = clean_table.run(input_path, output_path)
        storage.update_job(
            job_id,
            output_path=str(output_path),
            status="completed",
            error=None,
            updated_at=utc_now(),
        )
        # Metrics are added to job responses in a later iteration; keep the
        # first engine version focused on a stable upload/process/download cycle.
    except Exception:
        storage.update_job(
            job_id,
            status="failed",
            error="The file could not be processed. Check its format and contents, then try again.",
            updated_at=utc_now(),
        )


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "prototype-catalyst-automation"}


@app.post("/jobs", status_code=202)
async def submit_job(
    background_tasks: BackgroundTasks,
    workflow: str = Form("clean_table"),
    file: UploadFile = File(...),
) -> dict:
    if workflow != "clean_table":
        raise HTTPException(status_code=400, detail="Unknown workflow.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload a CSV or XLSX file.")

    job_id = str(uuid.uuid4())
    safe_name = Path(file.filename or "upload").name[:180]
    input_path = storage.UPLOAD_DIR / f"{job_id}{suffix}"

    size = 0
    try:
        with input_path.open("wb") as destination:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    destination.close()
                    input_path.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail="File exceeds the 25 MB upload limit.")
                destination.write(chunk)
    finally:
        await file.close()

    if size == 0:
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    now = utc_now()
    storage.create_job({
        "id": job_id,
        "workflow": workflow,
        "original_filename": safe_name,
        "input_path": str(input_path),
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
    return FileResponse(
        output_path,
        filename=f"cleaned_{job['original_filename']}",
        media_type="application/octet-stream",
    )
