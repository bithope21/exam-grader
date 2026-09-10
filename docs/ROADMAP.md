# Roadmap and acceptance gates

นี่คือ milestone map ไม่ใช่ backlog ที่พร้อม implement ทุกช่วง ให้เขียน task brief เฉพาะ frontier แล้วผ่าน Codex review ก่อนขยับ gate

| Gate | Antigravity deliverable | Codex acceptance evidence | Dependencies |
|---|---|---|---|
| G0 Discovery | Reference inventory + support decision evidence | WF-001 verdict, corpus gaps explicit | Product scope |
| G1 Foundation + packaging spike | Minimal headless/desktop entrypoints, test harness, storage migration/checkpoint skeleton, native dependency smoke bundle | Fresh setup commands, offline smoke, original hash checks, Mac/Windows evidence separately | G0 for template-specific work; generic skeleton may proceed |
| G2 Registration | Versioned template + diagnostic overlays + quality rejection | Independent ROI/anchor labels, accepted transforms in tolerance, bad geometry blocked | G0, G1 |
| G3 OMR | Deterministic cell classifier + seeded generator | Per-state metrics on synthetic and held-out real sheets; no threshold tuning on test | G2 + real marked corpus |
| G4 Identity | Numeric baselines + chosen local recognizer + review | Exact full-number metrics and coverage on held-out real writers; all duplicate conflicts reviewed | G2 + handwriting corpus |
| G5 Trusted grading + evidence | Key/review versions, scoring, renderer, Excel/JSON | Oracle cases exact, stale handling, reproducible overlay + consistent export snapshot | G3/G4 contracts + approved scoring policy |
| G6 Teacher workflow + hardening | UI end-to-end, batch cancel/resume, safe file lifecycle | No-terminal teacher walkthrough, crash/restart tests, paths/disk failures, real batch timing | G5 |
| G7 Release | Actual installers, bundled resources/models, release docs | Clean offline installation on declared OS/CPU matrix, UAT, license/signing/distribution evidence | G6 |

G3/G4 investigations can be sequenced independently after G2; ห้ามเอา mock identity ไปประกาศว่า G4 ผ่าน ไม่ต้องรอ UI สวยจึงค่อยทดลอง packaging; codec/model เพิ่มใหม่ต้องทำ packaged smoke ซ้ำ

## Per-task loop

Codex ระบุ scope + test oracle → Antigravity inspect/claim/implement → ส่ง diff และ commands/results/artifacts → Codex อ่าน diff และรัน focused checks อิสระ → PASS / CHANGES_REQUIRED / BLOCKED → update handoff → task ถัดไป

PASS = criteria ของงานนั้นครบเท่านั้น ไม่ได้แปลว่า release ผ่านทุก gate ห้ามรายงาน skipped/not-run เป็น pass ไม่ commit/push/publish โดยอ้างแผนนี้เป็น blanket authorization
