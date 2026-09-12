"""Read-only comparison against teacher export; no labels enter recognition."""

import json
from pathlib import Path

import cv2
import numpy as np

from exam_grader.imaging import analyze, cell_rect, classify_ink


def main():
    root = Path("tests/fixtures/real/vol.2")
    truth_path = next(
        Path("/Users/zubinpijit/Documents/ExamGrader/2569_ม.1_6_math_test2 แก้เลขที่ auto_40q").rglob(
            "results.json"
        )
    )
    truth = json.loads(truth_path.read_text())
    targets = {r["source"]["original_name"]: r["answers"] for r in truth["results"]}
    targets["key.jpg"] = truth["key"]["answers"]
    for path in sorted(root.glob("*.jpg")):
        data = analyze(path.read_bytes())
        gray = cv2.cvtColor(data["aligned"], cv2.COLOR_BGR2GRAY).astype(np.float32)
        background = cv2.GaussianBlur(gray, (0, 0), 9)
        for threshold in (16,):
            # Relative contrast makes exposure compensation local, including shadows.
            feature = (background - gray) * 180 / np.maximum(background, 30)
            wrong = []
            for q, expected in enumerate(targets[path.name], 1):
                densities, cores = [], []
                for c in range(5):
                    x, y, w, h = cell_rect(q, c)
                    ink = feature[y : y + h, x : x + w] > threshold
                    densities.append(float(ink.mean()))
                    cores.append(float(ink[h // 4 : 3 * h // 4, w // 4 : 3 * w // 4].mean()))
                selected, state, _ = classify_ink(densities, cores)
                actual = selected[0] if state == "single_mark" else state
                if actual != expected:
                    wrong.append(
                        (
                            q,
                            expected,
                            actual,
                            [round(d, 2) for d in densities],
                            [round(c, 2) for c in cores],
                        )
                    )
            print(path.name, threshold, len(wrong), wrong, flush=True)


if __name__ == "__main__":
    main()
