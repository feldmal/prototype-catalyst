import re
from pathlib import Path

import pandas as pd


def _clean_column_name(value: object) -> str:
    name = str(value).strip().lower()
    name = re.sub(r"[^a-z0-9]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return name or "unnamed_column"


def _clean_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    cleaned_names = [_clean_column_name(column) for column in frame.columns]

    # Keep normalized column names unique if two original headers collapse
    # to the same snake_case name.
    seen: dict[str, int] = {}
    unique_names = []
    for name in cleaned_names:
        seen[name] = seen.get(name, 0) + 1
        unique_names.append(name if seen[name] == 1 else f"{name}_{seen[name]}")
    frame.columns = unique_names

    for column in frame.select_dtypes(include=["object", "string"]).columns:
        frame[column] = frame[column].map(
            lambda value: value.strip() if isinstance(value, str) else value
        )

    frame = frame.replace(r"^\s*$", pd.NA, regex=True)
    return frame.dropna(axis=0, how="all").dropna(axis=1, how="all")


def run(
    input_paths: list[Path],
    output_path: Path,
    cleanup: bool = False,
) -> dict[str, int]:
    if len(input_paths) < 2:
        raise ValueError("The combine_files workflow requires at least two files.")

    frames = []
    total_rows = 0
    for input_path in input_paths:
        suffix = input_path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(input_path, skip_blank_lines=False)
        elif suffix == ".xlsx":
            frame = pd.read_excel(input_path, engine="openpyxl")
        else:
            raise ValueError(f"Unsupported file type: {suffix}")
        total_rows += len(frame)
        frames.append(_clean_frame(frame) if cleanup else frame)

    combined = pd.concat(frames, ignore_index=True, sort=False)

    if output_path.suffix.lower() == ".csv":
        combined.to_csv(output_path, index=False)
    else:
        combined.to_excel(output_path, index=False, engine="openpyxl")

    return {
        "input_files": len(input_paths),
        "input_rows": int(total_rows),
        "output_rows": int(len(combined)),
        "output_columns": int(len(combined.columns)),
    }
