from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.workflows import aggregate_data, clean_table, combine_files, transform_data, validate_data


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    min_files: int
    max_files: int
    run: Callable[..., dict[str, int]]
    output_format: str = "input"


def _one_file(module):
    def runner(input_paths: list[Path], output_path: Path, options: dict | None = None):
        if len(input_paths) != 1:
            raise ValueError(f"The {module.__name__.split('.')[-1]} workflow requires exactly one file.")
        return module.run(input_paths, output_path, options or {})
    return runner


def _run_clean_table(input_paths: list[Path], output_path: Path, options: dict | None = None):
    if len(input_paths) != 1:
        raise ValueError("The clean_table workflow requires exactly one file.")
    return clean_table.run(input_paths[0], output_path)


def _run_combine_files(input_paths: list[Path], output_path: Path, options: dict | None = None):
    options = options or {}
    return combine_files.run(input_paths, output_path, cleanup=bool(options.get("cleanup", False)))


WORKFLOWS = {
    "clean_table": Workflow("clean_table", "Standardize headers, trim text, and remove empty rows and columns.", 1, 1, _run_clean_table),
    "combine_files": Workflow("combine_files", "Append rows from multiple CSV/XLSX files, optionally cleaning them first.", 2, 10, _run_combine_files),
    "validate_data": Workflow("validate_data", "Profile a file and report missing values, duplicates, and configured invalid values without changing source data.", 1, 1, _one_file(validate_data), "xlsx"),
    "transform_data": Workflow("transform_data", "Rename, filter, convert, calculate, and remove columns using a reusable configuration.", 1, 1, _one_file(transform_data)),
    "aggregate_data": Workflow("aggregate_data", "Group records and calculate business summaries such as totals, averages, and counts.", 1, 1, _one_file(aggregate_data)),
}


def get_workflow(name: str) -> Workflow | None:
    return WORKFLOWS.get(name)
