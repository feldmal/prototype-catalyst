from pathlib import Path

import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")
    raise ValueError("This workflow supports CSV and XLSX files.")


def run(input_paths: list[Path], output_path: Path, options: dict | None = None) -> dict[str, int]:
    if len(input_paths) != 1:
        raise ValueError("The validate_data workflow requires exactly one file.")
    options = options or {}
    frame = _read(input_paths[0])
    issues: list[dict] = []

    required_columns = options.get("required_columns", [])
    if not isinstance(required_columns, list) or not all(isinstance(x, str) for x in required_columns):
        raise ValueError("required_columns must be a list of column names.")
    for column in required_columns:
        if column not in frame.columns:
            issues.append({"row": None, "column": column, "issue": "Required column is missing", "value": None})

    for column in frame.columns:
        missing_count = int(frame[column].isna().sum())
        if missing_count:
            issues.append({"row": None, "column": str(column), "issue": f"Missing values ({missing_count})", "value": None})

    if options.get("check_duplicates", True):
        duplicate_mask = frame.duplicated(keep=False)
        for index in frame.index[duplicate_mask]:
            issues.append({"row": int(index) + 2, "column": None, "issue": "Duplicate row", "value": None})

    date_columns = options.get("date_columns", [])
    numeric_columns = options.get("numeric_columns", [])
    for key, columns in (("date_columns", date_columns), ("numeric_columns", numeric_columns)):
        if not isinstance(columns, list) or not all(isinstance(x, str) for x in columns):
            raise ValueError(f"{key} must be a list of column names.")
    for column in date_columns:
        if column not in frame.columns:
            issues.append({"row": None, "column": column, "issue": "Configured date column not found", "value": None})
            continue
        parsed = pd.to_datetime(frame[column], errors="coerce")
        invalid = frame[column].notna() & parsed.isna()
        for index in frame.index[invalid]:
            issues.append({"row": int(index) + 2, "column": column, "issue": "Invalid date", "value": str(frame.at[index, column])})
    for column in numeric_columns:
        if column not in frame.columns:
            issues.append({"row": None, "column": column, "issue": "Configured numeric column not found", "value": None})
            continue
        parsed = pd.to_numeric(frame[column], errors="coerce")
        invalid = frame[column].notna() & parsed.isna()
        for index in frame.index[invalid]:
            issues.append({"row": int(index) + 2, "column": column, "issue": "Invalid number", "value": str(frame.at[index, column])})

    issue_frame = pd.DataFrame(issues, columns=["row", "column", "issue", "value"])
    summary = pd.DataFrame([
        {"metric": "Rows checked", "value": len(frame)},
        {"metric": "Columns checked", "value": len(frame.columns)},
        {"metric": "Issues found", "value": len(issues)},
        {"metric": "Duplicate rows", "value": int(frame.duplicated(keep=False).sum()) if options.get("check_duplicates", True) else 0},
    ])
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Summary", index=False)
        issue_frame.to_excel(writer, sheet_name="Issues", index=False)
    return {"input_rows": int(len(frame)), "input_columns": int(len(frame.columns)), "issues_found": len(issues)}
