import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from exam_grader.app import initialize
from exam_grader.ui import MainWindow


def test_home_camera_help_is_accessible_and_covers_capture_basics(tmp_path):
    app = QApplication.instance() or QApplication([])
    window = MainWindow(initialize(tmp_path / "data"))
    window.show()
    app.processEvents()

    help_button = window.camera_help_button
    assert help_button.isVisible()
    assert help_button.accessibleName() == "คำแนะนำการถ่ายภาพกระดาษคำตอบ"
    guidance = help_button.toolTip()
    assert "4 มุม" in guidance
    assert "พื้นหลังที่ตัดกับกระดาษ" in guidance
    assert "ขนานกับกระดาษ" in guidance
    assert "เงาหรือแสงสะท้อน" in guidance
    assert "ไม่ต้องครอปภาพ" in guidance

    window.close()
