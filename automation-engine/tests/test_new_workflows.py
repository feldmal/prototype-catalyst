from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app
from app.workflows.aggregate_data import run as aggregate
from app.workflows.transform_data import run as transform
from app.workflows.validate_data import run as validate


def test_validation_report_does_not_modify_source_and_finds_issues(tmp_path: Path):
    source, output = tmp_path / "source.csv", tmp_path / "report.xlsx"
    pd.DataFrame({"id": [1, 1, 1, 3], "amount": ["10", "bad", "bad", None], "date": ["2026-01-01", "bad", "bad", "2026-01-03"]}).to_csv(source, index=False)
    before = source.read_bytes()
    metrics = validate([source], output, {"required_columns": ["id", "amount"], "numeric_columns": ["amount"], "date_columns": ["date"]})
    report = pd.read_excel(output, sheet_name="Issues")
    assert source.read_bytes() == before
    assert metrics["input_rows"] == 4
    assert metrics["issues_found"] >= 4
    assert "Invalid number" in report["issue"].tolist()
    assert "Invalid date" in report["issue"].tolist()
    assert "Duplicate row" in report["issue"].tolist()


def test_transform_applies_rename_filter_types_calculation_and_drop(tmp_path: Path):
    source, output = tmp_path / "source.csv", tmp_path / "result.csv"
    pd.DataFrame({"Customer": ["A", "B", "C"], "Qty": ["2", "4", "1"], "Price": [5, 3, 9], "Unused": [1, 2, 3]}).to_csv(source, index=False)
    metrics = transform([source], output, {
        "rename_columns": {"Customer": "customer"},
        "filters": [{"column": "Qty", "operator": "gte", "value": 2}],
        "column_types": {"Qty": "integer"},
        "calculated_columns": [{"name": "total", "left": "Qty", "operator": "multiply", "right": "Price"}],
        "drop_columns": ["Unused"],
    })
    result = pd.read_csv(output)
    assert result["customer"].tolist() == ["A", "B"]
    assert result["total"].tolist() == [10, 12]
    assert "Unused" not in result.columns
    assert metrics == {"input_rows": 3, "output_rows": 2, "output_columns": 4}


def test_transform_rejects_unsafe_or_unknown_operator(tmp_path: Path):
    source, output = tmp_path / "source.csv", tmp_path / "result.csv"
    pd.DataFrame({"x": [1]}).to_csv(source, index=False)
    with pytest.raises(ValueError, match="Unsupported filter operator"):
        transform([source], output, {"filters": [{"column": "x", "operator": "eval", "value": "1"}]})


def test_aggregate_groups_and_calculates_multiple_metrics(tmp_path: Path):
    source, output = tmp_path / "source.csv", tmp_path / "summary.xlsx"
    pd.DataFrame({"region": ["West", "West", "East"], "sales": [10, 20, 7], "order": [1, 2, 3]}).to_csv(source, index=False)
    metrics = aggregate([source], output, {"group_by": ["region"], "aggregations": {"sales": ["sum", "mean"], "order": "count"}})
    result = pd.read_excel(output).set_index("region")
    assert result.loc["West", "sales_sum"] == 30
    assert result.loc["West", "sales_mean"] == 15
    assert result.loc["East", "order_count"] == 1
    assert metrics["output_rows"] == 2


def test_api_lists_jobs_and_saves_reusable_workflow_config(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "data" / "jobs.sqlite3")
    monkeypatch.setattr(storage, "UPLOAD_DIR", tmp_path / "data" / "uploads")
    monkeypatch.setattr(storage, "OUTPUT_DIR", tmp_path / "data" / "outputs")
    with TestClient(app) as client:
        saved = client.post("/workflow-configs", data={
            "name": "Monthly sales totals", "workflow": "aggregate_data",
            "options_json": '{"group_by":["region"],"aggregations":{"sales":"sum"}}'
        })
        assert saved.status_code == 201
        assert saved.json()["config"]["options"]["group_by"] == ["region"]
        configs = client.get("/workflow-configs")
        assert len(configs.json()["configs"]) == 1
        jobs = client.get("/jobs")
        assert jobs.status_code == 200
        assert jobs.json()["jobs"] == []
        assert client.get("/workflows").json()["workflows"][-1]["name"] == "aggregate_data"
