import re
from pathlib import Path

import pandas as pd


class EmptyInputFileError(ValueError):
    """Raised when a file has no usable data rows."""


class InvalidCsvStructureError(ValueError):
    """Raised when a CSV cannot be parsed into a consistent table."""


EMPTY_FILE_MESSAGE = (
    "EMPTY_FILE: This file contains no data rows. Upload a CSV or XLSX file "
    "with a header row and at least one data row."
)


def _clean_column_name(value: object) -> str:
    name = str(value).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed_column"


def run(input_path: Path, output_path: Path) -> dict[str, int]:
    suffix = input_path.suffix.lower()
    if suffix == ".csv":
        try:
            frame = pd.read_csv(input_path)
        except pd.errors.EmptyDataError:
            raise EmptyInputFileError(EMPTY_FILE_MESSAGE) from None
        except pd.errors.ParserError as exc:
            import re

            line_match = re.search(r"line\s+(\d+)", str(exc), re.IGNORECASE)
            row_hint = f" Check row {line_match.group(1)}" if line_match else ""
            message = (
                "INVALID_CSV: This CSV has an inconsistent structure."
                f"{row_hint} Look for extra commas or missing quotation marks, "
                "then upload the corrected file."
            )
            raise InvalidCsvStructureError(message) from None
    elif suffix == ".xlsx":
        try:
            frame = pd.read_excel(input_path, engine="openpyxl")
        except pd.errors.EmptyDataError:
            raise EmptyInputFileError(EMPTY_FILE_MESSAGE) from None
    else:
        raise ValueError("This workflow supports CSV and XLSX files.")

    if frame.empty:
        raise EmptyInputFileError(EMPTY_FILE_MESSAGE)

    original_rows, original_columns = frame.shape
    frame.columns = [_clean_column_name(column) for column in frame.columns]

    # Trim text first so whitespace-only cells become genuinely empty values.
    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )

    # Treat empty strings and whitespace-only strings as missing before dropping
    # fully empty rows and columns. This catches rows that contain only spaces.
    frame = frame.replace(r"^\s*$", pd.NA, regex=True)
    frame = frame.dropna(axis=0, how="all")
    if frame.empty:
        raise EmptyInputFileError(EMPTY_FILE_MESSAGE)
    frame = frame.dropna(axis=1, how="all")

    # Exact duplicate rows are removed by default after normalization.
    rows_before_deduplication = len(frame)
    frame = frame.drop_duplicates()
    duplicates_removed = rows_before_deduplication - len(frame)

    if suffix == ".csv":
        frame.to_csv(output_path, index=False)
    else:
        frame.to_excel(output_path, index=False, engine="openpyxl")

    return {
        "input_rows": int(original_rows),
        "output_rows": int(len(frame)),
        "input_columns": int(original_columns),
        "output_columns": int(len(frame.columns)),
        "duplicates_removed": int(duplicates_removed),
    }
