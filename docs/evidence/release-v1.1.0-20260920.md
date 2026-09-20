# Release v1.1.0 evidence — 2026-09-20

## Scope gate

PR #3 (`feat/windows-uat-indicators-polish`) was audited against
`origin/main` before fast-forwarding local `main` to `e9162d5`. The changed
paths cover Assessment Indicators/Exam Rooms, Excel presentation formatting and
borders, Home room count, light/dark destructive-icon polish, the Windows
`QApplication` compatibility fix, and related tests/docs. No Student Number
recognizer/model/training change, Whole-ROI experiment, model weight, or
fixture entered the merge. The concurrent untracked `data/` and Vol.8/9/10
fixtures remain untouched and outside the release.

## Version and source

- Release version: `1.1.0` (semver minor: backward-compatible feature addition)
- Merged source checkpoint: `e9162d5`
- Release metadata files: `pyproject.toml`, `src/exam_grader/__init__.py`,
  `scripts/build/package_dmg.sh`, `scripts/build/windows-installer.iss`
- Auto-accept remains unchanged; no Student Number/Whole-ROI experiment is
  included.

## Verification

- Focused Mac command: `QT_QPA_PLATFORM=offscreen .venv/bin/pytest -q`
  over the Indicators/Rooms, export, theme/UI, workflow, Windows RC/UAT,
  identity, and digit-model tests, excluding the test that writes to the real
  Mac Documents directory: `77 passed, 1 skipped, 1 deselected`.
- The skipped test lacked its workspace images. The excluded real-Documents
  test is a platform-specific Windows UAT path and was not claimed as Mac
  evidence.
- Ruff on changed source/tests: passed; `git diff --check`: passed.
- Fresh macOS arm64 app:
  `/Users/zubinpijit/private/exam-grader/dist/ExamGrader.app`
- Packaged self-check: version `1.1.0`, `storage=ok`; settings/UI smoke passed;
  `codesign --verify --deep --strict` passed.
- DMG:
  `/Users/zubinpijit/private/exam-grader/dist/Exam-Grader-v1.1.0-macOS-Apple-Silicon.dmg`
  (108 MB), SHA-256
  `d16750cbf17dc499c0469e73efec699749a5714191d960d4656c335b101447db`.
- Windows native UAT: PR #3 body records Product Owner approval of the
  Windows `.exe` flow and the scoped room/indicator/Excel/compatibility checks.
  This is reported Windows evidence, not a Mac rerun; the final-tag Windows
  artifact is produced by GitHub Actions.

## Remaining publication gate

Commit the metadata/evidence checkpoint, create annotated tag `v1.1.0` from
the final `main`, push `main` and the tag, then verify the tag workflow and
GitHub Release artifacts. Final status must remain clean except for the
protected pre-existing untracked concurrent-work files.
