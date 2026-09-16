# Student-number dataset and benchmark

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
label-ready only: it remains `seed_only` and `training_allowed=false` until a
writer/sheet-grouped split is created.

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

Do not train on corrections or promote a model from this seed alone. A future
recognizer needs writer/sheet-grouped train/calibration/held-out splits, an
independent label audit, hard-pair error slices, model/config/hash provenance,
and a Product Owner-approved acceptable auto-accept error and minimum coverage.
If those gates are not met, the correct output remains a review-required
candidate, not a forced identity.
