# Student-number dataset and benchmark

## Current checkpoint — 2026-09-20

The current Student Number Recognition round is closed. The shipped recognizer
is review-only: auto-accept remains disabled and `wrong auto-accept = 0`.
Source/package evidence is separate from Product Owner native UAT.

Verified real-sheet results:

- Vol.8/9: exact `20/22`, 1-digit `8/8`, 2-digit `12/14`, candidate/review
  visibility `21/22`.
- Vol.10: exact `15/22`, 1-digit `6/9`, 2-digit `9/13`, candidate/review
  visibility `18/22`.
- Product Owner UAT confirms materially better prefill. Correct examples
  include `15`, `16`, `19`, and `21`; remaining visible errors include
  `14→191`, `17→11`, `18→98`, `20→79`, and `22→92`.
- Windows native UAT remains pending. OMR, document crop/registration,
  grading/export, assessment indicators, rooms, and unrelated business logic
  were not changed in this round.

The annotation-v3 manifest has 200 proposals, 198 accepted labels and 2
excluded records. All 198 evaluated digits overlap the current seed training
source; writer identity is unknown and the manifest says
`training_allowed=false`. Therefore v1 `140/198` and v2 `142/198` are
training-overlap evidence only, not held-out accuracy. Any next recognizer
must first establish a sheet/writer-disjoint held-out protocol and preserve
Vol.8/9/10 provenance before training or tuning.

The next authorized direction is a supplemental whole-ROI/sequence recognizer
experiment. Benchmark the current segmentation→digit-classifier path first;
retain it as fallback; do not hard-code Vol.10; and do not use evaluation data
for tuning. See the current prompt at the top of `docs/NEXT_CHAT_HANDOFF.md`
and the detailed evidence at
`docs/evidence/student-number-recognition-20260920.md`.

This repository keeps student-number recognition evidence separate from the
runtime recognizer and from OMR/crop/registration acceptance.

## PDF seed extraction

The supplied `number handwriting.pdf` is a local/private source and is not
copied into Git. Extract it to an external directory:

```sh
rtk proxy env PYTHONPATH=. .venv/bin/python tools/benchmark/extract_number_handwriting_dataset.py \
  --pdf "/Users/zubinpijit/Downloads/number handwriting.pdf" \
  --output /private/tmp/exam-grader-number-handwriting-seed
```

The output contains:

- `manifest.json` with the PDF SHA-256, renderer version, normalized geometry,
  privacy status, split policy and provenance.
- 100 page-1 sequence crops labeled `00` through `99` from the grid position.
  These are seed sequence labels, not automatically trusted digit bounding
  boxes.
- Rendered pages 2-11 as a review queue. Arithmetic answers, corrections,
  crossed-out marks, blanks and student identities are deliberately not
  auto-labeled.

The PDF is one source sheet/writer, so its samples are `seed_only`, not a
train/validation/test split. Digit segmentation requires a separate visual
annotation step before model training.

## Visual QC and annotation worklist

Create an external annotation worklist after extraction:

```sh
rtk proxy env PYTHONPATH=. .venv/bin/python tools/benchmark/prepare_digit_annotation.py \
  --seed-manifest /private/tmp/exam-grader-number-handwriting-seed/manifest.json \
  --output /private/tmp/exam-grader-number-handwriting-annotation
```

This creates 200 fixed-midline digit proposals and a sequence contact sheet.
They are deliberately marked `needs_review`; the midpoint is only a proposal
and must not be treated as a trusted digit bounding box. Each eventual accepted
annotation must record the annotator, timestamp, corrected bounding box, label,
and decision reason. The accepted bbox is recorded separately from the original
proposal, whether it was visually confirmed or corrected. Empty/low-ink or border-touch anomalies stay in the queue
for explicit review rather than being silently dropped. The worklist remains
`training_ready=false` until the annotation audit and writer/sheet split are
completed. The seed visibly contains a layout variant for `06`-`09` where the
leading zero is not written; those proposals have no automatic digit label and
must be resolved explicitly during annotation.

Open the offline workbench with an explicit annotator id:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  tools/benchmark/annotate_digit_proposals.py \
  --manifest /private/tmp/exam-grader-number-handwriting-annotation-v3/annotation_manifest.json \
  --annotator-id "product-owner"
```

Keys `0`-`9` accept a label, `X` excludes/marks ambiguous, arrows navigate,
`B` marks `bad_bbox`, and dragging a rectangle on the source crop corrects the
bbox. `U` resets the current record. Every decision is saved immediately with
an atomic replace and appended to `audit_log`; reopening the same manifest
resumes at the first remaining `needs_review` record. Original proposal/crop
files are never modified.

After annotation, export only accepted samples:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  tools/benchmark/build_training_ready_manifest.py \
  --annotation-manifest /private/tmp/exam-grader-number-handwriting-annotation-v3/annotation_manifest.json \
  --output /private/tmp/exam-grader-number-handwriting-training-ready.json
```

The validator rejects duplicate ids, missing crops, labels outside `0`-`9`,
unresolved `bad_bbox`, missing annotation provenance, and any training-ready
manifest containing `excluded` or `needs_review`. The exported manifest is
label-ready for the explicitly authorized internal seed split, but remains
`seed_only` with `generalization_claim_allowed=false`; Vol.8/Vol.9 must remain
independent held-out evidence.

## Seed model and held-out comparison

Train the small KNN/centroid comparison from the accepted seed crops:

```sh
rtk proxy env PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. .venv/bin/python \
  tools/benchmark/train_digit_model.py \
  --manifest /private/tmp/exam-grader-number-handwriting-training-ready-v2.json \
  --output-dir /private/tmp/exam-grader-digit-model-v2
```

The selected artifact is bundled into the runtime as a review-only candidate.
Compare it to the legacy path with `--no-digit-model`; both runs must use the
same saved-registration held-out corpus. The current comparison improved exact
whole-number accuracy from `5/22` (`22.7%`) to `7/22` (`31.8%`), while review
remained `22/22` and wrong auto-accept remained `0`. This is provisional
evidence only; confidence is a conservative review score, not a probability,
and auto-accept remains off.

## Teacher-confirmed real benchmark corpus

Build a manifest from the existing teacher-confirmed Vol.8/Vol.9 exports. This
uses saved transforms only to isolate identity evaluation from the current
geometry blocker; it does not rerun or change registration:

```sh
rtk proxy env PYTHONPATH=. .venv/bin/python tools/benchmark/build_identity_corpus.py \
  --export vol8="tests/fixtures/real/vol.8/2569_ป.1_1_math_vol8 lunar ultra_30q/ผลการตรวจ/2026-09-14_205501/_system/results.json" \
  --source-root vol8="tests/fixtures/real/vol.8" \
  --export vol9="tests/fixtures/real/vol.9/2026-09-14_214703/_system/results.json" \
  --source-root vol9="tests/fixtures/real/vol.9" \
  --output /private/tmp/exam-grader-identity-corpus.json
```

Every row must be `teacher_confirmed`, have a matching immutable source hash,
and remain `held_out`. No row is training data. Writer identity is currently
unknown.

Run the current identity baseline:

```sh
rtk proxy env PYTHONPATH=. .venv/bin/python tools/benchmark/identity_labeled_benchmark.py \
  --manifest /private/tmp/exam-grader-identity-corpus.json \
  --output /private/tmp/exam-grader-identity-baseline.json
```

The report distinguishes primary exactness, candidate visibility, review rate,
auto-accept coverage, wrong auto-accept count, timing and deterministic 95%
bootstrap intervals. Scores are not probabilities. Auto-accept remains off.

## Promotion gate

The current Product Owner authorization permits internal seed training from the
198 accepted records, but this seed alone cannot support a generalization claim.
Any future recognizer still needs independent held-out evidence, hard-pair error
slices, model/config/hash provenance, and a Product Owner-approved acceptable
auto-accept error and minimum coverage. Until those gates are met, the runtime
output remains a review-required candidate, not a forced identity.
