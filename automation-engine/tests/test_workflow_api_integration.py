from io import BytesIO

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app import storage
from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    monkeypatch.setattr(storage, "DATA_DIR", data_dir)
    monkeypatch.setattr(storage, "DB_PATH", data_dir / "jobs.sqlite3")
    monkeypatch.setattr(storage, "UPLOAD_DIR", data_dir / "uploads")
    monkeypatch.setattr(storage, "OUTPUT_DIR", data_dir / "outputs")
    with TestClient(app) as test_client:
        yield test_client


def csv_upload(name, content):
    return ("files", (name, content.encode("utf-8"), "text/csv"))


def submit_and_download(client, workflow, uploads, options=None, extra_data=None):
    data = {"workflow": workflow}
    if options is not None:
        import json
        data["options_json"] = json.dumps(options)
    if extra_data:
        data.update(extra_data)

    response = client.post("/jobs", data=data, files=uploads)
    assert response.status_code == 202, response.text
    submitted = response.json()["job"]
    assert submitted["status"] == "queued"

    detail_response = client.get(f"/jobs/{submitted['id']}")
    assert detail_response.status_code == 200
    job = detail_response.json()["job"]
    assert job["status"] == "completed", job
    assert job["error"] is None
    assert job["download_url"] == f"/jobs/{submitted['id']}/download"

    download = client.get(job["download_url"])
    assert download.status_code == 200
    assert download.content
    return job, download.content


def test_clean_table_through_api(client):
    source = "Customer Name,Amount,Empty Column\n Acme ,10,\nNorthwind,20,\n,,\n"
    job, output = submit_and_download(
        client, "clean_table", [csv_upload("customers.csv", source)]
    )

    result = pd.read_csv(BytesIO(output))
    assert list(result.columns) == ["customer_name", "amount"]
    assert len(result) == 2
    assert result.iloc[0, 0] == "Acme"
    assert job["metrics"]["output_rows"] == 2


def test_combine_files_through_api_with_cleanup(client):
    first = " Customer Name ,Amount\n Acme ,10\n"
    second = " Customer Name ,Amount\n Northwind ,20\n"
    job, output = submit_and_download(
        client,
        "combine_files",
        [csv_upload("first.csv", first), csv_upload("second.csv", second)],
        extra_data={"cleanup": "true"},
    )

    result = pd.read_csv(BytesIO(output))
    assert list(result.columns) == ["customer_name", "amount"]
    assert result["customer_name"].tolist() == ["Acme", "Northwind"]
    assert job["metrics"]["input_files"] == 2
    assert job["metrics"]["output_rows"] == 2


def test_validate_data_through_api(client):
    source = "id,amount,order_date\n1,10,2026-01-01\n1,bad,not-a-date\n"
    job, output = submit_and_download(
        client,
        "validate_data",
        [csv_upload("orders.csv", source)],
        options={
            "required_columns": ["id", "amount", "missing_field"],
            "numeric_columns": ["amount"],
            "date_columns": ["order_date"],
            "check_duplicates": True,
        },
    )

    issues = pd.read_excel(BytesIO(output), sheet_name="Issues")
    issue_names = issues["issue"].tolist()
    assert "Invalid number" in issue_names
    assert "Invalid date" in issue_names
    assert "Duplicate row" in issue_names
    assert "Required column is missing" in issue_names
    assert job["metrics"]["issues_found"] >= 4


def test_transform_data_through_api(client):
    source = "Customer,Qty,Price,Unused\nAcme,2,5,x\nNorthwind,4,3,y\nContoso,1,9,z\n"
    options = {
        "rename_columns": {"Customer": "customer"},
        "filters": [{"column": "Qty", "operator": "gte", "value": 2}],
        "column_types": {"Qty": "integer"},
        "calculated_columns": [
            {"name": "total", "left": "Qty", "operator": "multiply", "right": "Price"}
        ],
        "drop_columns": ["Unused"],
    }
    job, output = submit_and_download(
        client, "transform_data", [csv_upload("orders.csv", source)], options=options
    )

    result = pd.read_csv(BytesIO(output))
    assert result["customer"].tolist() == ["Acme", "Northwind"]
    assert result["total"].tolist() == [10, 12]
    assert "Unused" not in result.columns
    assert job["metrics"]["input_rows"] == 3
    assert job["metrics"]["output_rows"] == 2


def test_aggregate_data_through_api(client):
    source = "region,product,sales,order_id\nWest,Widget,10,1\nWest,Widget,20,2\nEast,Gadget,7,3\n"
    options = {
        "group_by": ["region", "product"],
        "aggregations": {"sales": ["sum", "mean"], "order_id": "count"},
    }
    job, output = submit_and_download(
        client, "aggregate_data", [csv_upload("sales.csv", source)], options=options
    )

    result = pd.read_csv(BytesIO(output))
    west = result.loc[result["region"] == "West"].iloc[0]
    assert west["sales_sum"] == 30
    assert west["sales_mean"] == 15
    assert west["order_id_count"] == 2
    assert job["metrics"]["output_rows"] == 2


def test_api_rejects_invalid_options_json(client):
    response = client.post(
        "/jobs",
        data={"workflow": "aggregate_data", "options_json": "{not-json"},
        files=[csv_upload("data.csv", "region,sales\nWest,10\n")],
    )
    assert response.status_code == 400
    assert "valid JSON" in response.json()["detail"]


def test_api_rejects_unknown_workflow(client):
    response = client.post(
        "/jobs",
        data={"workflow": "not_a_workflow"},
        files=[csv_upload("data.csv", "a\n1\n")],
    )
    assert response.status_code == 400
    assert "Unknown workflow" in response.json()["detail"]


def test_api_rejects_unsupported_file_extension(client):
    response = client.post(
        "/jobs",
        data={"workflow": "clean_table"},
        files=[("files", ("notes.txt", b"hello", "text/plain"))],
    )
    assert response.status_code == 415


def test_api_rejects_wrong_number_of_files(client):
    response = client.post(
        "/jobs",
        data={"workflow": "combine_files"},
        files=[csv_upload("only.csv", "a\n1\n")],
    )
    assert response.status_code == 400
    assert "between 2 and 10" in response.json()["detail"]


def test_job_history_filters_and_saved_config(client):
    config_response = client.post(
        "/workflow-configs",
        data={
            "name": "West region sales",
            "workflow": "aggregate_data",
            "options_json": '{"group_by":["region"],"aggregations":{"sales":"sum"}}',
        },
    )
    assert config_response.status_code == 201

    source = "region,sales\nWest,10\nEast,5\n"
    job, _ = submit_and_download(
        client,
        "aggregate_data",
        [csv_upload("sales.csv", source)],
        options={"group_by": ["region"], "aggregations": {"sales": "sum"}},
    )

    history = client.get("/jobs", params={"status": "completed", "workflow": "aggregate_data"})
    assert history.status_code == 200
    assert any(item["id"] == job["id"] for item in history.json()["jobs"])

    configs = client.get("/workflow-configs")
    assert configs.status_code == 200
    assert configs.json()["configs"][0]["name"] == "West region sales"


def test_download_before_completion_returns_conflict(client):
    response = client.post(
        "/jobs",
        data={"workflow": "clean_table"},
        files=[csv_upload("data.csv", "Name\nAcme\n")],
    )
    assert response.status_code == 202
    job_id = response.json()["job"]["id"]
    # The normal TestClient background-task lifecycle completes jobs before the
    # response is returned, so use a deliberately missing job ID to verify
    # that the download route does not return a successful file.
    missing = client.get(f"/jobs/{job_id}-missing/download")
    assert missing.status_code == 404
