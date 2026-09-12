# Fresh-Chat Handoff: Exam Grader v1.0.1 Published & Live

- **Repository**: `/Users/zubinpijit/private/exam-grader` (Branch: `main`)
- **Release Tag**: `v1.0.1`
- **Release Commit SHA**: `ccc6d49a971a162097044957677a4881afa3ce08`
- **Release URL**: https://github.com/bithope21/exam-grader/releases/tag/v1.0.1
- **Release ID**: `387664293`
- **Current Status**: **RELEASE v1.0.1 PUBLISHED & 100% VERIFIED LIVE OVER HTTP GET**.

---

## 1. Verified Release Artifacts & SHA-256 Checksums

| Asset Name | Size | SHA-256 Checksum | HTTP GET Verification |
|------------|------|------------------|-----------------------|
| `Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg` | 113,086,354 bytes (~108 MB) | `d90919cc6fd7f2952eacfbd53dd6c4d589b9d4def6710b11c8795762b206433f` | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-macOS-Apple-Silicon.dmg.sha256` | 109 bytes | N/A | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-Windows-Setup.exe` | 77,919,326 bytes (~74 MB) | `b618fe15646290cd73eb3ee6238beddefd7081c581835c39fa780e26c7cd19ec` | HTTP 200 (MATCH) |
| `Exam-Grader-v1.0.1-Windows-Setup.exe.sha256` | 104 bytes | N/A | HTTP 200 (MATCH) |

---

## 2. Release Highlights Included in Notes

1. **100% Offline Processing**: Zero cloud telemetry, no image/data leakage.
2. **Transparent Brand Icons**: Multi-resolution clean alpha icons for macOS (.icns) and Windows (.ico) without white background or halos. Windows `SetCurrentProcessExplicitAppUserModelID` configured.
3. **High Performance Import**: Student answer sheet import accelerated up to 4.7x using fast scaled ECC and in-memory feature/reference caching.
4. **Human-in-the-Loop Review**: Multi-select bulk edit in teacher review workspace.
5. **Custom Templates**: 3 built-in templates (Default #1, #2, #3) + custom layout calibration.
6. **Comprehensive Export**: Excel (.xlsx) score report + verified checked answer sheet images (.jpg).
7. **Windows Hardening**: Fixed template management dialog crash and solved `[WinError 5]` on export with copy-then-cleanup.

---

## 3. GitHub Actions CI Architecture Note

- Windows installer build is automated via `.github/workflows/release.yml` with dynamic filename and version detection (avoiding hardcoded release strings).
- Completed Windows Runner Run ID: `34711082160` (Artifact ID: `10302829066`).

