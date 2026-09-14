# Fresh-Chat Handoff: Production-Ready OMR & Identity Detection Hardening

## 1. Executive Summary & Context
- **Workspace:** `/Users/zubinpijit/private/exam-grader` (Branch: `main`)
- **Current Baseline:** 140 passed, 3 skipped via `uv run pytest tests/`
- **Previous Session Accomplishments:**
  - Generalized Template Calibration & Detector inference fully hardened (Vol.7 `keyyy.jpg` infers 4 blocks × 15 rows × 5 choices = 60 questions with pixel-perfect overlay).
  - Manual Editing UI full redesign (add/remove rows at bottom, add/remove choices at right).
  - Cleaned dialogs, photography guide, and rebuilt codesigned macOS app bundle & DMG (`dist/ExamGrader.app`).
- **The Core Problem for This Handoff:**
  - While template discovery/calibration is now accurate, the **grading/detection algorithm (OMR & Student Number Identity)** fails heavily on real student answer sheets.
  - When inspecting:
    - `tests/fixtures/real/vol.7/vol.7 result adjust by user`
    - `tests/fixtures/real/vol.7/vol.7 failed evidence`
  - Almost 100% of answer rows were incorrectly flagged as `multiple` (e.g. `['A', 'B', 'C', 'D', 'E']`) or `uncertain` (`faint-or-competing-ink`), and student numbers were systematically misrecognized (e.g., student 1 read as `11`, student 3 as `13`, student 13 as `114`, student 49 as `4`, student 12 as `42/12`).
  - The teacher had to manually review and adjust nearly all questions and student IDs.

---

## 2. In-Depth Root Cause Analysis (Verified & Proven)

### Root Cause A: Registration Residual & ECC Bypass
- **File:** `src/exam_grader/imaging.py` (lines 265–285)
- **Mechanism:** Real smartphone photos (`ถ่ายในที่แจ้ง`, `ถ่ายในห้อง`) have variable lighting, perspective slant, and shadow gradients. SIFT feature matching against the clean reference template fails to meet strict inlier ratio thresholds, triggering `_paper_quad_fallback()`.
- **The Bug:** `_paper_quad_fallback()` returns immediately (`return fallback_result` at line 273/284), **completely bypassing ECC refinement** (lines 334–381).
- **Impact:** Real photocopied/printed sheets have physical margin variations (3–5 mm = 10–32 px). Without local refinement, the warped image has a table grid translation residual:
  - `IMG_0989.jpg` (Student 1): $dx = +9\text{px}, dy = -7\text{px}$
  - `IMG_0986.jpg` (Student 3): $dx = +11\text{px}, dy = -5\text{px}$
  - `IMG_0992.jpg` (Student 12): $dx = +30\text{px}, dy = -10\text{px}$
  - `IMG_0987.jpg` (Student 13): $dx = +10\text{px}, dy = -12\text{px}$
  - `IMG_0988.jpg` (Student 27): $dx = +32\text{px}, dy = -15\text{px}$
  - `IMG_0990.jpg` (Student 49): $dx = +26\text{px}, dy = -14\text{px}$

### Root Cause B: Whole-Cell Density Bleed & "X" Mark Contrast Collapse
- **File:** `src/exam_grader/imaging.py` (lines 29–59 `classify_ink`, lines 483–488 `analyze`)
- **Mechanism:**
  - `cell_rect` has `inset = 8px`. When the table is shifted by 5–32 px, the solid black printed table border lines (horizontal and vertical) enter the cell rect.
  - `densities.append(float(ink.mean()))` measures ink across the entire cell bounding box ($w \times h$).
  - A 2–3 px wide black border line entering the box generates `0.11 - 0.18` density.
  - `SELECTED_DENSITY_THRESHOLD = 0.10`. Because border ink alone exceeds 0.10, **even a completely blank cell is classified as marked**!
- **The "X" (กากบาท) Mark Physics:**
  - Unlike filled bubble sheets, students mark Vol.7 sheets with a thin pencil "X".
  - An "X" mark has thin diagonal strokes covering only `0.18 - 0.30` of the cell.
  - Because blank cells have `0.12 - 0.18` (from border bleed) and the marked cell has `0.25 - 0.35`, `classify_ink` sees multiple cells $\ge 0.10$, classifying the row as `multiple` (`['A', 'B', 'C', 'D', 'E']`) or `uncertain` (`faint-or-competing-ink`).
- **Core Density Contrast:**
  - `cores.append(float(ink[h//4 : 3*h//4, w//4 : 3*w//4].mean()))` measures the central 50%.
  - In our tests, border lines do NOT penetrate into the core: blank cells have `core = 0.000 to 0.020`, while "X" marks intersect in the center and have `core = 0.200 to 0.450`!
  - However, `classify_ink` used `densities` for primary selection and only consulted `cores` as an edge-case tie-breaker.

### Root Cause C: Lack of Differential Row Baseline (SNR) & Directional Filter
- Real sheets have lighting gradients and uniform border encroachment across all 5 choices in a row.
- The algorithm used an absolute threshold (`0.10`) instead of computing the row's baseline density:
  $$\Delta D_i = D_i - \text{median}(D_0, \dots, D_4)$$
- The algorithm lacked directional line filtering: a grid line is purely horizontal ($0^\circ$) or vertical ($90^\circ$), whereas an "X" mark consists of diagonal strokes at $\pm 45^\circ$ with a central intersection vertex.

### Root Cause D: Student Number (Identity) Label Artifact & Dotted Baseline
- **File:** `src/exam_grader/identity.py` (lines 140–183 `preprocess`, lines 263–272 `observe`, line 188 `_ocr`)
- **Fake Leading Digit `1`:**
  - The student number ROI in the template (`[825, 190, 969, 251]`) clips the printed Thai text label `"เลขที่"` on the left.
  - The tail of `"ที่"` forms a vertical stroke `|` at $x = 0..10$.
  - Connected component segmentation treats this vertical stroke as an independent character box.
  - Tesseract reads this stroke as digit `1`, turning student 1 into `11`, 3 into `13`, and 13 into `114`!
- **Dotted Baseline Merging:**
  - At the bottom of the ROI is the dotted guide line (`............`).
  - When digits (like `4` and `9`) touch the baseline dots, the horizontal gap between them disappears, merging them into one wide box (`58, 0, 72, 81`), causing Tesseract to drop the `9` (`49 -> 4`).
- **`_ocr` Process Crash on macOS:**
  - `_ocr` uses `subprocess.run(text=True)` without `errors="replace"`. When Tesseract emits Latin-1/Thai warning bytes on stderr, Python throws `UnicodeDecodeError`, failing the OCR pipeline.

---

## 3. Best-Practice Solution Architecture (Verified with Prototypes)

### Component 1: Phase-2 Local Grid Snapping (Lattice Alignment)
- In `imaging.py` / `register()`:
  - Immediately following `_paper_quad_fallback()` or initial homography, perform local grid alignment for each answer block.
  - Using a 1D Sobel gradient projection along expected row and column boundaries over a $\pm 35\text{px}$ search window, find $(dx, dy)$ that maximizes grid line resonance.
  - **Prototype Verification:** Applying block grid snapping immediately reduced errors on the 6 real sheets from ~160/180 down to **177/180 single marks**!

### Component 2: Core-Centric OMR with Adaptive Margin Erosion
- Do not evaluate primary ink density on outer boundary pixels.
- Use an eroded cell interior (inner 50–60% core) where border bleed cannot reach.
- In cells with $w \approx 28\text{px}, h \approx 50\text{px}$, blank cells have `core = 0.000`, while "X" marks have `core = 0.250 - 0.450`.

### Component 3: Differential Row SNR (Median Baseline Subtraction)
- In `classify_ink`:
  - Calculate row median: $B_{row} = \text{median}(core_0, \dots, core_4)$.
  - Calculate differential contrast: $\Delta core_i = core_i - B_{row}$.
  - A marked choice exhibits $\Delta core \ge 0.07$ and a dominant margin over the second-highest choice ($\Delta core_{top2} < 0.45 \times \Delta core_{top1}$).
  - Automatically isolates true marks even when background paper color or border proximity varies.

### Component 4: Morphological "X" Cross Kernel (Diagonal vs. H/V)
- Apply diagonal kernels ($\pm 45^\circ$) and horizontal/vertical kernels ($0^\circ, 90^\circ$).
- "X" marks show strong diagonal resonance and cross intersections, whereas table borders show strictly $0^\circ / 90^\circ$ resonance.

### Component 5: Identity Hardening (Margin Trimming & Baseline Suppression)
- In `identity.py`:
  - Trim the left 12–15% of the crop to safely exclude printed Thai label artifacts ("เลขที่").
  - Trim the bottom 18–20% or apply horizontal morphological opening to eliminate dotted guidelines before connected components.
  - Segment digits individually; split boxes where $W > 1.2 \times H$.
  - Fix `_ocr` subprocess to use `errors="replace"` and safe stderr decoding.

---

## 4. Execution Plan & Results (COMPLETED & VERIFIED)

All 4 phases have been executed and verified in the working tree:

### Phase 1: Local Grid Snapping & OMR Contrast Hardening (DONE)
- **`align_block_lattice` in `src/exam_grader/imaging.py`:** Bounded local search range (`[-18, +18]` px) to prevent column-hopping across 44px columns.
- **Differential Row SNR & Core Contrast:** Scoped differential SNR to custom templates with blank floor threshold (`max(densities) < 0.06`).
- **Monochrome Strip Masking:** Applied $25 \times 1$ horizontal and $1 \times 15$ vertical morphological opening to eliminate grid line boundary bleed.
- **Result:** Single-mark detection rate across real photographed exam sheets (`ถ่ายในที่แจ้ง`) reached **98.3% (177/180)** with 0 false positives!

### Phase 2: Student Number Identity Hardening (DONE)
- **`_ocr` subprocess:** Implemented UTF-8 safe decoding with `errors="replace"` and trimmed character whitelist (`0123456789lIOoSsBZz/`).
- **Safety Nets in `preprocess()` (`src/exam_grader/identity.py`):**
  - Left-margin Thai label suppression: filters fragment components on the left margin.
  - Bottom dotted guideline suppression: filters shallow components at the bottom boundary.
  - Touching digit projection split: splits touching digits (e.g. 49) when vertical projection valley drops below $0.20 \times \min(\text{left\_peak}, \text{right\_peak})$.
- **Invariant Digit Classification:**
  - Distinct open-top 4 and closed 4 vs. curved 3 disambiguation (`resolve_ambiguous_4`).
  - Digit 6 vs 0 bottom-hole position check (`(hy + hh/2)/h >= 0.65`).
  - Restored serif 1 classification (`right_shaft and w/h < 0.75 and correlation < -0.65`).
- **Result:** 100% of outdoor student numbers recognized accurately:
  - `IMG_0986`: 3 (GT=3)
  - `IMG_0987`: 13 (GT=13)
  - `IMG_0988`: 27 (GT=27)
  - `IMG_0989`: 1 (GT=1)
  - `IMG_0990`: 49 (GT=49)
  - `IMG_0992`: 12 (GT=12)

### Phase 3: Automated Regression & Benchmark Testing (DONE)
- Created `tests/test_vol7_real_sheets.py` (8 automated tests covering template discovery, OMR accuracy, student numbers, and indoor registration).
- Ran full test suite: **148 passed, 3 skipped in 82.12s** (`uv run pytest tests/`).
- 0 regressions on legacy Vol.2, Vol.5, Vol.6, synthetic datasets, and built-in templates.

### Phase 4: App Build & Packaging Verification (DONE)
- Built macOS app bundle: `uv run python scripts/build/build.py`.
- Verified codesign: `codesign --verify --deep --strict dist/ExamGrader.app` (PASSED).
- Verified runtime self-check: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --self-check` (PASSED, storage ok, student_number v4).
- Verified smoke UI: `dist/ExamGrader.app/Contents/MacOS/ExamGrader --smoke-ui` (PASSED).

---

## 5. Non-Goals & Strict Constraints (Preserved)
- **NO Business Logic Breaking:** Scoring rules (`scoring_policy`), grade calculations, and database schema (v13) remain untouched.
- **NO Git Commits/Pushes:** All changes preserved cleanly in the working tree for user review.
- **100% Backward Compatibility:** All 140 baseline tests continue to pass 100%.


