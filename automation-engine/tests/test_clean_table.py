from pathlib import Path

import pandas as pd
import pytest

from app.workflows.clean_table import run


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

    metrics = run(source, output)

    if suffix == ".csv":
        result = pd.read_csv(output)
    else:
        result = pd.read_excel(output, engine="openpyxl")

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

    run(source, output)

    assert output.suffix == suffix
    assert output.is_file()
