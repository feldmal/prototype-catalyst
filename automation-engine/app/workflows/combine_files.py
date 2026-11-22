from pathlib import Path

import pandas as pd


def run(input_paths: list[Path], output_path: Path) -> dict[str, int]:
    if len(input_paths) < 2:
        raise ValueError("The combine_files workflow requires at least two files.")

    frames = []
    total_rows = 0
    for input_path in input_paths:
        suffix = input_path.suffix.lower()
        if suffix == ".csv":
            frame = pd.read_csv(input_path)
        elif suffix == ".xlsx":
            frame = pd.read_excel(input_path, engine="openpyxl")
        else:
            raise ValueError(f"Unsupported file type: {suffix}")
        total_rows += len(frame)
        frames.append(frame)

    # Append rows and align columns by their existing header names.
    combined = pd.concat(frames, ignore_index=True, sort=False)

    # Use Excel output when inputs are mixed or any input is an Excel workbook;
    # otherwise keep the compact CSV format.
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
