"""Application composition, usable without importing Qt."""

from dataclasses import dataclass
from pathlib import Path

from platformdirs import user_data_path

from exam_grader.storage import ExamStore


@dataclass(frozen=True)
class Application:
    data_dir: Path
    exams: ExamStore


def initialize(data_dir: Path | None = None) -> Application:
    directory = (
        (data_dir if data_dir is not None else user_data_path("ExamGrader", appauthor=False))
        .expanduser()
        .resolve()
    )
    store = ExamStore(directory / "exam-grader.sqlite3")
    store.initialize()
    return Application(directory, store)
