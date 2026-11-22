from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.workflows import clean_table, combine_files


@dataclass(frozen=True)
class Workflow:
    name: str
    description: str
    min_files: int
    max_files: int
    run: Callable[[list[Path], Path], dict[str, int]]


def _run_clean_table(input_paths: list[Path], output_path: Path) -> dict[str, int]:
    if len(input_paths) != 1:
        raise ValueError("The clean_table workflow requires exactly one file.")
    return clean_table.run(input_paths[0], output_path)


WORKFLOWS = {
    "clean_table": Workflow(
        name="clean_table",
        description="Standardize headers, trim text, and remove empty rows and columns.",
        min_files=1,
        max_files=1,
        run=_run_clean_table,
    ),
    "combine_files": Workflow(
        name="combine_files",
        description="Append rows from multiple CSV and/or Excel files into one output.",
        min_files=2,
        max_files=10,
        run=combine_files.run,
    ),
}


def get_workflow(name: str) -> Workflow | None:
    return WORKFLOWS.get(name)
