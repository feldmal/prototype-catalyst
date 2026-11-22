import re
from pathlib import Path

import pandas as pd


def _clean_column_name(value: object) -> str:
    name = str(value).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed_column"


def run(input_path: Path, output_path: Path) -> dict[str, int]:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        frame = pd.read_csv(input_path)
    elif suffix == ".xlsx":
        frame = pd.read_excel(input_path, engine="openpyxl")
    else:
        raise ValueError("This workflow supports CSV and XLSX files.")

    original_rows, original_columns = frame.shape
    frame.columns = [_clean_column_name(column) for column in frame.columns]

    # Keep only rows/columns that contain at least one non-empty value.
    frame = frame.dropna(axis=0, how="all").dropna(axis=1, how="all")

    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )

    if suffix == ".csv":
        frame.to_csv(output_path, index=False)
    else:
        frame.to_excel(output_path, index=False, engine="openpyxl")

    return {
        "input_rows": int(original_rows),
        "output_rows": int(len(frame)),
        "input_columns": int(original_columns),
        "output_columns": int(len(frame.columns)),
    }
