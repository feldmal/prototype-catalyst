from pathlib import Path

import pandas as pd
import pytest

from app.workflows.clean_table import run as run_clean_table
from app.workflows.combine_files import run as run_combine_files
from app.workflows.registry import get_workflow


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_clean_table_removes_empty_and_whitespace_only_rows_and_columns(
    tmp_path: Path, suffix: str
):
    source = tmp_path / f"source{suffix}"
    output = tmp_path / f"output{suffix}"

    frame = pd.DataFrame(
        {
            " Customer Name ": [" Alice ", "   ", None, " Bob "],
            " Amount ": [10, None, None, 20],
            " Empty Column ": ["   ", "   ", None, " "],
        }
    )
    if suffix == ".csv":
        frame.to_csv(source, index=False)
    else:
        frame.to_excel(source, index=False, engine="openpyxl")

    metrics = run_clean_table(source, output)

    result = pd.read_csv(output) if suffix == ".csv" else pd.read_excel(output)
    assert output.is_file()
    assert list(result.columns) == ["customer_name", "amount"]
    assert result["customer_name"].tolist() == ["Alice", "Bob"]
    assert result["amount"].tolist() == [10, 20]
    assert metrics == {
        "input_rows": 4,
        "output_rows": 2,
        "input_columns": 3,
        "output_columns": 2,
    }


@pytest.mark.parametrize("suffix", [".csv", ".xlsx"])
def test_clean_table_preserves_file_format(tmp_path: Path, suffix: str):
    source = tmp_path / f"source{suffix}"
    output = tmp_path / f"cleaned{suffix}"
    frame = pd.DataFrame({" Name ": [" Taylor "], " Total ": [42]})

    if suffix == ".csv":
        frame.to_csv(source, index=False)
    else:
        frame.to_excel(source, index=False, engine="openpyxl")

    run_clean_table(source, output)

    assert output.suffix == suffix
    assert output.is_file()


def test_combine_csv_files_appends_rows_and_unions_columns(tmp_path: Path):
    first = tmp_path / "january.csv"
    second = tmp_path / "february.csv"
    output = tmp_path / "combined.csv"

    pd.DataFrame({"Customer": ["Acme"], "Amount": [100]}).to_csv(first, index=False)
    pd.DataFrame({"Customer": ["Northwind"], "Region": ["West"]}).to_csv(second, index=False)

    metrics = run_combine_files([first, second], output)
    result = pd.read_csv(output)

    assert result["Customer"].tolist() == ["Acme", "Northwind"]
    assert result.loc[0, "Amount"] == 100
    assert pd.isna(result.loc[1, "Amount"])
    assert pd.isna(result.loc[0, "Region"])
    assert result.loc[1, "Region"] == "West"
    assert metrics == {
        "input_files": 2,
        "input_rows": 2,
        "output_rows": 2,
        "output_columns": 3,
    }


def test_combine_mixed_csv_and_excel_outputs_xlsx(tmp_path: Path):
    csv_path = tmp_path / "part_a.csv"
    xlsx_path = tmp_path / "part_b.xlsx"
    output = tmp_path / "combined.xlsx"

    pd.DataFrame({"Item": ["A"], "Qty": [2]}).to_csv(csv_path, index=False)
    pd.DataFrame({"Item": ["B"], "Qty": [3]}).to_excel(xlsx_path, index=False)

    run_combine_files([csv_path, xlsx_path], output)
    result = pd.read_excel(output)

    assert output.is_file()
    assert result["Item"].tolist() == ["A", "B"]
    assert result["Qty"].tolist() == [2, 3]


def test_combine_requires_at_least_two_files(tmp_path: Path):
    source = tmp_path / "single.csv"
    output = tmp_path / "combined.csv"
    pd.DataFrame({"Item": ["A"]}).to_csv(source, index=False)

    with pytest.raises(ValueError, match="at least two"):
        run_combine_files([source], output)


def test_workflow_registry_exposes_both_workflows():
    assert get_workflow("clean_table").max_files == 1
    assert get_workflow("combine_files").min_files == 2
    assert get_workflow("combine_files").max_files == 10
    assert get_workflow("not_a_workflow") is None
