from pathlib import Path

import pandas as pd


def _read(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".csv":
        return pd.read_csv(path)
    if path.suffix.lower() == ".xlsx":
        return pd.read_excel(path, engine="openpyxl")
    raise ValueError("This workflow supports CSV and XLSX files.")


def _matches(series: pd.Series, operator: str, value) -> pd.Series:
    if operator == "eq": return series == value
    if operator == "ne": return series != value
    if operator == "gt": return series > value
    if operator == "gte": return series >= value
    if operator == "lt": return series < value
    if operator == "lte": return series <= value
    if operator == "contains": return series.astype("string").str.contains(str(value), case=False, na=False, regex=False)
    if operator == "is_null": return series.isna()
    if operator == "not_null": return series.notna()
    raise ValueError(f"Unsupported filter operator: {operator}")


def run(input_paths: list[Path], output_path: Path, options: dict | None = None) -> dict[str, int]:
    if len(input_paths) != 1:
        raise ValueError("The transform_data workflow requires exactly one file.")
    options = options or {}
    frame = _read(input_paths[0])
    original_rows = len(frame)

    renames = options.get("rename_columns", {})
    if not isinstance(renames, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in renames.items()):
        raise ValueError("rename_columns must be an object mapping existing names to new names.")
    missing = [name for name in renames if name not in frame.columns]
    if missing: raise ValueError(f"Columns to rename were not found: {missing}")
    frame = frame.rename(columns=renames)

    filters = options.get("filters", [])
    if not isinstance(filters, list): raise ValueError("filters must be a list.")
    for rule in filters:
        if not isinstance(rule, dict) or not {"column", "operator"}.issubset(rule):
            raise ValueError("Each filter requires column and operator.")
        column = rule["column"]
        if column not in frame.columns: raise ValueError(f"Filter column not found: {column}")
        frame = frame.loc[_matches(frame[column], rule["operator"], rule.get("value"))].copy()

    types = options.get("column_types", {})
    if not isinstance(types, dict): raise ValueError("column_types must be an object.")
    converters = {"string": lambda s: s.astype("string"), "integer": lambda s: pd.to_numeric(s, errors="raise").astype("Int64"),
                  "float": lambda s: pd.to_numeric(s, errors="raise"), "date": lambda s: pd.to_datetime(s, errors="raise"),
                  "boolean": lambda s: s.astype("boolean")}
    for column, kind in types.items():
        if column not in frame.columns: raise ValueError(f"Type conversion column not found: {column}")
        if kind not in converters: raise ValueError(f"Unsupported data type for {column}: {kind}")
        frame[column] = converters[kind](frame[column])

    calculations = options.get("calculated_columns", [])
    if not isinstance(calculations, list): raise ValueError("calculated_columns must be a list.")
    for calc in calculations:
        if not isinstance(calc, dict) or not {"name", "left", "operator", "right"}.issubset(calc):
            raise ValueError("Each calculated column requires name, left, operator, and right.")
        left, right, name, op = calc["left"], calc["right"], calc["name"], calc["operator"]
        if left not in frame.columns: raise ValueError(f"Calculated column source not found: {left}")
        lhs = pd.to_numeric(frame[left], errors="raise")
        rhs = pd.to_numeric(frame[right], errors="raise") if isinstance(right, str) and right in frame.columns else right
        if op == "add": result = lhs + rhs
        elif op == "subtract": result = lhs - rhs
        elif op == "multiply": result = lhs * rhs
        elif op == "divide": result = lhs / rhs
        else: raise ValueError(f"Unsupported calculation operator: {op}")
        frame[name] = result

    drop = options.get("drop_columns", [])
    if not isinstance(drop, list) or not all(isinstance(x, str) for x in drop): raise ValueError("drop_columns must be a list of column names.")
    absent = [name for name in drop if name not in frame.columns]
    if absent: raise ValueError(f"Columns to drop were not found: {absent}")
    frame = frame.drop(columns=drop)

    if output_path.suffix.lower() == ".csv": frame.to_csv(output_path, index=False)
    else: frame.to_excel(output_path, index=False, engine="openpyxl")
    return {"input_rows": int(original_rows), "output_rows": int(len(frame)), "output_columns": int(len(frame.columns))}
