import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from sqlalchemy import (
    Column,
    Index,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    inspect,
    select,
    text,
    update,
)
from sqlalchemy.engine import Connection, Engine

DATA_DIR = Path(os.getenv("DATA_DIR", "data"))
DB_PATH = DATA_DIR / "jobs.sqlite3"
UPLOAD_DIR = DATA_DIR / "uploads"
OUTPUT_DIR = DATA_DIR / "outputs"

metadata = MetaData()

jobs = Table(
    "jobs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("workflow", String(100), nullable=False),
    Column("original_filename", String(500), nullable=False),
    Column("input_path", Text, nullable=False),
    Column("output_path", Text, nullable=True),
    Column("status", String(30), nullable=False),
    Column("error", Text, nullable=True),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
    Column("workflow_options", Text, nullable=False, server_default="{}"),
    Column("result_metrics", Text, nullable=False, server_default="{}"),
)
Index("idx_jobs_created", jobs.c.created_at)
Index("idx_jobs_status", jobs.c.status)

r2_upload_sessions = Table(
    "r2_upload_sessions",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("object_key", String(700), nullable=False, unique=True),
    Column("multipart_upload_id", String(300), nullable=False),
    Column("filename", String(500), nullable=False),
    Column("content_type", String(120), nullable=False),
    Column("expected_size", String(30), nullable=False),
    Column("part_size", String(30), nullable=False),
    Column("part_count", String(20), nullable=False),
    Column("workflow", String(100), nullable=False),
    Column("workflow_options", Text, nullable=False),
    Column("status", String(30), nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)

workflow_configs = Table(
    "workflow_configs",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("name", String(120), nullable=False),
    Column("workflow", String(100), nullable=False),
    Column("options", Text, nullable=False),
    Column("created_at", String(40), nullable=False),
    Column("updated_at", String(40), nullable=False),
)


def _database_url() -> str:
    configured = os.getenv("DATABASE_URL")
    if configured:
        return configured
    return f"sqlite:///{DB_PATH.resolve().as_posix()}"


def _create_engine() -> Engine:
    url = _database_url()
    options: dict[str, Any] = {"pool_pre_ping": True}
    if url.startswith("sqlite:"):
        options["connect_args"] = {"check_same_thread": False}
    return create_engine(url, **options)


@contextmanager
def _connect() -> Iterator[Connection]:
    engine = _create_engine()
    try:
        with engine.begin() as connection:
            yield connection
    finally:
        engine.dispose()


def initialize_storage() -> None:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    engine = _create_engine()
    try:
        metadata.create_all(engine)

        # Upgrade older SQLite databases created before options and metrics
        # were stored. The same additive ALTER statements also work in
        # PostgreSQL, so existing metadata is preserved during this change.
        existing_columns = {
            column["name"] for column in inspect(engine).get_columns("jobs")
        }
        with engine.begin() as connection:
            if "workflow_options" not in existing_columns:
                connection.execute(text(
                    "ALTER TABLE jobs ADD COLUMN workflow_options TEXT NOT NULL DEFAULT '{}'"
                ))
            if "result_metrics" not in existing_columns:
                connection.execute(text(
                    "ALTER TABLE jobs ADD COLUMN result_metrics TEXT NOT NULL DEFAULT '{}'"
                ))
    finally:
        engine.dispose()


def create_job(job: dict[str, Any]) -> None:
    values = {
        **job,
        "workflow_options": job.get("workflow_options", "{}"),
        "result_metrics": job.get("result_metrics", "{}"),
    }
    with _connect() as connection:
        connection.execute(jobs.insert().values(**values))


def update_job(job_id: str, **fields: Any) -> None:
    allowed = {"output_path", "status", "error", "updated_at", "result_metrics"}
    if not fields:
        return
    if not set(fields).issubset(allowed):
        raise ValueError("Unsupported job field update.")
    with _connect() as connection:
        connection.execute(
            update(jobs).where(jobs.c.id == job_id).values(**fields)
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            select(jobs).where(jobs.c.id == job_id)
        ).mappings().first()
        return dict(row) if row else None


def list_jobs(
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
    workflow: str | None = None,
) -> list[dict[str, Any]]:
    statement = select(jobs).order_by(jobs.c.created_at.desc()).limit(limit).offset(offset)
    if status:
        statement = statement.where(jobs.c.status == status)
    if workflow:
        statement = statement.where(jobs.c.workflow == workflow)
    with _connect() as connection:
        rows = connection.execute(statement).mappings().all()
        return [dict(row) for row in rows]


def create_workflow_config(config: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(workflow_configs.insert().values(**config))


def list_workflow_configs() -> list[dict[str, Any]]:
    with _connect() as connection:
        rows = connection.execute(
            select(workflow_configs).order_by(workflow_configs.c.created_at.desc())
        ).mappings().all()
        result = []
        for row in rows:
            item = dict(row)
            item["options"] = json.loads(item["options"])
            result.append(item)
        return result



def create_r2_upload_session(session: dict[str, Any]) -> None:
    with _connect() as connection:
        connection.execute(r2_upload_sessions.insert().values(**session))


def get_r2_upload_session(session_id: str) -> dict[str, Any] | None:
    with _connect() as connection:
        row = connection.execute(
            select(r2_upload_sessions).where(r2_upload_sessions.c.id == session_id)
        ).mappings().first()
        return dict(row) if row else None


def update_r2_upload_session(session_id: str, **fields: Any) -> None:
    allowed = {"status", "updated_at"}
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("Unsupported upload-session update.")
    with _connect() as connection:
        connection.execute(
            update(r2_upload_sessions)
            .where(r2_upload_sessions.c.id == session_id)
            .values(**fields)
        )
