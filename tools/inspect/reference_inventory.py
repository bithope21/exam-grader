"""Read-only reference inventory; run with the project's Python environment."""

import argparse
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QImage, QImageReader, QPainter
from PySide6.QtWidgets import QApplication


def inspect(source: Path) -> tuple[list[dict], list[QImage]]:
    records, images = [], []
    for path in sorted(source.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        # Read once: digest and decoder see precisely the same bytes.
        data = path.read_bytes()
        image = QImage.fromData(data)
        record = {
            "path": path.relative_to(source).as_posix(),
            "sha256": hashlib.sha256(data).hexdigest(),
            "bytes": len(data),
            "width": image.width() if not image.isNull() else None,
            "height": image.height() if not image.isNull() else None,
            "format": bytes(QImageReader.imageFormat(str(path))).decode("ascii"),
            "status": "decode_error" if image.isNull() else "decoded",
        }
        records.append(record)
        images.append(image)
    return records, images


def write_contact_sheet(records: list[dict], images: list[QImage], output: Path) -> None:
    width, height = 560, 640
    canvas = QImage(width * 2, height * max(1, (len(records) + 1) // 2), QImage.Format.Format_RGB32)
    canvas.fill(QColor("white"))
    painter = QPainter(canvas)
    painter.setPen(QColor("black"))
    painter.setFont(QFont("Tahoma", 12))
    for index, (record, image) in enumerate(zip(records, images)):
        x, y = (index % 2) * width, (index // 2) * height
        painter.drawText(
            QRect(x + 12, y + 8, width - 24, 66),
            Qt.TextFlag.TextWordWrap,
            f"{index + 1}. {record['path']}\n"
            f"{record['width']} x {record['height']} | {record['status']}",
        )
        if not image.isNull():
            scaled = image.scaled(
                width - 24,
                height - 88,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            painter.drawImage(x + (width - scaled.width()) // 2, y + 78, scaled)
    painter.end()
    if not canvas.save(str(output)):
        raise OSError(f"Could not save {output}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source, output = args.source.resolve(), args.output.resolve()
    if not source.is_dir():
        parser.error("source must be a directory")
    if output == source or source in output.parents:
        parser.error("output must be outside the source directory")
    qt = QApplication.instance() or QApplication([])
    qt.setApplicationName("ExamGrader reference inventory")
    records, images = inspect(source)
    if not records:
        parser.error("source contains no non-hidden files")
    # Verify sources before publishing evidence. No writes ever target inputs.
    for record in records:
        if hashlib.sha256((source / record["path"]).read_bytes()).hexdigest() != record["sha256"]:
            raise RuntimeError("Source changed during inventory")
    output.mkdir(parents=True, exist_ok=True)
    (output / "manifest.json").write_text(
        json.dumps({"schema_version": 1, "files": records}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    write_contact_sheet(records, images, output / "contact-sheet.png")
    errors = sum(record["status"] != "decoded" for record in records)
    print(f"Inventoried {len(records)} files; decode errors: {errors}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
