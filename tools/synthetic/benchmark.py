"""Seeded synthetic probe. Results are NOT real-sheet accuracy estimates."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import cv2
import numpy as np

from exam_grader.imaging import analyze, reference_image

# Independently written mark centers, visually checked against the reference.
# Deliberately do not call detector cell_rect: expected truth never comes from OMR.
X = [[74, 107, 139, 172, 204], [274, 307, 339, 371, 403],
     [473, 505, 538, 570, 602], [671, 703, 735, 767, 798]]
Y = [244, 276, 309, 341, 374, 406, 438, 471, 503, 535, 568, 600, 632, 664, 697]


def generate(seed: int):
    rng = np.random.default_rng(seed)
    image = reference_image()
    truth = []
    for question in range(60):
        kind = int(rng.integers(0, 10))
        choices = [] if kind == 0 else sorted(rng.choice(5, 2 if kind == 1 else 1, replace=False).tolist())
        truth.append({"selected": ["ABCDE"[choice] for choice in choices],
                      "classification": "blank" if not choices else "multiple" if len(choices)>1 else "single_mark"})
        for choice in choices:
            x, y = X[question//15][choice], Y[question % 15]
            cv2.line(image,(x-7,y-7),(x+7,y+7),(0,0,0),2)
            cv2.line(image,(x+7,y-7),(x-7,y+7),(0,0,0),2)
    return image, truth


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",type=Path,required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    results=[]
    for seed in (101,202,303):
        image,truth=generate(seed)
        center=(image.shape[1]/2,image.shape[0]/2)
        rotation=cv2.getRotationMatrix2D(center,3,1)
        variants={"clean":image,
                  "rotate3":cv2.warpAffine(image,rotation,(image.shape[1],image.shape[0]),borderValue=(255,255,255)),
                  "blur":cv2.GaussianBlur(image,(5,5),1),
                  "dark":np.clip(image.astype(float)*.7,0,255).astype(np.uint8),
                  "crop":image[200:600,100:600]}
        for variant,pixels in variants.items():
            data=cv2.imencode(".png",pixels)[1].tobytes()
            name=f"seed-{seed}-{variant}.png"
            (args.output/name).write_bytes(data)
            started=time.perf_counter()
            try:
                prediction=analyze(data)
                exact=sum(a["selected"]==b["selected"] and a["classification"]==b["classification"]
                          for a,b in zip(prediction["answers"],truth,strict=True))
                entry={"suggestion_exact":exact,"questions":60,"status":"review_required"}
            except ValueError as error:
                entry={"status":"rejected","reason":str(error)}
            results.append({"file":name,"seed":seed,"variant":variant,
                            "sha256":hashlib.sha256(data).hexdigest(),
                            "seconds":round(time.perf_counter()-started,4),"truth":truth,**entry})
    report={"kind":"synthetic_probe_only","auto_accept_coverage":0,
            "warning":"All variants derive from one screenshot; no real-world accuracy claim",
            "results":results}
    (args.output/"benchmark.json").write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding="utf-8")
    print(json.dumps([{k:v for k,v in row.items() if k not in {"truth","sha256"}} for row in results],ensure_ascii=False))


if __name__=="__main__":
    main()
