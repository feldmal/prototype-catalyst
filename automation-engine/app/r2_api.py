"""Authenticated R2 multipart upload routes (single-file job submission)."""
from __future__ import annotations

import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app import storage
from app.r2_storage import R2ConfigurationError, R2Storage, UploadSizeError
from app.workflows.registry import get_workflow

router = APIRouter(prefix="/r2/uploads", tags=["R2 uploads"])
ALLOWED_SUFFIXES = {".csv", ".xlsx"}
CONTENT_TYPES = {".csv": "text/csv", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_upload_token(authorization: str | None = Header(default=None)) -> None:
    expected = os.getenv("R2_UPLOAD_API_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="R2 upload API is not configured.")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="A valid bearer token is required.")


def r2() -> R2Storage:
    try:
        return R2Storage()
    except R2ConfigurationError as exc:
        raise HTTPException(status_code=503, detail=str(exc))


class InitiateRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=180)
    size_bytes: int = Field(gt=0)
    workflow: str = "clean_table"
    options: dict = Field(default_factory=dict)


class CompleteRequest(BaseModel):
    parts: list[dict] = Field(min_length=1, max_length=10000)


def _session_upload(session: dict):
    from app.r2_storage import MultipartUpload
    return MultipartUpload(
        bucket=os.environ["R2_BUCKET"],
        key=session["object_key"],
        upload_id=session["multipart_upload_id"],
        part_size=int(session["part_size"]),
        part_count=int(session["part_count"]),
        max_object_size=int(os.getenv("R2_MAX_UPLOAD_MB", "1024")) * 1024 * 1024,
    )


@router.post("", status_code=201, dependencies=[Depends(require_upload_token)])
def initiate_upload(payload: InitiateRequest):
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(status_code=415, detail="Upload CSV or XLSX files only.")
    workflow = get_workflow(payload.workflow)
    if workflow is None:
        raise HTTPException(status_code=400, detail="Unknown workflow.")
    if workflow.min_files != 1 or workflow.max_files != 1:
        raise HTTPException(status_code=400, detail="R2 uploads currently support single-file workflows only.")
    clean_name = re.sub(r"[^A-Za-z0-9._-]", "_", Path(payload.filename).name)[:180]
    session_id = str(uuid.uuid4())
    key = f"incoming/{session_id}/{clean_name}"
    try:
        upload = r2().initiate_multipart(key, CONTENT_TYPES[suffix], payload.size_bytes)
    except UploadSizeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    stamp = now()
    storage.create_r2_upload_session({
        "id": session_id, "object_key": key, "multipart_upload_id": upload.upload_id,
        "filename": clean_name, "content_type": CONTENT_TYPES[suffix],
        "expected_size": str(payload.size_bytes), "part_size": str(upload.part_size),
        "part_count": str(upload.part_count), "workflow": payload.workflow,
        "workflow_options": json.dumps(payload.options), "status": "uploading",
        "created_at": stamp, "updated_at": stamp,
    })
    return {"upload_id": session_id, "part_size": upload.part_size,
            "part_count": upload.part_count, "max_upload_mb": int(os.getenv("R2_MAX_UPLOAD_MB", "1024"))}


@router.post("/{session_id}/parts/{part_number}/url", dependencies=[Depends(require_upload_token)])
def get_part_url(session_id: str, part_number: int):
    session = storage.get_r2_upload_session(session_id)
    if not session or session["status"] != "uploading":
        raise HTTPException(status_code=404, detail="Active upload session not found.")
    try:
        url = r2().create_part_url(_session_upload(session), part_number)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"part_number": part_number, "url": url, "expires_in": 900}


@router.post("/{session_id}/complete", status_code=202, dependencies=[Depends(require_upload_token)])
def complete_upload(session_id: str, payload: CompleteRequest, background_tasks: BackgroundTasks):
    session = storage.get_r2_upload_session(session_id)
    if not session or session["status"] != "uploading":
        raise HTTPException(status_code=404, detail="Active upload session not found.")
    if len(payload.parts) != int(session["part_count"]):
        raise HTTPException(status_code=400, detail="Every expected part must be supplied.")
    try:
        client = r2()
        client.complete_multipart(_session_upload(session), payload.parts)
        actual_size = int(client.head_object(session["object_key"]).get("ContentLength", -1))
        if actual_size != int(session["expected_size"]):
            raise ValueError("Uploaded object size does not match the declared file size.")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    stamp, job_id = now(), str(uuid.uuid4())
    storage.update_r2_upload_session(session_id, status="completed", updated_at=stamp)
    storage.create_job({
        "id": job_id, "workflow": session["workflow"], "original_filename": session["filename"],
        "input_path": json.dumps([f"r2://{session['object_key']}"]), "output_path": None,
        "status": "queued", "error": None, "created_at": stamp, "updated_at": stamp,
        "workflow_options": session["workflow_options"], "result_metrics": "{}",
    })
    background_tasks.add_task(process_r2_job, job_id, session["object_key"])
    return {"job_id": job_id, "status": "queued", "status_url": f"/jobs/{job_id}"}


@router.delete("/{session_id}", dependencies=[Depends(require_upload_token)])
def abort_upload(session_id: str):
    session = storage.get_r2_upload_session(session_id)
    if not session or session["status"] != "uploading":
        raise HTTPException(status_code=404, detail="Active upload session not found.")
    r2().abort_multipart(_session_upload(session))
    storage.update_r2_upload_session(session_id, status="aborted", updated_at=now())
    return {"upload_id": session_id, "status": "aborted"}


def process_r2_job(job_id: str, object_key: str) -> None:
    import tempfile
    from app.main import process_job_from_paths
    job = storage.get_job(job_id)
    if not job:
        return
    suffix = Path(job["original_filename"]).suffix.lower()
    input_path = storage.UPLOAD_DIR / f"{job_id}{suffix}"
    output_suffix = ".xlsx" if job["workflow"] == "validate_data" else suffix
    output_path = storage.OUTPUT_DIR / f"{job_id}{output_suffix}"
    storage.update_job(job_id, status="processing", updated_at=now())
    try:
        r2().download_file(object_key, str(input_path))
        metrics = process_job_from_paths(job, [input_path], output_path)
        result_key = f"results/{job_id}/result{output_suffix}"
        r2().upload_file(str(output_path), result_key,
                         "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" if output_suffix == ".xlsx" else "text/csv")
        storage.update_job(job_id, output_path=f"r2://{result_key}", status="completed",
                           error=None, result_metrics=json.dumps(metrics), updated_at=now())
    except Exception:
        storage.update_job(job_id, status="failed",
                           error="The uploaded file could not be processed. Check the workflow options and file contents, then try again.",
                           updated_at=now())
    finally:
        input_path.unlink(missing_ok=True)
        output_path.unlink(missing_ok=True)
