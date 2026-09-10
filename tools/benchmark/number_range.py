"""Generated number coverage, explicitly not unseen handwriting accuracy."""
import json
from pathlib import Path

import cv2
import numpy as np

from exam_grader.identity import observe
from exam_grader.imaging import reference_image, template


def main():
    out = Path("docs/evidence/automation/number-range")
    out.mkdir(parents=True, exist_ok=True)
    geometry = template()
    x1, y1, x2, y2 = [v * 4 for v in geometry["student_number_roi"]]
    reference = cv2.resize(reference_image(), None, fx=4, fy=4)
    matrix = np.diag([0.25, 0.25, 1.0]).tolist()
    records = []
    for number in range(1, 51):
        pixels = reference.copy()
        pixels[y1:y2, x1:x2] = 255
        cv2.putText(pixels, str(number), (x1 + 24, y1 + 100), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (0, 0, 0), 5, cv2.LINE_AA)
        data = cv2.imencode(".png", pixels)[1].tobytes()
        result = observe(data, matrix, diagnostics_dir=out / str(number))
        records.append({"truth": str(number), "candidate": result["candidate"], "correct": result["candidate"] == str(number), "observation": result})
        print(number, result["candidate"], result["candidates"], flush=True)
    # Compose existing 1/4 real glyphs as a segmentation stress test. These are
    # reused glyphs, not independently written real numbers or validation data.
    glyphs = {}
    for number, stem in (("1", "IMG_0791"), ("4", "IMG_0794")):
        path = Path("docs/evidence/polish/final-offscreen-final/numbers") / stem / "number_roi_processed.png"
        image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        ys, xs = np.where(image == 0)
        glyphs[number] = image[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    for number in ("14", "41"):
        pixels = reference.copy()
        pixels[y1:y2, x1:x2] = 255
        x = x1 + 24
        for digit in number:
            glyph = glyphs[digit]
            h, w = glyph.shape
            pixels[y1 + 20:y1 + 20 + h, x:x + w] = cv2.cvtColor(glyph, cv2.COLOR_GRAY2BGR)
            x += w + 15
        result = observe(cv2.imencode(".png", pixels)[1].tobytes(), matrix, diagnostics_dir=out / f"composite-{number}")
        records.append({"truth": number, "kind": "composed-existing-handwriting", "candidate": result["candidate"], "correct": result["candidate"] == number, "observation": result})
        print("composite", number, result["candidate"], flush=True)
    report = {"kind": "generated developer test; not real handwriting accuracy", "records": records,
              "correct": sum(r["correct"] for r in records), "total": len(records)}
    (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
