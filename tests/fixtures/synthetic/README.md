# Synthetic Answer Sheet Dataset Fixtures

> [!WARNING]
> **SYNTHETIC / PROVISIONAL FIXTURES ONLY**  
> This fixture set is generated deterministically for testing and benchmarking Codex OMR pipeline capabilities. It is **NOT** a replacement for real-world accuracy benchmarks, **MUST NOT** be used to train digit recognition models, and does **NOT** constitute a production accuracy claim.

---

## Directory Overview

- **`expected/`**: Contains 3 mock answer keys (`answer_keys.json`) along with rendered answer key sheet images (`key_01.png`, `key_02.png`, `key_03.png`) for testing answer key image import workflows.
- **`clean/`** (15 sheets): Perfect/zero/random score sheets, all A–E sheets, alternating patterns, single blank answers, and valid student numbers.
- **`degraded/`** (20 sheets): Faint/heavy/off-center marks, rotation (±1°, ±3°, ±5°), lighting variations, low contrast, shadows, Gaussian blur, motion blur, and JPEG compression.
- **`edge_cases/`** (20 sheets): Double marks, checkmarks (`✓`), slashes (`/`), scribbles/corrected answers, solid filled bubbles (edge case), rotation ±10°, perspective skew, mild crops/partial sheets, duplicate student numbers, missing student numbers, and unreadable scribbled student numbers.
- **`manifest.json`**: Comprehensive ground truth dataset manifest mapping every fixture image to its `student_no`, 60 question answers, `expected_score`, `expected_review_flags`, `seed`, and applied `transforms`.

---

## Seed Strategy & Reproducibility

The dataset is generated deterministically using NumPy PRNG (`np.random.default_rng(seed)`).
Default seed: `42`.

Rerunning the generator script with seed `42` reproduces byte-for-byte identical images and manifests.

Byte identity is guaranteed for repeated runs in the same pinned runtime. Rasterized text/anti-aliasing can differ across Qt/PySide6/OpenCV/font versions, so do not compare checked-in PNGs byte-for-byte against a different environment; compare manifest/truth and run the same-environment determinism test.

---

## Regeneration Command

To regenerate or update the dataset, run:

```bash
PYTHONPATH=. .venv/bin/python tools/synthetic/generate_dataset.py --seed 42 --output-dir tests/fixtures/synthetic
```

To run the verification test suite:

```bash
PYTHONPATH=. .venv/bin/python -m pytest tests/test_synthetic_dataset.py
```
