import json
import os
import sqlite3
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "jobs.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"


def initialize_storage() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, workflow TEXT NOT NULL, original_filename TEXT NOT NULL,
                input_path TEXT NOT NULL, output_path TEXT, status TEXT NOT NULL, error TEXT,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                workflow_options TEXT NOT NULL DEFAULT '{}', result_metrics TEXT NOT NULL DEFAULT '{}'
            )
        """)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()}
        if "workflow_options" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN workflow_options TEXT NOT NULL DEFAULT '{}'")
        if "result_metrics" not in columns:
            connection.execute("ALTER TABLE jobs ADD COLUMN result_metrics TEXT NOT NULL DEFAULT '{}'")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at DESC)")
        connection.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        connection.execute("""
            CREATE TABLE IF NOT EXISTS workflow_configs (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, workflow TEXT NOT NULL,
                options TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            )
        """)
        connection.commit()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_job(job: dict[str, Any]) -> None:
    job = {**job, "workflow_options": job.get("workflow_options", "{}"), "result_metrics": job.get("result_metrics", "{}")}
    with _connect() as connection:
        connection.execute("""
            INSERT INTO jobs
            (id, workflow, original_filename, input_path, output_path, status, error,
             created_at, updated_at, workflow_options, result_metrics)
            VALUES (:id, :workflow, :original_filename, :input_path, :output_path,
                    :status, :error, :created_at, :updated_at, :workflow_options, :result_metrics)
        """, job)
        connection.commit()


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"output_path", "status", "error", "updated_at", "result_metrics"}
    if not fields:
        return
    if not set(fields).issubset(allowed):
        raise ValueError("Unsupported job field update.")
    assignments = ", ".join(f"{key} = ?" for key in fields)
    with _connect() as connection:
        connection.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", list(fields.values()) + [job_id])
        connection.commit()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def list_jobs(limit: int = 50, offset: int = 0, status: str | None = None, workflow: str | None = None) -> list[dict[str, Any]]:
    clauses, params = [], []
    if status:
        clauses.append("status = ?"); params.append(status)
    if workflow:
        clauses.append("workflow = ?"); params.append(workflow)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with _connect() as connection:
        rows = connection.execute(
            f"SELECT * FROM jobs{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [dict(row) for row in rows]


def create_workflow_config(config: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute("""
            INSERT INTO workflow_configs (id, name, workflow, options, created_at, updated_at)
            VALUES (:id, :name, :workflow, :options, :created_at, :updated_at)
        """, config)
        connection.commit()


def list_workflow_configs() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute("SELECT * FROM workflow_configs ORDER BY created_at DESC").fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["options"] = json.loads(item["options"])
            result.append(item)
        return result
