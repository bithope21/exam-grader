"""Run the small local/offline Tkinter digit annotation workbench."""

from __future__ import annotations

import argparse
import string
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Any

from PIL import Image, ImageDraw, ImageTk

from tools.benchmark.annotation_workflow import (
    accept_label,
    atomic_save,
    counts,
    exclude_record,
    load_manifest,
    mark_bad_bbox,
    next_review_index,
    reset_record,
    set_bbox,
    source_crop_path,
)


class AnnotationApp:
    def __init__(self, root: tk.Tk, manifest_path: Path, annotator_id: str) -> None:
        self.root = root
        self.manifest_path = manifest_path.resolve()
        self.annotator_id = annotator_id
        self.manifest = load_manifest(self.manifest_path)
        self.index = next_review_index(self.manifest) or 0
        self.source_image: Image.Image | None = None
        self.display_scale = 1.0
        self.display_offset = (0, 0)
        self.drag_start: tuple[int, int] | None = None
        self.drag_preview: int | None = None
        self.photo: ImageTk.PhotoImage | None = None
        self.digit_photo: ImageTk.PhotoImage | None = None

        root.title("Exam Grader · Offline Digit Annotation")
        root.geometry("1100x760")
        root.minsize(900, 650)
        self.progress = tk.StringVar()
        self.provenance = tk.StringVar()
        self.detail = tk.StringVar()
        tk.Label(root, textvariable=self.progress, font=("TkDefaultFont", 14, "bold")).pack(
            anchor="w", padx=16, pady=(12, 2)
        )
        tk.Label(root, textvariable=self.provenance, justify="left").pack(
            anchor="w", padx=16, pady=(0, 2)
        )
        tk.Label(root, textvariable=self.detail, fg="#7a3e00", justify="left").pack(
            anchor="w", padx=16, pady=(0, 8)
        )

        content = tk.Frame(root)
        content.pack(fill="both", expand=True, padx=16)
        self.canvas = tk.Canvas(content, background="#eeeeee", highlightthickness=1)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<ButtonPress-1>", self._drag_start)
        self.canvas.bind("<B1-Motion>", self._drag_motion)
        self.canvas.bind("<ButtonRelease-1>", self._drag_end)

        side = tk.Frame(content, width=270)
        side.pack(side="right", fill="y", padx=(16, 0))
        tk.Label(side, text="Selected proposal", font=("TkDefaultFont", 12, "bold")).pack(
            pady=(8, 4)
        )
        self.digit_preview = tk.Label(side, background="white", width=220, height=220)
        self.digit_preview.pack(pady=4)
        tk.Label(
            side,
            text="ลากบนภาพด้านซ้ายเพื่อแก้ bbox\nB = bad_bbox · U = reset\n0–9 = label · X = exclude\n←/→ = ก่อนหน้า/ถัดไป · Esc = ออก",
            justify="left",
        ).pack(anchor="w", pady=12)
        button_row = tk.Frame(side)
        button_row.pack(fill="x", pady=4)
        tk.Button(button_row, text="← ก่อนหน้า", command=lambda: self._move(-1)).pack(
            side="left", expand=True, fill="x", padx=(0, 3)
        )
        tk.Button(button_row, text="ถัดไป →", command=lambda: self._move(1)).pack(
            side="left", expand=True, fill="x", padx=(3, 0)
        )
        tk.Button(side, text="X  Exclude / ambiguous", command=self._exclude).pack(
            fill="x", pady=3
        )
        tk.Button(side, text="B  Mark bad_bbox", command=self._bad_bbox).pack(
            fill="x", pady=3
        )
        tk.Button(side, text="U  Reset to needs_review", command=self._reset).pack(
            fill="x", pady=3
        )
        root.bind("<Key>", self._key)
        root.bind("<Left>", lambda _event: self._move(-1))
        root.bind("<Right>", lambda _event: self._move(1))
        root.bind("<Escape>", lambda _event: root.destroy())
        self._show()

    @property
    def record(self) -> dict[str, Any]:
        return self.manifest["records"][self.index]

    def _save(self) -> None:
        atomic_save(self.manifest_path, self.manifest)

    def _show(self) -> None:
        total_counts = counts(self.manifest)
        self.progress.set(
            f"Progress {total_counts['labeled'] + total_counts['excluded']} / "
            f"{total_counts['total']}   · labeled {total_counts['labeled']}   · "
            f"excluded {total_counts['excluded']}   · remaining {total_counts['remaining']}"
        )
        if not self.manifest.get("records"):
            self.provenance.set("ไม่มี records ใน manifest")
            return
        record = self.record
        self.provenance.set(
            f"source: {record.get('source_group')}  · page: {record.get('source_page')}  · "
            f"cell: {record.get('source_cell')}\n"
            f"proposal id: {record.get('annotation_id')}  · parent: {record.get('parent_sample_id')}"
        )
        reason = ", ".join(record.get("qc_reasons", []))
        self.detail.set(
            f"status: {record.get('label_status')}  · bbox: {record.get('bbox_status')}  · "
            f"layout: {record.get('layout_variant')}\n"
            f"QC: {reason or 'none'}"
        )
        self._show_source_and_bbox(record)
        self._show_digit_preview(record)

    def _show_source_and_bbox(self, record: dict[str, Any]) -> None:
        source_path = source_crop_path(self.manifest, self.manifest_path.parent, record)
        self.source_image = Image.open(source_path).convert("RGB")
        width, height = self.source_image.size
        self.root.update_idletasks()
        canvas_width = max(self.canvas.winfo_width(), 500)
        canvas_height = max(self.canvas.winfo_height(), 400)
        self.display_scale = min((canvas_width - 30) / width, (canvas_height - 30) / height)
        self.display_scale = max(self.display_scale, 1.0)
        display_size = (round(width * self.display_scale), round(height * self.display_scale))
        rendered = self.source_image.resize(display_size, Image.Resampling.NEAREST)
        draw = ImageDraw.Draw(rendered)
        bbox = record.get("bbox_annotated_px") or record.get("bbox_proposed_px")
        if bbox:
            color = "red" if record.get("bad_bbox") else (
                "#16803c" if record.get("bbox_status") == "corrected" else "#2455c3"
            )
            draw.rectangle(
                tuple(round(value * self.display_scale) for value in bbox),
                outline=color,
                width=max(2, round(self.display_scale / 2)),
            )
        self.photo = ImageTk.PhotoImage(rendered)
        self.canvas.delete("all")
        offset_x = max((canvas_width - rendered.width) // 2, 10)
        offset_y = max((canvas_height - rendered.height) // 2, 10)
        self.display_offset = (offset_x, offset_y)
        self.canvas.create_image(offset_x, offset_y, image=self.photo, anchor="nw")

    def _show_digit_preview(self, record: dict[str, Any]) -> None:
        path = self.manifest_path.parent / record["proposed_digit_path"]
        image = Image.open(path).convert("RGB")
        image.thumbnail((230, 230), Image.Resampling.NEAREST)
        self.digit_photo = ImageTk.PhotoImage(image)
        self.digit_preview.configure(image=self.digit_photo, text="")

    def _key(self, event: tk.Event[Any]) -> None:
        if event.char in string.digits:
            self._accept(int(event.char))
        elif event.char.lower() == "x":
            self._exclude()
        elif event.char.lower() == "b":
            self._bad_bbox()
        elif event.char.lower() == "u":
            self._reset()

    def _accept(self, digit: int) -> None:
        try:
            accept_label(self.manifest, self.record["annotation_id"], digit, self.annotator_id)
            self._save()
            self._advance_after_decision()
        except ValueError as error:
            messagebox.showwarning("Cannot accept label", str(error), parent=self.root)

    def _exclude(self) -> None:
        exclude_record(self.manifest, self.record["annotation_id"], self.annotator_id)
        self._save()
        self._advance_after_decision()

    def _bad_bbox(self) -> None:
        mark_bad_bbox(self.manifest, self.record["annotation_id"], self.annotator_id)
        self._save()
        self._show()

    def _reset(self) -> None:
        reset_record(self.manifest, self.record["annotation_id"], self.annotator_id)
        self._save()
        self._show()

    def _advance_after_decision(self) -> None:
        self.index = next_review_index(self.manifest, self.index + 1)
        if self.index is None:
            self.index = 0
            messagebox.showinfo("Annotation complete", "ไม่มี sample ที่ needs_review เหลืออยู่", parent=self.root)
        self._show()

    def _move(self, delta: int) -> None:
        if not self.manifest.get("records"):
            return
        self.index = (self.index + delta) % len(self.manifest["records"])
        self._show()

    def _canvas_to_source(self, x: int, y: int) -> tuple[int, int]:
        offset_x, offset_y = self.display_offset
        assert self.source_image is not None
        source_x = round((x - offset_x) / self.display_scale)
        source_y = round((y - offset_y) / self.display_scale)
        return (
            max(0, min(self.source_image.width, source_x)),
            max(0, min(self.source_image.height, source_y)),
        )

    def _drag_start(self, event: tk.Event[Any]) -> None:
        self.drag_start = (event.x, event.y)
        self.drag_preview = None

    def _drag_motion(self, event: tk.Event[Any]) -> None:
        if self.drag_start is None:
            return
        if self.drag_preview is not None:
            self.canvas.delete(self.drag_preview)
        self.drag_preview = self.canvas.create_rectangle(
            self.drag_start[0], self.drag_start[1], event.x, event.y, outline="#cc5500", width=3
        )

    def _drag_end(self, event: tk.Event[Any]) -> None:
        if self.drag_start is None:
            return
        start = self._canvas_to_source(*self.drag_start)
        end = self._canvas_to_source(event.x, event.y)
        self.drag_start = None
        if self.drag_preview is not None:
            self.canvas.delete(self.drag_preview)
            self.drag_preview = None
        bbox = [min(start[0], end[0]), min(start[1], end[1]), max(start[0], end[0]), max(start[1], end[1])]
        if bbox[2] - bbox[0] < 2 or bbox[3] - bbox[1] < 2:
            return
        try:
            set_bbox(self.manifest, self.record["annotation_id"], bbox, self.annotator_id)
            self._save()
            self._show()
        except ValueError as error:
            messagebox.showwarning("Cannot correct bbox", str(error), parent=self.root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--annotator-id", required=True)
    args = parser.parse_args()
    root = tk.Tk()
    AnnotationApp(root, args.manifest, args.annotator_id)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
