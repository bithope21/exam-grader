import argparse
import json
import sqlite3
import sys
from pathlib import Path

from exam_grader import __version__
from exam_grader.app import initialize


def main() -> int:
    parser = argparse.ArgumentParser(description="Exam Grader desktop foundation")
    parser.add_argument("--data-dir", type=Path, help="Override application data directory")
    parser.add_argument(
        "--self-check", action="store_true", help="Initialize/check storage without GUI"
    )
    parser.add_argument("--smoke-ui", action="store_true", help="Open and close the UI for build verification")
    parser.add_argument("--report", type=Path, help="Write self-check JSON to this path")
    args = parser.parse_args()
    try:
        application = initialize(args.data_dir)
        exams = application.exams.list_exams()
        from exam_grader.diagnostics import runtime_health
        health = runtime_health()
    except (OSError, sqlite3.Error, RuntimeError, ValueError, ImportError) as error:
        if args.self_check:
            print(f"Startup failed: {error}", file=sys.stderr)
        else:
            from PySide6.QtWidgets import QApplication, QMessageBox

            qt = QApplication(sys.argv[:1])
            QMessageBox.critical(None, "เปิดโปรแกรมไม่ได้", f"ไม่สามารถเปิดข้อมูลได้\n{error}")
        return 1
    if args.self_check or args.report:
        report = json.dumps({
                    "version": __version__,
                    "storage": "ok",
                    "exam_count": len(exams),
                    "data_dir": str(application.data_dir),
                    "runtime": health,
                    "packaging": "not_verified",
                })
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        if sys.stdout is not None:
            print(report)
    if (args.self_check or args.report) and not args.smoke_ui:
        return 0
    from PySide6.QtWidgets import QApplication

    from exam_grader.ui import MainWindow

    qt = QApplication(sys.argv[:1])
    window = MainWindow(application)
    window.show()
    if args.smoke_ui:
        from PySide6.QtCore import QTimer
        QTimer.singleShot(700, qt.quit)
    return qt.exec()


if __name__ == "__main__":
    raise SystemExit(main())
