from pathlib import Path

import pandas as pd


def run(input_paths: list[Path], output_path: Path, options: dict | None = None) -> dict[str, int]:
    if len(input_paths) != 1:
        raise ValueError("The aggregate_data workflow requires exactly one file.")
    options = options or {}
    path = input_paths[0]
    frame = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path, engine="openpyxl")
    group_by = options.get("group_by", [])
    aggregations = options.get("aggregations", {})
    if not isinstance(group_by, list) or not group_by or not all(isinstance(x, str) for x in group_by):
        raise ValueError("group_by must be a non-empty list of column names.")
    if not isinstance(aggregations, dict) or not aggregations:
        raise ValueError("aggregations must map column names to aggregation functions.")
    missing = [x for x in group_by if x not in frame.columns]
    missing += [x for x in aggregations if x not in frame.columns]
    if missing: raise ValueError(f"Aggregation columns not found: {sorted(set(missing))}")
    allowed = {"sum", "mean", "count", "min", "max", "nunique"}
    for column, funcs in aggregations.items():
        funcs = [funcs] if isinstance(funcs, str) else funcs
        if not isinstance(funcs, list) or not funcs or any(func not in allowed for func in funcs):
            raise ValueError(f"Unsupported aggregation for {column}. Use sum, mean, count, min, max, or nunique.")
        aggregations[column] = funcs
    result = frame.groupby(group_by, dropna=False).agg(aggregations)
    result.columns = [f"{column}_{func}" for column, func in result.columns]
    result = result.reset_index()
    if output_path.suffix.lower() == ".csv": result.to_csv(output_path, index=False)
    else: result.to_excel(output_path, index=False, engine="openpyxl")
    return {"input_rows": int(len(frame)), "output_rows": int(len(result)), "output_columns": int(len(result.columns))}
