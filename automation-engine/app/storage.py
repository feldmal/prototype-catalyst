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
                id TEXT PRIMARY KEY,
                workflow TEXT NOT NULL,
                original_filename TEXT NOT NULL,
                input_path TEXT NOT NULL,
                output_path TEXT,
                status TEXT NOT NULL,
                error TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                workflow_options TEXT NOT NULL DEFAULT '{}'
            )
        """)
        # Upgrade existing local databases without deleting prior job history.
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "workflow_options" not in columns:
            connection.execute(
                "ALTER TABLE jobs ADD COLUMN workflow_options TEXT NOT NULL DEFAULT '{}'"
            )
        connection.commit()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def create_job(job: dict[str, Any]) -> None:
    job = {**job, "workflow_options": job.get("workflow_options", "{}")}
    with _connect() as connection:
        connection.execute("""
            INSERT INTO jobs
            (id, workflow, original_filename, input_path, output_path, status, error,
             created_at, updated_at, workflow_options)
            VALUES (:id, :workflow, :original_filename, :input_path, :output_path,
                    :status, :error, :created_at, :updated_at, :workflow_options)
        """, job)
        connection.commit()


def update_job(job_id: str, **fields: Any) -> None:
    if not fields:
        return
    assignments = ", ".join(f"{key} = ?" for key in fields)
    values = list(fields.values()) + [job_id]
    with _connect() as connection:
        connection.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", values)
        connection.commit()


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
