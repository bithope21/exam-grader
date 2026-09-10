import hashlib
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtGui import QImage

SCRIPT = Path(__file__).resolve().parents[1] / "tools/inspect/reference_inventory.py"


def run_inventory(source, output):
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--source", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
    )


def test_inventory_repeatable_and_reports_corrupt_input(tmp_path):
    source = tmp_path / "ต้นฉบับ"
    source.mkdir()
    image = QImage(13, 17, QImage.Format.Format_RGB32)
    image.fill(0xFFFFFFFF)
    assert image.save(str(source / "ภาพ.png"))
    (source / "broken.png").write_bytes(b"not an image")
    before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}
    output = tmp_path / "evidence"
    assert run_inventory(source, output).returncode == 1
    first = (output / "manifest.json").read_bytes()
    records = json.loads(first)["files"]
    assert records[0]["status"] == "decode_error"
    assert (records[1]["width"], records[1]["height"]) == (13, 17)
    assert run_inventory(source, output).returncode == 1
    assert (output / "manifest.json").read_bytes() == first
    assert before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir()}


def test_inventory_cannot_write_into_sources(tmp_path):
    assert run_inventory(tmp_path, tmp_path / "output").returncode == 2
    assert not (tmp_path / "output").exists()
