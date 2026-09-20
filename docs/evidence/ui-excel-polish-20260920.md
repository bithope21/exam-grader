# UI and Excel polish evidence — 2026-09-20

## Scope

This checkpoint is presentation-only: the Home exam list now shows the
authoritative room count, the archive action has a visible destructive icon in
both light and dark themes, and the Scores worksheet draws thin borders around
every used cell. No recognition, OMR, registration, grading, export values,
assessment-indicator, room persistence, or unrelated business logic changed.

## Implementation

- `src/exam_grader/ui.py` derives `len(application.exams.list_rooms(exam.id))`
  for the existing exam-row text and uses the bundled
  `src/exam_grader/resources/trash-destructive.svg` for the archive action.
- `src/exam_grader/preferences.py` gives the destructive icon button a
  high-contrast red affordance in light and dark palettes.
- `src/exam_grader/exporting.py` applies thin neutral borders to all four sides
  of every used Scores cell while preserving existing values, widths, filters,
  freeze panes, alignment, and worksheet semantics.

## Verification

- Focused source checks: home room-count/icon `1 passed`; theme `2 passed`;
  room-isolated Excel export/border check `1 passed`; export compatibility
  checks `2 passed`.
- Changed-file Ruff: passed.
- `git diff --check`: passed.
- Fresh macOS arm64 package: `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`.
- Package size: approximately 235 MB.
- Packaged self-check: `storage=ok`.
- Packaged settings smoke: `smoke_settings=ok`, 3 templates.
- Packaged offscreen UI smoke: exited without error.
- Strict deep codesign: passed.
- Native macOS visual inspection of the rebuilt app showed room counts and a
  clearly visible red trash action in both light and dark themes.
- The generated workbook was opened/checked through the focused export test;
  `A1`, `H1`, `A2`, and `H2` all have thin left/right/top/bottom borders.

## Evidence boundaries

This is source/package evidence plus bounded native visual inspection. It is
not Windows native UAT, a release, or a claim about the separate whole-ROI
Student Number Recognition experiment. The whole-ROI dirty/untracked files
remain preserved and outside this checkpoint.

## Windows follow-up

Windows must pull this scoped checkpoint, run native self-check/UI/Excel smoke,
and report any platform-specific rendering or packaging issue before an `.exe`
build is treated as a candidate artifact. Do not claim Windows native UAT from
the macOS package.
