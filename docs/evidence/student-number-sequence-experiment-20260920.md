# Student Number Whole-ROI Sequence Experiment — Protocol Freeze

Status: protocol and baseline frozen before prototype work.

## Scope and invariants

This experiment is limited to Student Number Recognition prefill. The existing
registration, crop, OMR, grading/export, assessment-indicator, room, UI, and
business-logic paths are outside scope. The production recognizer remains the
segmentation → digit-classifier path, review-required, with auto-accept off.

The supplied screenshots are native manual-UAT context only. They are not
training labels and are not used as benchmark records.

## Frozen baseline

- Repository: `/Users/zubinpijit/private/exam-grader`
- Branch: `feat/assessment-indicators-multi-room`
- Baseline commit: `f0dd998` (`docs: close student recognition round`)
- Pipeline: `student-number-adaptive-roi-v8`
- Primary model: bundled `student_number_digit_model.npz`,
  SHA-256 `5addf658d9a2090d8423ab98311e098e4398b20df521dd44066f2c865be6e9b9`
- Supplemental digit model remains part of the unchanged baseline runtime;
  its SHA-256 is
  `2789388ff11d5a8947f681ca15045128c7201f45b48a1581b64690ffa47b175e`.
- Auto-accept: disabled; every benchmark record is review-required.

The baseline was reproduced with the unchanged source and a newly built
provenance manifest from the saved teacher-confirmed exports:

```text
tools/benchmark/build_identity_corpus.py
tools/benchmark/identity_labeled_benchmark.py --review-only
```

The disposable manifest is
`/private/tmp/exam-grader-sequence-baseline-manifest-20260920.json` and the
baseline report is
`/private/tmp/exam-grader-sequence-baseline-20260920.json`.

| Corpus | Sheets | Exact top-1 | 1-digit | 2-digit | Truth visible | Review | Wrong auto-accept | Mean latency |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Vol.8 | 10 | 9/10 | 4/4 | 5/6 | 9/10 | 10/10 | 0 | 0.6227 s |
| Vol.9 | 12 | 11/12 | 4/4 | 7/8 | 12/12 | 12/12 | 0 | 0.6391 s |
| Vol.8 + Vol.9 | 22 | 20/22 | 8/8 | 12/14 | 21/22 | 22/22 | 0 | 0.6252 s |
| Vol.10 | 22 | 15/22 | 6/9 | 9/13 | 18/22 | 22/22 | 0 | 0.6186 s |
| All | 44 | 35/44 | 14/17 | 21/27 | 39/44 | 44/44 | 0 | 0.6251 s |

The baseline failure examples in Vol.10 include `14→191`, `18→98`,
`20→79`, and `22→92`; these are evaluation observations, not hard-coded
cases.

## Held-out protocol

The benchmark corpus contains 44 teacher-confirmed records from the saved
Vol.8, Vol.9, and Vol.10 exports. Source bytes and saved registration matrices
are hash-checked before evaluation. No source sheet is duplicated across
records. These volumes are never used for sequence training, augmentation,
feature selection, threshold selection, or ranking-rule tuning.

The claim is deliberately limited to **sheet/volume-disjoint evaluation;
writer generalization unknown**. The result exports do not identify writers,
so writer-disjoint generalization cannot be claimed.

The local sequence seed is separate support data: 100 unique whole-ROI crops
labelled `00`–`99`, from one source PDF page/group with writer identity unknown.
Its source manifest says the seed is not sufficient for leakage-free
train/validation/test splitting. It may be used only as seed-support training
for this bounded prototype; it is never used as held-out evidence. The
annotation-v3 digit worklist is also seed-only and is not an evaluation set.

## Acceptance gates

The supplemental path must be compared on the same 44 records and must report:

- exact top-1/prefill, separated into 1-digit and 2-digit records;
- truth visibility in top-k candidates;
- per-record failure attribution where evidence supports it;
- latency and model size;
- disagreement and hybrid-ranking outcomes;
- unchanged review-required and wrong-auto-accept counts.

For complexity to be earned, Vol.8/9 must not materially regress and Vol.10
two-digit accuracy should improve clearly from the frozen `9/13` baseline,
with `11–12/13` as the requested target. If the prototype does not meet that
bar without held-out tuning, it will remain an experiment only and will not be
integrated or bundled.

## Prototype result

The prototype is implemented only in
`tools/benchmark/whole_roi_sequence.py`; it is not called by the production
identity runtime. It normalizes the complete ROI ink blob and predicts the two
output positions from compact centroid features. It does not require the
existing connected-component digit boxes.

The seed manifest contains 100 two-digit sequence crops (`00`–`99`) from one
source page/group. It contains no independent writer-diverse sequence set and
no usable one-digit sequence training set, so the sequence path was evaluated
as a two-digit supplemental experiment only. One-digit production candidates
remain on the frozen baseline path.

The direct sequence result was poor and is not eligible for integration:

| Path | Vol.8/9 exact | Vol.10 exact | Vol.10 2-digit | Vol.10 truth visible | Mean recognizer-only latency | Model size |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Frozen baseline | 20/22 | 15/22 | 9/13 | 18/22 | 0.618–0.639 s/sheet | existing bundled models |
| Whole-ROI sequence top-1 | 0/22 | 2/22 | 2/13 | 4/22 | 0.0020 s/sheet | 171,520 bytes / 167.5 KiB |

The fixed, predeclared hybrid rule was: promote the sequence top-1 only when
the frozen baseline emitted more than two digits; otherwise keep the baseline
top-1. This preserved Vol.8/9 at `20/22` exact and improved Vol.10 only to
`16/22`, with `10/13` two-digit exact and `20/22` truth visible. It did not
reach the requested `11–12/13` two-digit target, so the sequence model did not
earn production complexity and was not integrated, bundled, or allowed to
change runtime behavior.

Failure inspection is consistent with a data-diversity bottleneck rather than
a proven package/runtime issue:

- `IMG_1189` truth `14`: sequence top-1 recovered `14` from baseline `191`,
  a useful over-split rescue;
- `IMG_1193` truth `18`: sequence top-1 was `18`, but the conservative rule
  retained baseline `98` because both were two-digit and the sequence score is
  not calibrated;
- `IMG_1194` truth `20` remained baseline `79`, while sequence proposed `90`;
- `IMG_1196` truth `22` remained baseline `92`, while sequence proposed `11`.

The full per-record report is disposable at
`/private/tmp/exam-grader-whole-roi-sequence-20260920-final.json`. The model
was not copied into `src/exam_grader/resources`, so package impact is zero.
Auto-accept remains disabled and wrong auto-accept remains `0`.

Conclusion: do not integrate this sequence path. The remaining bottleneck is
primarily training-data diversity/sequence-domain mismatch, with classifier or
ranking ambiguity still present in the difficult two-digit cases. A future
attempt needs authoritative writer-diverse whole-ROI labels before another
architecture or held-out tuning cycle; Vol.8/9/10 must remain evaluation-only.
