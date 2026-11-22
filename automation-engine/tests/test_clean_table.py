from pathlib import Path

import pandas as pd

from app.workflows.clean_table import run


def test_clean_table_normalizes_headers_and_trims_values(tmp_path: Path):
    source = tmp_path / "source.csv"
    output = tmp_path / "output.csv"
    source.write_text(" Customer Name , Order Date , Amount \n Alice ,2026-01-01,10\n,,\n", encoding="utf-8")

    metrics = run(source, output)
    result = pd.read_csv(output)

    assert list(result.columns) == ["customer_name", "order_date", "amount"]
    assert result.loc[0, "customer_name"] == "Alice"
    assert metrics["input_rows"] == 2
    assert metrics["output_rows"] == 1


def test_clean_table_excel_round_trip(tmp_path: Path):
    source = tmp_path / "source.xlsx"
    output = tmp_path / "output.xlsx"
    pd.DataFrame({" Customer Name ": [" Bob "], " Amount ": [12]}).to_excel(source, index=False)

    run(source, output)
    result = pd.read_excel(output)

    assert list(result.columns) == ["customer_name", "amount"]
    assert result.loc[0, "customer_name"] == "Bob"
