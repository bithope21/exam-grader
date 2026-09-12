"""Visual inspection loop script to generate screenshot artifacts for Default #3 and Calibration UI."""

from __future__ import annotations

import shutil
from pathlib import Path

import cv2
from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.calibration_ui import (
    CalibrationDialog,
    CalibrationTestDialog,
)
from exam_grader.imaging import analyze
from exam_grader.preferences import apply_appearance_theme
from exam_grader.settings_ui import TemplateSettingsDialog
from exam_grader.template_discovery import discover_template
from exam_grader.template_manager import save_custom_reference_image


def run_inspection(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_data = output_dir / "app_data"
    shutil.rmtree(tmp_data, ignore_errors=True)

    qapp = QApplication.instance() or QApplication([])
    apply_appearance_theme(qapp, "light")

    app = initialize(tmp_data)

    # 1. Discover template from real fixture default#3 (sheet.png)
    sheet_bytes = open("tests/fixtures/real/default3/sheet.png", "rb").read()
    discovery_res = discover_template(
        sheet_bytes,
        template_name="สุทธิอนุสรณ์ 30 ข้อ (4 ตัวเลือก)",
        template_id="custom-suthianusorn-30q",
    )
    td = discovery_res.template_def
    ref_bgr = discovery_res.warped_image

    # Save reference image to content-addressed store
    ref_png = cv2.imencode(".png", ref_bgr)[1].tobytes()
    save_custom_reference_image(app.data_dir, ref_png)

    # Save to app database so TemplateSettingsDialog shows it
    app.exams.save_template(td)

    # 2. Render TemplateSettingsDialog
    settings_dlg = TemplateSettingsDialog(app)
    settings_dlg.resize(1000, 680)
    settings_dlg.show()
    qapp.processEvents()

    # Grab screenshot
    pix_settings = settings_dlg.grab()
    pix_settings.save(str(output_dir / "template_settings_dialog.png"))
    print("Saved template_settings_dialog.png")
    settings_dlg.close()

    # 3. Render CalibrationDialog with default#3 loaded
    calib_dlg = CalibrationDialog(app, edit_template=td)
    calib_dlg.resize(1180, 780)
    calib_dlg.show()
    qapp.processEvents()

    pix_calib = calib_dlg.grab()
    pix_calib.save(str(output_dir / "calibration_dialog_default3.png"))
    print("Saved calibration_dialog_default3.png", flush=True)

    # 4. Run Test-Before-Save on real fixture sheet.png
    analysis_res = analyze(
        sheet_bytes, template_def=td, reference_override=ref_bgr, app_data_dir=app.data_dir
    )

    test_dlg = CalibrationTestDialog(td, analysis_res)
    test_dlg.resize(1180, 800)
    test_dlg.show()
    qapp.processEvents()

    pix_test = test_dlg.grab()
    pix_test.save(str(output_dir / "calibration_test_dialog_inspection.png"))
    print("Saved calibration_test_dialog_inspection.png", flush=True)

    test_dlg.close()
    calib_dlg.close()

    # 5. Render Dark Mode screenshots
    apply_appearance_theme(qapp, "dark")
    settings_dark = TemplateSettingsDialog(app)
    settings_dark.resize(1000, 680)
    settings_dark.show()
    qapp.processEvents()
    settings_dark.grab().save(str(output_dir / "template_settings_dialog_dark.png"))
    settings_dark.close()

    calib_dark = CalibrationDialog(app, edit_template=td)
    calib_dark.resize(1180, 780)
    calib_dark.show()
    qapp.processEvents()
    calib_dark.grab().save(str(output_dir / "calibration_dialog_default3_dark.png"))
    calib_dark.close()

    print("Visual inspection completed successfully!", flush=True)


if __name__ == "__main__":
    artifact_dir = Path(
        "/Users/zubinpijit/.gemini/antigravity-ide/brain/55d84ef5-135d-4acc-885a-4c58466f4646"
    )
    run_inspection(artifact_dir)
