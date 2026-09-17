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
    parser.add_argument(
        "--smoke-ui", action="store_true", help="Open and close the UI for build verification"
    )
    parser.add_argument(
        "--smoke-settings",
        action="store_true",
        help="Open template settings dialog and verify all templates load for build verification",
    )
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
        report = json.dumps(
            {
                "version": __version__,
                "storage": "ok",
                "exam_count": len(exams),
                "data_dir": str(application.data_dir),
                "runtime": health,
                "packaging": "not_verified",
            }
        )
        if args.report:
            args.report.write_text(report, encoding="utf-8")
        if sys.stdout is not None:
            print(report)
    if (args.self_check or args.report) and not args.smoke_ui and not args.smoke_settings:
        return 0
    from PySide6.QtWidgets import QApplication

    from exam_grader.preferences import apply_appearance_theme
    from exam_grader.ui import MainWindow

    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "bithope.examgrader.app"
            )
        except Exception:
            pass

    qt = QApplication(sys.argv[:1])
    resources_dir = Path(__file__).resolve().parent / "resources"
    icon_ico = resources_dir / "icon.ico"
    icon_png = resources_dir / "icon.png"
    icon_path = icon_ico if (sys.platform == "win32" and icon_ico.exists()) else icon_png
    if icon_path.exists():
        from PySide6.QtGui import QIcon

        qt.setWindowIcon(QIcon(str(icon_path)))
    apply_appearance_theme(qt)

    if args.smoke_settings:
        from exam_grader.settings_ui import TemplateSettingsDialog
        from exam_grader.template_manager import get_reference_image

        dlg = TemplateSettingsDialog(application)
        templates = []
        for r in range(dlg.table.rowCount()):
            item = dlg.table.item(r, 0)
            if item is not None:
                templates.append(item.text())
        if len(dlg.templates_list) < 3:
            print(f"FAILED: Expected at least 3 templates, got {len(dlg.templates_list)}", file=sys.stderr)
            return 1
        for b_name in ("Default #1", "Default #2", "Default #3"):
            if not any(b_name in n for n in templates):
                print(f"FAILED: Missing template {b_name} in {templates}", file=sys.stderr)
                return 1
        for t in dlg.templates_list:
            if t.kind == "builtin":
                ref = get_reference_image(t, application.data_dir)
                if ref is None or ref.size == 0:
                    print(f"FAILED: Reference image empty for {t.template_id}", file=sys.stderr)
                    return 1
        print(json.dumps({
            "smoke_settings": "ok",
            "template_count": len(dlg.templates_list),
            "templates": templates,
        }, ensure_ascii=False))
        return 0
    window = MainWindow(application)
    if not qt.windowIcon().isNull():
        window.setWindowIcon(qt.windowIcon())
    window.show()
    if args.smoke_ui:
        from PySide6.QtCore import QTimer

        QTimer.singleShot(700, qt.quit)
    return qt.exec()


if __name__ == "__main__":
    raise SystemExit(main())
