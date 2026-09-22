from pathlib import Path
from PySide6.QtCore import QLocale, Qt
from PySide6.QtWidgets import QApplication, QLineEdit

from exam_grader.numeric_widgets import (
    NumericDoubleSpinBox,
    NumericDoubleValidator,
    NumericIntValidator,
    NumericLineEdit,
    NumericSpinBox,
    attach_digit_normalizer,
    ensure_arabic_numeric_locale,
    normalize_digits,
    parse_float_safe,
    parse_int_safe,
)


def _get_app():
    return QApplication.instance() or QApplication([])


def test_normalize_digits():
    assert normalize_digits("๐๑๒๓๔๕๖๗๘๙") == "0123456789"
    assert normalize_digits("ห้อง ๑/๒ (ชั้น ป.๓)") == "ห้อง 1/2 (ชั้น ป.3)"
    assert normalize_digits("12345") == "12345"
    assert normalize_digits(None) == ""
    assert normalize_digits("") == ""


def test_parse_int_safe():
    assert parse_int_safe("๑๒๓") == 123
    assert parse_int_safe("  ๔๕  ") == 45
    assert parse_int_safe("123") == 123
    assert parse_int_safe(99) == 99
    assert parse_int_safe("invalid", default=10) == 10
    assert parse_int_safe(None, default=5) == 5


def test_parse_float_safe():
    assert parse_float_safe("๔๕.๖") == 45.6
    assert parse_float_safe("๔๕,๖") == 45.6
    assert parse_float_safe("12.34") == 12.34
    assert parse_float_safe(3.14) == 3.14
    assert parse_float_safe("bad", default=1.5) == 1.5
    assert parse_float_safe(None, default=0.0) == 0.0


def test_ensure_arabic_numeric_locale():
    _get_app()
    ensure_arabic_numeric_locale()
    current_locale = QLocale()
    assert current_locale.language() == QLocale.Language.Thai
    assert current_locale.zeroDigit() == "0"
    assert current_locale.toString(123) == "123"


def test_numeric_spinbox_display_and_paste():
    _get_app()
    ensure_arabic_numeric_locale()
    sb = NumericSpinBox()
    sb.setRange(1, 1000)
    sb.setValue(123)

    assert sb.text() == "123"
    assert sb.cleanText() == "123"

    # Test typing/pasting Thai digits into lineEdit
    sb.lineEdit().setText("๔๕๖")
    assert sb.lineEdit().text() == "456"
    assert sb.value() == 456

    # Test valueFromText and validate
    assert sb.valueFromText("๗๘๙") == 789
    state, norm_text, _pos = sb.validate("๑๐๐", 0)
    assert norm_text == "100"


def test_numeric_double_spinbox_display_and_paste():
    _get_app()
    ensure_arabic_numeric_locale()
    dsb = NumericDoubleSpinBox()
    dsb.setRange(0.0, 100.0)
    dsb.setDecimals(2)
    dsb.setValue(12.5)

    assert dsb.text() == "12.50"

    # Test typing/pasting Thai digits
    dsb.lineEdit().setText("๙๙.๕")
    assert dsb.lineEdit().text() == "99.5"
    assert dsb.value() == 99.5

    assert dsb.valueFromText("๑๒.๓๔") == 12.34


def test_numeric_validators():
    _get_app()
    iv = NumericIntValidator(1, 100)
    state, text, _pos = iv.validate("๕๐", 0)
    assert text == "50"
    assert iv.fixup("๙๙") == "99"

    dv = NumericDoubleValidator(0.0, 100.0, 2)
    state, text, _pos = dv.validate("๕๐.๕", 0)
    assert text == "50.5"
    assert dv.fixup("๑๒,๓") == "12.30"


def test_attach_digit_normalizer():
    _get_app()
    le = QLineEdit()
    attach_digit_normalizer(le)
    le.setText("ตัวชี้วัด ๒.๑")
    assert le.text() == "ตัวชี้วัด 2.1"

    le_digits = QLineEdit()
    attach_digit_normalizer(le_digits, digits_only=True)
    le_digits.setText("ห้อง ๑/๒")
    assert le_digits.text() == "12"


def test_assessment_indicators_thai_digits_normalization(tmp_path: Path):
    _get_app()
    from exam_grader.exam_ui import AssessmentIndicatorsDialog
    from exam_grader.workflow import Workflow

    db_path = tmp_path / "exam-grader.sqlite3"
    wf = Workflow(db_path)
    with wf.connection() as con:
        con.execute(
            "CREATE TABLE exams (id TEXT PRIMARY KEY, name TEXT, academic_year TEXT, grade TEXT, room TEXT, subject TEXT, question_count INTEGER, expected_number_max INTEGER, template_id TEXT, template_version INTEGER, created_at TEXT, updated_at TEXT, archived_at TEXT)"
        )
        con.execute(
            "CREATE TABLE assessment_indicators (id TEXT PRIMARY KEY, exam_id TEXT, identifier TEXT, from_question INTEGER, to_question INTEGER, position INTEGER, created_at TEXT, updated_at TEXT)"
        )
        con.execute(
            "INSERT INTO exams VALUES ('e1', 'Test', '2569', 'ป.1', '1', 'Math', 60, 50, 'default-1', 1, 'now', 'now', NULL)"
        )
        # Existing data with Thai numerals in database
        con.execute(
            "INSERT INTO assessment_indicators VALUES ('i1', 'e1', '๒.๑', '๑', '๑๐', 0, 'now', 'now')"
        )

    dlg = AssessmentIndicatorsDialog(db_path, "e1", 60)
    assert len(dlg.rows) == 1
    container, identifier_edit, from_spin, to_spin = dlg.rows[0]
    assert identifier_edit.text() == "2.1"
    assert from_spin.value() == 1
    assert to_spin.value() == 10
    assert from_spin.text() == "1"
    assert to_spin.text() == "10"

    # Simulate entering Thai numerals in a new row
    dlg._add_row()
    assert len(dlg.rows) == 2
    c2, id2, from2, to2 = dlg.rows[1]
    id2.setText("๒.๒")
    from2.lineEdit().setText("๑๑")
    to2.lineEdit().setText("๒๐")

    assert id2.text() == "2.2"
    assert from2.value() == 11
    assert to2.value() == 20

    dlg.accept()

    saved = wf.list_assessment_indicators("e1")
    assert len(saved) == 2
    assert saved[0]["identifier"] == "2.1"
    assert saved[0]["from_question"] == 1
    assert saved[0]["to_question"] == 10
    assert saved[1]["identifier"] == "2.2"
    assert saved[1]["from_question"] == 11
    assert saved[1]["to_question"] == 20
