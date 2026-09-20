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
