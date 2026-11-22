from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient

from app import storage
from app.main import app
from app.workflows.combine_files import run


def _write(path: Path, frame: pd.DataFrame) -> None:
    if path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        frame.to_excel(path, index=False, engine="openpyxl")


def test_cleanup_option_normalizes_headers_and_removes_blank_rows_columns(tmp_path: Path):
    first, second, output = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "out.csv"
    _write(first, pd.DataFrame({" Customer Name ": [" Acme ", "   "], " Amount ": [10, None], " Empty Column ": [" ", " "]}))
    _write(second, pd.DataFrame({" Customer Name ": [" Northwind "], " Amount ": [20], " Empty Column ": [" "]}))

    run([first, second], output, cleanup=True)
    result = pd.read_csv(output)
    assert list(result.columns) == ["customer_name", "amount"]
    assert result["customer_name"].tolist() == ["Acme", "Northwind"]
    assert result["amount"].tolist() == [10, 20]


def test_cleanup_off_preserves_source_headers_and_whitespace(tmp_path: Path):
    first, second, output = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "out.csv"
    _write(first, pd.DataFrame({" Customer ": [" Acme ", "   "]}))
    _write(second, pd.DataFrame({" Customer ": [" Northwind "]}))

    run([first, second], output, cleanup=False)
    result = pd.read_csv(output, keep_default_na=False)
    assert list(result.columns) == [" Customer "]
    assert result.iloc[:, 0].tolist() == [" Acme ", "   ", " Northwind "]


def test_cleanup_handles_duplicate_normalized_headers(tmp_path: Path):
    first, second, output = tmp_path / "a.csv", tmp_path / "b.csv", tmp_path / "out.csv"
    _write(first, pd.DataFrame({"Customer Name": ["A"], "Customer-Name": ["A2"]}))
    _write(second, pd.DataFrame({"Customer Name": ["B"], "Customer-Name": ["B2"]}))

    run([first, second], output, cleanup=True)
    result = pd.read_csv(output)
    assert list(result.columns) == ["customer_name", "customer_name_2"]
    assert result["customer_name"].tolist() == ["A", "B"]
    assert result["customer_name_2"].tolist() == ["A2", "B2"]


def test_cleanup_option_handles_mixed_csv_and_excel(tmp_path: Path):
    first, second, output = tmp_path / "a.csv", tmp_path / "b.xlsx", tmp_path / "out.xlsx"
    _write(first, pd.DataFrame({" Item Name ": [" A "], " Qty ": [2]}))
    _write(second, pd.DataFrame({" Item Name ": [" B "], " Qty ": [3]}))

    run([first, second], output, cleanup=True)
    result = pd.read_excel(output)
    assert list(result.columns) == ["item_name", "qty"]
    assert result["item_name"].tolist() == ["A", "B"]


def test_api_accepts_cleanup_option_and_downloads_cleaned_output(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "jobs.sqlite3")
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path / "data" / "outputs")

    first = b" Customer Name , Amount , Empty Column \n Acme ,10, \n   ,, \n"
    second = b" Customer Name , Amount , Empty Column \n Northwind ,20, \n"
    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            data={"workflow": "combine_files", "cleanup": "true"},
            files=[
                ("files", ("first.csv", first, "text/csv")),
                ("files", ("second.csv", second, "text/csv")),
            ],
        )
        assert response.status_code == 202
        submitted_job = response.json()["job"]
        assert submitted_job["status"] == "queued"
        job_response = client.get(f"/jobs/{submitted_job['id']}")
        assert job_response.status_code == 200
        job = job_response.json()["job"]
        assert job["status"] == "completed"
        assert job["options"] == {"cleanup": True}
        download = client.get(job["download_url"])
        assert download.status_code == 200
        output = tmp_path / "download.csv"
        output.write_bytes(download.content)
        result = pd.read_csv(output)
        assert list(result.columns) == ["customer_name", "amount"]
        assert result["customer_name"].tolist() == ["Acme", "Northwind"]


def test_api_rejects_cleanup_option_for_clean_table(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "jobs.sqlite3")
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path / "data" / "outputs")

    with TestClient(app) as client:
        response = client.post(
            "/jobs",
            data={"workflow": "clean_table", "cleanup": "true"},
            files=[("files", ("one.csv", b"Name\nA\n", "text/csv"))],
        )
        assert response.status_code == 400
        assert "only available for combine_files" in response.json()["detail"]
