# Student Number Recognition — 2026-09-20 checkpoint

This is a Student Number Recognition-only evidence checkpoint. OMR,
document crop/registration, grading/export, assessment indicators, rooms, and
unrelated UI/business logic were not changed by this work. Raw recognition
observations remain persisted as immutable evidence; batch assistance is a
deep-copied, review-only effective ranking.

## Recognition result

The current recognizer is `student-number-adaptive-roi-v8` with the bundled
v1 binary/L2 digit model plus the v2 gray/cosine supplemental model. Auto-accept
is disabled and every measured sheet remains review-required.

| Corpus | Exact top-1 | 1-digit | 2-digit | Truth visible in candidates/review | Review | Auto-accept / wrong |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Vol.8 + Vol.9, 22 sheets | 20/22 (90.9%) | 8/8 | 12/14 | 21/22 (95.5%) | 22/22 | 0 / 0 |
| Vol.10, 22 sheets | 15/22 (68.2%) | 6/9 | 9/13 (69.2%) | 18/22 (81.8%) | 22/22 | 0 / 0 |

Vol.10 two-digit top-1 improved from the prior round's 6/13 to 9/13;
overall exact improved from 12/22 to 15/22. The Vol.8/9 regression corpus
remained at 20/22, including 12/14 two-digit and 21/22 visibility. This is a
meaningful but incomplete generalization result, not a release or native UAT
claim.

The Vol.10 remaining errors are mixed: `IMG_1189` is an over-split three-box
read for truth `14`, `IMG_1193` is incomplete two-box segmentation for truth
`18`, and the other remaining errors are mainly digit classifier/ranking
confusions (`2→9`, `5→3`, `8→4`, `20→79`, `22→92`). The next bottleneck is
therefore both segmentation on difficult strokes and generalization of the
digit classifier; candidate visibility is not sufficient by itself.

Primary reports:

- [Vol.8/9 diagnostics](/private/tmp/exam-grader-identity-all-diagnostics.json)
- [Vol.10 diagnostics](/private/tmp/exam-grader-vol10-frozen-validation.json)
- [Grouped batch benchmark Vol.8/9](/private/tmp/exam-grader-batch-vol89-grouped.json)
- [Grouped batch benchmark Vol.10](/private/tmp/exam-grader-batch-vol10-grouped.json)

## Annotation-v3 frozen-model check

The manifest contains 200 proposals: 198 accepted labels and 2 excluded
records. Product Owner annotation metadata is present for all records; 136
boxes were corrected and 64 retained proposal boxes. There are 100 distinct
source crop hashes/paths, writer identity is unknown, and the manifest's split
policy explicitly says `training_allowed=false`. All 198 evaluated samples
overlap the current seed training source, so these results are
resubstitution/training-overlap evidence, not held-out accuracy.

On the 198 evaluated digits:

- v1: 140/198 (70.7%), top-3 160/198, mean confidence 81.0;
- v2: 142/198 (71.7%), top-3 160/198, mean confidence 80.5;
- union top-3 visibility: 170/198 (85.9%);
- v1/v2 agree on top-1 for 150/198 (75.8%); v2 is correct while v1 is wrong
  on 16 records, versus 14 in the opposite direction;
- mean confidence on wrong predictions is still high (v1 67.8, v2 64.0), so
  confidence is not yet a safe auto-accept calibration signal.

Frequent confusions include `9→1` (v1 8, v2 4), `0→9` (v1 4, v2 5),
`1→6` (v1 2, v2 4), `5→3` (v1 2, v2 3), and `3→5` (2 in both). The union
helps candidate visibility, but does not establish generalization and was not
used as an excuse to enable auto-accept.

Frozen annotation report:

- [annotation manifest](/private/tmp/exam-grader-number-handwriting-annotation-v3/annotation_manifest.json)
- [v1/v2 frozen evaluation](/private/tmp/exam-grader-annotation-v3-frozen-model-evaluation.json)

## Batch identity assistance

The shipped production behavior is room-scoped hard exclusion only:

1. a teacher-confirmed number is a hard anchor when the existing room workflow
   treats identities as unique;
2. other sheets receive a deep-copied effective candidate list with that
   anchored number removed and the next existing candidate promoted;
3. raw candidates/scores and detection payloads are not deleted or rewritten;
4. derived changes remain review-required with no new calibrated confidence;
5. teacher corrections remain authoritative.

The global one-to-one solver was benchmarked but not enabled. In the real
Vol.8/9 collision groups it displaced correct local prefills and reduced
exactness, so it is retained only as a tested future option. Deterministic
anchor simulations show the expected contract: with three teacher-confirmed
anchors, Vol.10 has 14/19 exact non-anchor prefills and 17/22 post-confirmation
outcomes; Vol.8 and Vol.9 each reach 10/10 and 12/12 post-confirmation. These
post-confirmation figures include the teacher's authoritative anchors and must
not be presented as model-only accuracy. Resolver latency was about 3–7 ms per
room in the benchmark.

## Verification and package

- Focused recognition/review tests: 40 passed.
- Broader scoped regression run: 77 passed / 3 failed, with the existing Vol.7 suite's
  3 known baseline failures (two identity visibility cases and one unrelated
  indoor geometry case); the same 3 failures reproduce at baseline `ff64d03`.
- Changed-file Ruff and `git diff --check`: passed.
- Fresh macOS arm64 bundle: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`,
  approximately 235 MB.
- Packaged `--self-check`, offscreen `--smoke-settings`, offscreen
  `--smoke-ui`, and `codesign --verify --deep --strict`: passed.
- Windows native build/UAT was not run; source/package compatibility was not
  claimed as native Windows evidence. Product Owner interactive macOS UAT is
  still required.

Checkpoint commits:

- `85f4bc0` — recognizer evidence-backed prefill improvement
- `5387730` — short/incomplete segmentation recovery
- `8868e78` — room-scoped batch prefill assistance
- `7a9f6fe` — evidence-gated hard-only production batch assistance and benchmark

The app is a trial build, not a release. Auto-accept must remain disabled until
an independent held-out gate proves `wrong auto-accept = 0`.
