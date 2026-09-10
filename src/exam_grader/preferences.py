"""Small cross-platform UI preferences backed by QSettings."""

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths


def default_output_root() -> Path:
    settings = QSettings("ExamGrader", "ExamGrader")
    configured = str(settings.value("output_root", "", type=str) or "").strip()
    if configured:
        return Path(configured).expanduser()
    documents = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    return Path(documents or Path.home() / "Documents") / "ExamGrader"


def save_output_root(path: Path) -> None:
    QSettings("ExamGrader", "ExamGrader").setValue("output_root", str(path.expanduser().resolve()))
