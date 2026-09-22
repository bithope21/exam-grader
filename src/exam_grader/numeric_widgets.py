"""Centralized numeric widgets, locale configuration, and digit normalization.

Ensures that numeric inputs and displays in Exam Grader always use Arabic digits (0-9)
on both macOS and Windows, while properly handling pasted or legacy Thai digits (๐-๙).
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import QLocale
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QDoubleSpinBox, QLineEdit, QSpinBox

THAI_DIGITS = "๐๑๒๓๔๕๖๗๘๙"
ARABIC_DIGITS = "0123456789"
THAI_TO_ARABIC_MAP = str.maketrans(THAI_DIGITS, ARABIC_DIGITS)


def normalize_digits(text: str | None) -> str:
    """Translate Thai numerals (๐-๙) to Arabic digits (0-9).

    Safe for None values (returns empty string).
    """
    if text is None:
        return ""
    return str(text).translate(THAI_TO_ARABIC_MAP)


def parse_int_safe(val: object, default: int = 0) -> int:
    """Normalize Thai digits and parse an integer safely.

    Returns `default` if parsing fails.
    """
    if val is None:
        return default
    text = normalize_digits(str(val)).strip()
    try:
        return int(text)
    except (ValueError, TypeError):
        return default


def parse_float_safe(val: object, default: float = 0.0) -> float:
    """Normalize Thai digits and parse a float safely.

    Returns `default` if parsing fails.
    """
    if val is None:
        return default
    text = normalize_digits(str(val)).strip().replace(",", ".")
    try:
        return float(text)
    except (ValueError, TypeError):
        return default


def ensure_arabic_numeric_locale() -> None:
    """Configure Qt application default locale to Thai with Arabic numerals (0-9).

    On Windows with Thai locale, QLocale.system() defaults to native digits (๐-๙).
    Explicitly initializing QLocale with (Language.Thai, Country.Thailand) uses Qt's
    CLDR data where zeroDigit is '0', preventing QSpinBox / QDoubleSpinBox from rendering
    Thai numerals while fully preserving Thai language, dates, and month names.
    """
    locale = QLocale(QLocale.Language.Thai, QLocale.Country.Thailand)
    locale.setNumberOptions(QLocale.NumberOption.OmitGroupSeparator)
    QLocale.setDefault(locale)


def attach_digit_normalizer(line_edit: QLineEdit, digits_only: bool = False) -> None:
    """Attach dynamic Thai-to-Arabic digit normalization on textChanged for a QLineEdit.

    Preserves cursor position during in-place replacement.
    """
    def _on_text_changed(text: str) -> None:
        normalized = normalize_digits(text)
        if digits_only:
            normalized = "".join(ch for ch in normalized if ch.isdigit())
        if normalized != text:
            cursor = line_edit.cursorPosition()
            line_edit.blockSignals(True)
            line_edit.setText(normalized)
            line_edit.setCursorPosition(min(cursor, len(normalized)))
            line_edit.blockSignals(False)
            line_edit.textEdited.emit(normalized)

    line_edit.textChanged.connect(_on_text_changed)


class NumericSpinBox(QSpinBox):
    """QSpinBox that guarantees Arabic digit (0-9) display and accepts Thai digit paste."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLocale(QLocale.c())
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.textChanged.connect(self._normalize_input)

    def _normalize_input(self, text: str) -> None:
        normalized = normalize_digits(text)
        if normalized != text:
            line_edit = self.lineEdit()
            if line_edit is not None:
                cursor = line_edit.cursorPosition()
                line_edit.blockSignals(True)
                line_edit.setText(normalized)
                line_edit.setCursorPosition(min(cursor, len(normalized)))
                line_edit.blockSignals(False)

    def validate(self, text: str, pos: int):
        normalized = normalize_digits(text)
        return super().validate(normalized, pos)

    def valueFromText(self, text: str) -> int:
        normalized = normalize_digits(text)
        return super().valueFromText(normalized)

    def textFromValue(self, val: int) -> str:
        return str(val)


class NumericDoubleSpinBox(QDoubleSpinBox):
    """QDoubleSpinBox that guarantees Arabic digit (0-9) display and accepts Thai digit paste."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLocale(QLocale.c())
        line_edit = self.lineEdit()
        if line_edit is not None:
            line_edit.textChanged.connect(self._normalize_input)

    def _normalize_input(self, text: str) -> None:
        normalized = normalize_digits(text)
        if normalized != text:
            line_edit = self.lineEdit()
            if line_edit is not None:
                cursor = line_edit.cursorPosition()
                line_edit.blockSignals(True)
                line_edit.setText(normalized)
                line_edit.setCursorPosition(min(cursor, len(normalized)))
                line_edit.blockSignals(False)

    def validate(self, text: str, pos: int):
        normalized = normalize_digits(text)
        return super().validate(normalized, pos)

    def valueFromText(self, text: str) -> float:
        normalized = normalize_digits(text).replace(",", ".")
        return super().valueFromText(normalized)

    def textFromValue(self, val: float) -> str:
        return f"{val:.{self.decimals()}f}"


class NumericIntValidator(QIntValidator):
    """QIntValidator that normalizes Thai digits before validating."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLocale(QLocale.c())

    def validate(self, text: str, pos: int):
        normalized = normalize_digits(text)
        return super().validate(normalized, pos)

    def fixup(self, text: str) -> str:
        norm = normalize_digits(text)
        try:
            return str(int(norm))
        except (ValueError, TypeError):
            return super().fixup(norm)


class NumericDoubleValidator(QDoubleValidator):
    """QDoubleValidator that normalizes Thai digits before validating."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLocale(QLocale.c())

    def validate(self, text: str, pos: int):
        normalized = normalize_digits(text).replace(",", ".")
        return super().validate(normalized, pos)

    def fixup(self, text: str) -> str:
        norm = normalize_digits(text).replace(",", ".")
        try:
            val = float(norm)
            return f"{val:.{self.decimals()}f}"
        except (ValueError, TypeError):
            return super().fixup(norm)


class NumericLineEdit(QLineEdit):
    """QLineEdit that normalizes Thai digits (๐-๙) to Arabic digits (0-9) dynamically."""

    def __init__(self, *args, digits_only: bool = False, **kwargs):
        super().__init__(*args, **kwargs)
        self.setLocale(QLocale.c())
        self.digits_only = digits_only
        attach_digit_normalizer(self, digits_only=digits_only)
