"""Small cross-platform UI preferences backed by QSettings."""

from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths, Qt
from PySide6.QtGui import QColor, QPalette


def default_output_root() -> Path:
    settings = QSettings("ExamGrader", "ExamGrader")
    configured = str(settings.value("output_root", "", type=str) or "").strip()
    if configured:
        return Path(configured).expanduser()
    documents = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
    return Path(documents or Path.home() / "Documents") / "ExamGrader"


def save_output_root(path: Path) -> None:
    QSettings("ExamGrader", "ExamGrader").setValue("output_root", str(path.expanduser().resolve()))


DEFAULT_ANNOTATION_COLORS: dict[str, tuple[int, int, int, int]] = {
    "correct": (40, 180, 40, 255),  # green
    "incorrect": (40, 40, 220, 255),  # red
    "blank": (0, 165, 255, 255),  # orange
    "multiple": (190, 70, 190, 255),  # purple
    "boundary_cross": (0, 215, 255, 255),  # yellow
    "other": (0, 165, 255, 255),  # general other
    "score": (180, 90, 20, 255),  # blue
}


def default_annotation_colors() -> dict[str, tuple[int, int, int, int]]:
    return dict(DEFAULT_ANNOTATION_COLORS)


def annotation_colors() -> dict[str, tuple[int, int, int, int]]:
    settings = QSettings("ExamGrader", "ExamGrader")
    colors = dict(DEFAULT_ANNOTATION_COLORS)
    for key in ("correct", "incorrect", "blank", "multiple", "boundary_cross", "other", "score"):
        val = str(settings.value(f"annotation_colors/{key}", "", type=str) or "").strip()
        if val:
            try:
                parts = [int(p.strip()) for p in val.split(",")]
                if len(parts) == 4 and all(0 <= p <= 255 for p in parts):
                    colors[key] = (parts[0], parts[1], parts[2], parts[3])
            except ValueError:
                pass
    # If "other" was customized but specific subcategories were not, let "other" apply to them
    val_other = str(settings.value("annotation_colors/other", "", type=str) or "").strip()
    if val_other and not str(settings.value("annotation_colors/blank", "", type=str) or "").strip():
        colors["blank"] = colors["other"]
    if (
        val_other
        and not str(settings.value("annotation_colors/multiple", "", type=str) or "").strip()
    ):
        colors["multiple"] = colors["other"]
    if (
        val_other
        and not str(settings.value("annotation_colors/boundary_cross", "", type=str) or "").strip()
    ):
        colors["boundary_cross"] = colors["other"]
    return colors


def save_annotation_colors(colors: dict[str, tuple[int, int, int, int]]) -> None:
    settings = QSettings("ExamGrader", "ExamGrader")
    for key, val in colors.items():
        if len(val) == 4 and all(0 <= c <= 255 for c in val):
            settings.setValue(f"annotation_colors/{key}", f"{val[0]},{val[1]},{val[2]},{val[3]}")


def reset_annotation_colors() -> None:
    settings = QSettings("ExamGrader", "ExamGrader")
    for key in ("correct", "incorrect", "blank", "multiple", "boundary_cross", "other", "score"):
        settings.remove(f"annotation_colors/{key}")


def default_template_id() -> str:
    settings = QSettings("ExamGrader", "ExamGrader")
    tid = str(settings.value("default_template_id", "default-1", type=str) or "").strip()
    return tid or "default-1"


def save_default_template_id(template_id: str) -> None:
    QSettings("ExamGrader", "ExamGrader").setValue("default_template_id", template_id.strip())


APPEARANCE_MODES = ("system", "light", "dark")


def appearance_mode() -> str:
    """Return stored appearance preference: 'system' | 'light' | 'dark'."""
    settings = QSettings("ExamGrader", "ExamGrader")
    mode = str(settings.value("appearance_mode", "system", type=str) or "system").strip().lower()
    return mode if mode in APPEARANCE_MODES else "system"


def save_appearance_mode(mode: str) -> None:
    """Save appearance preference: 'system' | 'light' | 'dark'."""
    normalized = mode.strip().lower()
    if normalized not in APPEARANCE_MODES:
        raise ValueError(f"Unknown appearance mode: {mode}")
    QSettings("ExamGrader", "ExamGrader").setValue("appearance_mode", normalized)


def create_theme_palette(mode: str) -> QPalette:
    """Create a unified QPalette ensuring consistent native OS and Qt widget rendering."""
    palette = QPalette()
    if mode == "dark":
        bg = QColor("#0F172A")
        card_bg = QColor("#1E293B")
        alt_bg = QColor("#172033")
        text_pri = QColor("#F8FAFC")
        text_dis = QColor("#64748B")
        border = QColor("#334155")
        accent = QColor("#2563EB")
        accent_text = QColor("#FFFFFF")

        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.WindowText, text_pri)
        palette.setColor(QPalette.ColorRole.Base, card_bg)
        palette.setColor(QPalette.ColorRole.AlternateBase, alt_bg)
        palette.setColor(QPalette.ColorRole.ToolTipBase, card_bg)
        palette.setColor(QPalette.ColorRole.ToolTipText, text_pri)
        palette.setColor(QPalette.ColorRole.Text, text_pri)
        palette.setColor(QPalette.ColorRole.Button, card_bg)
        palette.setColor(QPalette.ColorRole.ButtonText, text_pri)
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, accent_text)
        palette.setColor(QPalette.ColorRole.Midlight, border)
        palette.setColor(QPalette.ColorRole.Dark, bg)

        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, bg)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, bg)
    else:
        bg = QColor("#F8FAFC")
        card_bg = QColor("#FFFFFF")
        alt_bg = QColor("#F1F5F9")
        text_pri = QColor("#0F172A")
        text_dis = QColor("#94A3B8")
        border = QColor("#CBD5E1")
        accent = QColor("#2563EB")
        accent_text = QColor("#FFFFFF")

        palette.setColor(QPalette.ColorRole.Window, bg)
        palette.setColor(QPalette.ColorRole.WindowText, text_pri)
        palette.setColor(QPalette.ColorRole.Base, card_bg)
        palette.setColor(QPalette.ColorRole.AlternateBase, alt_bg)
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#0F172A"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.Text, text_pri)
        palette.setColor(QPalette.ColorRole.Button, card_bg)
        palette.setColor(QPalette.ColorRole.ButtonText, text_pri)
        palette.setColor(QPalette.ColorRole.Highlight, accent)
        palette.setColor(QPalette.ColorRole.HighlightedText, accent_text)
        palette.setColor(QPalette.ColorRole.Midlight, border)
        palette.setColor(QPalette.ColorRole.Dark, QColor("#E2E8F0"))

        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, text_dis)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Base, bg)
        palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Button, alt_bg)
    return palette


def is_dark_mode(app: object = None) -> bool:
    """Return True if dark mode is active or resolved via system styleHints."""
    mode = appearance_mode()
    if mode == "dark":
        return True
    if mode == "light":
        return False
    if app and hasattr(app, "styleHints") and hasattr(app.styleHints(), "colorScheme"):
        return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
    return False


def _theme_icon_path(name: str, mode: str) -> str:
    """Return a bundled SVG path for stylesheet-drawn controls."""
    return (Path(__file__).resolve().parent / "resources" / f"{name}-{mode}.svg").as_posix()


def get_theme_stylesheet(mode: str) -> str:
    """Central design tokens and stylesheet for light/dark themes."""
    if mode == "light":
        chevron = _theme_icon_path("chevron-down", "light")
        return """
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Thonburi", "Noto Sans Thai", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
                color: #0F172A;
            }
            QMainWindow, QDialog {
                background-color: #F8FAFC;
            }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #334155;
            }
            QLabel {
                padding: 1px 0px;
            }
            QLabel[role="warning"] {
                color: #B45309;
                font-weight: 500;
            }
            QPushButton {
                min-height: 24px;
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 5px 12px;
                font-weight: 500;
                color: #0F172A;
            }
            QPushButton:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
            }
            QPushButton:pressed {
                background-color: #E2E8F0;
            }
            QPushButton:disabled {
                background-color: #F8FAFC;
                border-color: #E2E8F0;
                color: #94A3B8;
            }
            QPushButton:default {
                background-color: #2563EB;
                color: #FFFFFF;
                border-color: #1D4ED8;
            }
            QPushButton:default:hover {
                background-color: #1D4ED8;
            }
            QPushButton:checked {
                background-color: #EFF6FF;
                border-color: #2563EB;
                color: #1D4ED8;
                font-weight: 600;
            }
            QPushButton[destructive="true"] {
                color: #DC2626;
                border-color: #FCA5A5;
            }
            QPushButton[destructive="true"]:hover {
                background-color: #FEF2F2;
                border-color: #EF4444;
            }
            QPushButton[destructive="true"]:pressed {
                background-color: #FEE2E2;
            }
            QPushButton[kind="icon"] {
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0px;
                background: transparent;
            }
            QPushButton[kind="icon"]:hover {
                background-color: #F1F5F9;
                border-color: #CBD5E1;
            }
            QPushButton[kind="icon"]:pressed {
                background-color: #E2E8F0;
            }
            QPushButton[kind="icon"]:focus {
                border-color: #2563EB;
            }
            QPushButton[kind="trash"] {
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 0px;
                background: transparent;
            }
            QPushButton[kind="trash"]:hover {
                background-color: #FFF7F7;
                border-color: transparent;
            }
            QPushButton[kind="trash"]:pressed {
                background-color: #FEECEF;
                border-color: transparent;
            }
            QPushButton[kind="trash"]:focus {
                border-color: #E7AAB2;
            }
            QPushButton[kind="icon"][destructive="true"] {
                color: #DC2626;
                background-color: #FFF1F2;
                border-color: #FECDD3;
            }
            QPushButton[kind="icon"][destructive="true"]:hover {
                background-color: #FEF2F2;
                border-color: #FCA5A5;
            }
            QPushButton[kind="icon"][destructive="true"]:pressed {
                background-color: #FEE2E2;
            }
            QPushButton[kind="compact"] {
                min-height: 22px;
                max-height: 22px;
                border-radius: 8px;
                padding: 4px 10px;
            }
            QLineEdit, QSpinBox {
                min-height: 26px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 5px 10px;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1.5px solid #2563EB;
            }
            QLineEdit:disabled, QSpinBox:disabled {
                background-color: #F8FAFC;
                border-color: #E2E8F0;
                color: #94A3B8;
            }
            QSpinBox {
                min-height: 24px;
                padding: 3px 10px;
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }
            QComboBox {
                min-height: 26px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 5px 36px 5px 10px;
                background-color: #FFFFFF;
                color: #0F172A;
            }
            QComboBox:focus {
                border: 1.5px solid #2563EB;
            }
            QComboBox:disabled {
                background-color: #F8FAFC;
                border-color: #E2E8F0;
                color: #94A3B8;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 34px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url("__CHEVRON__");
                width: 14px;
                height: 8px;
            }
            QComboBox QLineEdit {
                border: none;
                border-radius: 0px;
                padding: 0px;
                background: transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                padding: 6px;
                color: #0F172A;
                selection-background-color: #2563EB;
                selection-color: #FFFFFF;
                outline: none;
            }
            QPushButton::menu-indicator, QToolButton::menu-indicator {
                image: url("__CHEVRON__");
                width: 12px;
                height: 7px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 11px;
            }
            QToolButton {
                min-height: 24px;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 5px 36px 5px 12px;
                background-color: #FFFFFF;
                color: #0F172A;
                font-weight: 500;
            }
            QToolButton:hover {
                background-color: #F1F5F9;
                border-color: #94A3B8;
            }
            QToolButton:pressed {
                background-color: #E2E8F0;
            }
            QToolButton:disabled {
                background-color: #F8FAFC;
                border-color: #E2E8F0;
                color: #94A3B8;
            }
            QToolButton[kind="icon"] {
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0px;
                background: transparent;
            }
            QToolButton[kind="icon"]:hover {
                background-color: #F1F5F9;
                border-color: #CBD5E1;
            }
            QToolButton[kind="icon"]:pressed {
                background-color: #E2E8F0;
            }
            QToolButton[kind="icon"]:focus {
                border-color: #2563EB;
            }
            QToolButton[kind="icon"]::menu-indicator {
                image: none;
            }
            QPushButton[accent="true"] {
                background-color: #2563EB;
                border-color: #1D4ED8;
                color: #FFFFFF;
                font-weight: 600;
            }
            QPushButton[accent="true"]:hover {
                background-color: #1D4ED8;
            }
            QPushButton[accent="true"]:pressed {
                background-color: #1E40AF;
            }
            QPushButton[accent="true"]:disabled {
                background-color: #BFDBFE;
                border-color: #93C5FD;
                color: #FFFFFF;
            }
            QLabel[role="muted"] {
                color: #64748B;
                font-weight: 500;
            }
            QLabel[role="page-title"] {
                font-size: 24px;
                font-weight: 700;
                color: #0F172A;
            }
            QLabel[role="section-title"] {
                font-size: 17px;
                font-weight: 700;
                color: #0F172A;
            }
            QLabel[role="section-label"] {
                font-weight: 600;
                color: #475569;
            }
            QLabel[role="hint"] {
                font-size: 11px;
                color: #64748B;
                padding: 2px 4px;
            }
            QLabel[role="body"] {
                font-size: 13px;
            }
            QLabel[role="metric"] {
                font-size: 13px;
                font-weight: 700;
                color: #0F172A;
            }
            QLabel[role="preview"], QLabel[role="preview-background"] {
                border: 1px solid #CBD5E1;
                border-radius: 10px;
                background-color: #F1F5F9;
            }
            QMenu {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 6px 4px;
                color: #0F172A;
            }
            QMenu::item {
                padding: 6px 24px 6px 20px;
                border-radius: 4px;
                background-color: transparent;
                color: #0F172A;
            }
            QMenu::item:selected {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            QMenu::item:disabled {
                color: #94A3B8;
            }
            QMenu::separator {
                height: 1px;
                background-color: #E2E8F0;
                margin: 4px 6px;
            }
            QMenuBar {
                background-color: #F8FAFC;
                color: #0F172A;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background-color: transparent;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #E2E8F0;
            }
            QListWidget {
                background-color: #FFFFFF;
                border: 1px solid #CBD5E1;
                border-radius: 8px;
                padding: 4px;
                outline: none;
                color: #0F172A;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 8px;
                color: #0F172A;
                border-bottom: 1px solid #F1F5F9;
            }
            QListWidget::item:hover:!selected {
                background-color: #F1F5F9;
            }
            QListWidget::item:selected {
                background-color: #EFF6FF;
                color: #0F172A;
                border-bottom-color: #BFDBFE;
            }
            QTabWidget::pane {
                border: 1px solid #E2E8F0;
                background-color: #FFFFFF;
                border-radius: 8px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #F1F5F9;
                color: #64748B;
                border: 1px solid #E2E8F0;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 18px;
                margin-right: 3px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background-color: #E2E8F0;
                color: #0F172A;
            }
            QTableWidget {
                background-color: #FFFFFF;
                alternate-background-color: #F8FAFC;
                border: 1px solid #E2E8F0;
                border-radius: 8px;
                gridline-color: #F1F5F9;
                color: #0F172A;
                selection-background-color: #2563EB;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #F1F5F9;
                color: #475569;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #CBD5E1;
                padding: 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #CBD5E1;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #94A3B8;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal {
                background: #CBD5E1;
                min-width: 24px;
                border-radius: 4px;
            }
            QToolTip {
                background-color: #0F172A;
                color: #FFFFFF;
                border: 1px solid #334155;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #CBD5E1;
                border-radius: 6px;
                text-align: center;
                background-color: #F1F5F9;
                color: #0F172A;
            }
            QProgressBar::chunk {
                background-color: #2563EB;
                border-radius: 5px;
            }
            QSplitter::handle {
                background-color: #E2E8F0;
            }
        """.replace("__CHEVRON__", chevron)
    elif mode == "dark":
        chevron = _theme_icon_path("chevron-down", "dark")
        return """
            QWidget {
                font-family: -apple-system, BlinkMacSystemFont, "Thonburi", "Noto Sans Thai", "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                font-size: 13px;
                color: #F8FAFC;
            }
            QMainWindow, QDialog {
                background-color: #0F172A;
            }
            QGroupBox {
                font-weight: 600;
                border: 1px solid #334155;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background-color: #1E293B;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
                color: #94A3B8;
            }
            QLabel {
                padding: 1px 0px;
            }
            QLabel[role="warning"] {
                color: #FBBF24;
                font-weight: 500;
            }
            QPushButton {
                min-height: 24px;
                background-color: #1E293B;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 5px 12px;
                font-weight: 500;
                color: #F8FAFC;
            }
            QPushButton:hover {
                background-color: #334155;
                border-color: #64748B;
            }
            QPushButton:pressed {
                background-color: #475569;
            }
            QPushButton:disabled {
                background-color: #0F172A;
                border-color: #334155;
                color: #64748B;
            }
            QPushButton:default {
                background-color: #3B82F6;
                color: #FFFFFF;
                border-color: #2563EB;
            }
            QPushButton:default:hover {
                background-color: #2563EB;
            }
            QPushButton:checked {
                background-color: #1E3A8A;
                border-color: #3B82F6;
                color: #93C5FD;
                font-weight: 600;
            }
            QPushButton[destructive="true"] {
                color: #F87171;
                border-color: #7F1D1D;
            }
            QPushButton[destructive="true"]:hover {
                background-color: #450A0A;
                border-color: #EF4444;
            }
            QPushButton[destructive="true"]:pressed {
                background-color: #7F1D1D;
            }
            QPushButton[kind="icon"] {
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0px;
                background: transparent;
            }
            QPushButton[kind="icon"]:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QPushButton[kind="icon"]:pressed {
                background-color: #475569;
            }
            QPushButton[kind="icon"]:focus {
                border-color: #3B82F6;
            }
            QPushButton[kind="trash"] {
                min-width: 32px;
                max-width: 32px;
                min-height: 32px;
                max-height: 32px;
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 0px;
                background: transparent;
            }
            QPushButton[kind="trash"]:hover {
                background-color: #3B2529;
                border-color: transparent;
            }
            QPushButton[kind="trash"]:pressed {
                background-color: #512C32;
                border-color: transparent;
            }
            QPushButton[kind="trash"]:focus {
                border-color: #B86B76;
            }
            QPushButton[kind="icon"][destructive="true"] {
                color: #F87171;
                background-color: #451A1A;
                border-color: #7F1D1D;
            }
            QPushButton[kind="icon"][destructive="true"]:hover {
                background-color: #450A0A;
                border-color: #7F1D1D;
            }
            QPushButton[kind="icon"][destructive="true"]:pressed {
                background-color: #7F1D1D;
            }
            QPushButton[kind="compact"] {
                min-height: 22px;
                max-height: 22px;
                border-radius: 8px;
                padding: 4px 10px;
            }
            QLineEdit, QSpinBox {
                min-height: 26px;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 5px 10px;
                background-color: #1E293B;
                color: #F8FAFC;
            }
            QLineEdit:focus, QSpinBox:focus {
                border: 1.5px solid #3B82F6;
            }
            QLineEdit:disabled, QSpinBox:disabled {
                background-color: #0F172A;
                border-color: #334155;
                color: #64748B;
            }
            QSpinBox {
                min-height: 24px;
                padding: 3px 10px;
            }
            QSpinBox::up-button, QSpinBox::down-button,
            QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {
                width: 0px;
                height: 0px;
                border: none;
                background: transparent;
            }
            QComboBox {
                min-height: 26px;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 5px 36px 5px 10px;
                background-color: #1E293B;
                color: #F8FAFC;
            }
            QComboBox:focus {
                border: 1.5px solid #3B82F6;
            }
            QComboBox:disabled {
                background-color: #0F172A;
                border-color: #334155;
                color: #64748B;
            }
            QComboBox::drop-down {
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 34px;
                border: none;
                background: transparent;
            }
            QComboBox::down-arrow {
                image: url("__CHEVRON__");
                width: 14px;
                height: 8px;
            }
            QComboBox QLineEdit {
                border: none;
                border-radius: 0px;
                padding: 0px;
                background: transparent;
            }
            QComboBox QAbstractItemView {
                background-color: #1E293B;
                border: 1px solid #475569;
                border-radius: 10px;
                padding: 6px;
                color: #F8FAFC;
                selection-background-color: #2563EB;
                selection-color: #FFFFFF;
                outline: none;
            }
            QPushButton::menu-indicator, QToolButton::menu-indicator {
                image: url("__CHEVRON__");
                width: 12px;
                height: 7px;
                subcontrol-origin: padding;
                subcontrol-position: center right;
                right: 11px;
            }
            QToolButton {
                min-height: 24px;
                border: 1px solid #475569;
                border-radius: 8px;
                padding: 5px 36px 5px 12px;
                background-color: #1E293B;
                color: #F8FAFC;
                font-weight: 500;
            }
            QToolButton:hover {
                background-color: #334155;
                border-color: #64748B;
            }
            QToolButton:pressed {
                background-color: #475569;
            }
            QToolButton:disabled {
                background-color: #0F172A;
                border-color: #334155;
                color: #64748B;
            }
            QToolButton[kind="icon"] {
                min-width: 36px;
                max-width: 36px;
                min-height: 36px;
                max-height: 36px;
                border: 1px solid transparent;
                border-radius: 8px;
                padding: 0px;
                background: transparent;
            }
            QToolButton[kind="icon"]:hover {
                background-color: #334155;
                border-color: #475569;
            }
            QToolButton[kind="icon"]:pressed {
                background-color: #475569;
            }
            QToolButton[kind="icon"]:focus {
                border-color: #3B82F6;
            }
            QToolButton[kind="icon"]::menu-indicator {
                image: none;
            }
            QPushButton[accent="true"] {
                background-color: #3B82F6;
                border-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
            }
            QPushButton[accent="true"]:hover {
                background-color: #2563EB;
            }
            QPushButton[accent="true"]:pressed {
                background-color: #1D4ED8;
            }
            QPushButton[accent="true"]:disabled {
                background-color: #1E3A8A;
                border-color: #1E40AF;
                color: #94A3B8;
            }
            QLabel[role="muted"] {
                color: #94A3B8;
                font-weight: 500;
            }
            QLabel[role="page-title"] {
                font-size: 24px;
                font-weight: 700;
                color: #F8FAFC;
            }
            QLabel[role="section-title"] {
                font-size: 17px;
                font-weight: 700;
                color: #F8FAFC;
            }
            QLabel[role="section-label"] {
                font-weight: 600;
                color: #CBD5E1;
            }
            QLabel[role="hint"] {
                font-size: 11px;
                color: #94A3B8;
                padding: 2px 4px;
            }
            QLabel[role="body"] {
                font-size: 13px;
            }
            QLabel[role="metric"] {
                font-size: 13px;
                font-weight: 700;
                color: #F8FAFC;
            }
            QLabel[role="preview"], QLabel[role="preview-background"] {
                border: 1px solid #475569;
                border-radius: 10px;
                background-color: #172033;
            }
            QMenu {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 6px 4px;
                color: #F8FAFC;
            }
            QMenu::item {
                padding: 6px 24px 6px 20px;
                border-radius: 4px;
                background-color: transparent;
                color: #F8FAFC;
            }
            QMenu::item:selected {
                background-color: #2563EB;
                color: #FFFFFF;
            }
            QMenu::item:disabled {
                color: #64748B;
            }
            QMenu::separator {
                height: 1px;
                background-color: #334155;
                margin: 4px 6px;
            }
            QMenuBar {
                background-color: #0F172A;
                color: #F8FAFC;
            }
            QMenuBar::item {
                padding: 4px 10px;
                background-color: transparent;
                border-radius: 4px;
            }
            QMenuBar::item:selected {
                background-color: #334155;
            }
            QListWidget {
                background-color: #1E293B;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 4px;
                outline: none;
                color: #F8FAFC;
            }
            QListWidget::item {
                padding: 4px 8px;
                border-radius: 8px;
                color: #F8FAFC;
                border-bottom: 1px solid #334155;
            }
            QListWidget::item:hover:!selected {
                background-color: #334155;
            }
            QListWidget::item:selected {
                background-color: #1E3A8A;
                color: #FFFFFF;
                border-bottom-color: #3B82F6;
            }
            QTabWidget::pane {
                border: 1px solid #334155;
                background-color: #1E293B;
                border-radius: 8px;
                top: -1px;
            }
            QTabBar::tab {
                background-color: #1E293B;
                color: #94A3B8;
                border: 1px solid #334155;
                border-bottom: none;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                padding: 8px 18px;
                margin-right: 3px;
                font-weight: 500;
            }
            QTabBar::tab:selected {
                background-color: #2563EB;
                color: #FFFFFF;
                font-weight: 600;
            }
            QTabBar::tab:hover:!selected {
                background-color: #334155;
                color: #F8FAFC;
            }
            QTableWidget {
                background-color: #1E293B;
                alternate-background-color: #172033;
                border: 1px solid #334155;
                border-radius: 8px;
                gridline-color: #334155;
                color: #F8FAFC;
                selection-background-color: #2563EB;
                selection-color: #FFFFFF;
            }
            QHeaderView::section {
                background-color: #0F172A;
                color: #94A3B8;
                font-weight: 600;
                border: none;
                border-bottom: 1px solid #334155;
                padding: 8px;
            }
            QScrollBar:vertical {
                background: transparent;
                width: 10px;
                margin: 2px;
            }
            QScrollBar::handle:vertical {
                background: #475569;
                min-height: 24px;
                border-radius: 4px;
            }
            QScrollBar::handle:vertical:hover {
                background: #64748B;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                height: 0px;
            }
            QScrollBar:horizontal {
                background: transparent;
                height: 10px;
                margin: 2px;
            }
            QScrollBar::handle:horizontal {
                background: #475569;
                min-width: 24px;
                border-radius: 4px;
            }
            QToolTip {
                background-color: #F8FAFC;
                color: #0F172A;
                border: 1px solid #E2E8F0;
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 12px;
            }
            QProgressBar {
                border: 1px solid #475569;
                border-radius: 6px;
                text-align: center;
                background-color: #1E293B;
                color: #F8FAFC;
            }
            QProgressBar::chunk {
                background-color: #3B82F6;
                border-radius: 5px;
            }
            QSplitter::handle {
                background-color: #334155;
            }
        """.replace("__CHEVRON__", chevron)
    return ""  # Fallback


def apply_appearance_theme(app: object, mode: str | None = None) -> None:
    """Apply chosen appearance theme to QApplication, synchronizing palette and stylesheet."""
    target_mode = (mode or appearance_mode()).lower()

    # Resolve "system" mode dynamically via styleHints if available
    effective_mode = target_mode
    if target_mode == "system":
        if hasattr(app, "styleHints") and hasattr(app.styleHints(), "colorScheme"):
            if app.styleHints().colorScheme() == Qt.ColorScheme.Dark:
                effective_mode = "dark"
            else:
                effective_mode = "light"
        else:
            effective_mode = "light"

    if hasattr(app, "setPalette"):
        app.setPalette(create_theme_palette(effective_mode))
    if hasattr(app, "setStyleSheet"):
        app.setStyleSheet(get_theme_stylesheet(effective_mode))
