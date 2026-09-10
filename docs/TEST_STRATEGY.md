# Independent verification contract

## Corpus and oracle

แยก real references, real marked sheets, synthetic และ damaged inputs พร้อม manifest/hash/provenance/permission ภาพ 4 ใบปัจจุบันพิสูจน์ได้เพียง reference inventory ไม่ใช่ recognition accuracy

Ground truth ของ real sheets ต้องครู/ผู้ label ตรวจยืนยันโดยไม่ใช้ prediction เป็นเฉลย เก็บ registration anchors/ROI, number, per-question state/choices และ approved scoring truth Synthetic ใช้ seed + truth อิสระจาก detector; ห้ามสร้าง expected answers ด้วย detector ตัวเดียวกัน

แยก train/calibration/held-out test ตามต้นฉบับกระดาษและผู้เขียนเมื่อทราบ: transformed copies ของต้นฉบับเดียวกันห้ามกระจายข้าม split จัดกลุ่ม near-duplicates ด้วย ห้ามปรับ threshold ตาม held-out failure แล้วคงเรียกชุดเดิมว่า unseen

## Metrics

รายงาน numerator/denominator, corpus version, hardware, config และ failure examples ไม่รายงาน accuracy เดี่ยว

- Registration: accepted/rejected coverage, ROI corner error เทียบ independent labels ในหน่วย cell size, wrong-row/column failures
- Answers: exact choices + state confusion matrix, per-question/per-sheet correctness
- Auto-accept: error rate เฉพาะ accepted items ควบคู่ coverage และ review rate; reject ทุกภาพไม่ถือว่าผ่าน
- Identity: exact whole-number accuracy, auto-accept error/coverage, blank/duplicate/out-of-range behavior
- End-to-end: final identity + score correctness หลัง review, stale result prevention
- Performance: stage timings, p50/p95, peak memory, cancel latency, batch throughput บนเครื่องระบุรุ่น

## Gate thresholds

ตั้งแต่ต้น: deterministic grading oracle ต้องถูกทุกเคส, originals hashes unchanged, unresolved/invalid ไม่ออกเป็น final score, Excel/JSON/checked images อ้าง snapshot เดียวกัน ต้องผ่านทั้งหมด

Recognition release targets (acceptable auto-accept error, minimum coverage, corpus size, geometry tolerance) ยัง **TBD — release blocker** ให้เสนอและ Product Owner เห็นชอบก่อนเปิด held-out evaluation ไม่แต่งเลข accuracy จากภาพเปล่า Zero observed errors ไม่ได้แปลว่า true error = 0; รายงาน uncertainty และ sheet-level clustering เมื่อคำนวณ interval

## Required suites as capability appears

| Area | Cases |
|---|---|
| Geometry | rotation, perspective, crop, wrong orientation/template, shadows, glare, blur, printed inner boxes |
| Marks | blank, each choice, multiple, faint, border-crossing, erasure, overwritten, unusual marks → review when ambiguous |
| Identity | blank, joined digits, confusing pairs, duplicate across batch/reimport, human correction collision |
| Scoring | approved/unapproved key, active question bounds, blank/multiple policy, key change, review change, rerun |
| Files | Thai/Unicode, reserved/long names, duplicate bytes, same name different bytes, corrupt/empty files, read-only/full disk |
| Recovery | interrupt before/after DB checkpoint/export publish, restart without duplication, one image fails while batch continues |
| Packaging | clean machine without Python, network disabled, resources/model/codecs, supported architecture, uninstall preserves exams |

Visual review ต้องตรวจ cell alignment และหลักฐานที่ไม่ถูก overlay บัง ทั้งสีและ grayscale; ไม่พึ่ง pixel golden อย่างเดียว

## Review evidence format

แต่ละ submission มี task ID, base/revision หรือ diff inventory, changed paths, exact commands + exit status, artifacts, expected vs actual, limitations และ tests not run Codex บันทึกสิ่งที่รันเองแยกจากรายงาน Antigravity; Product Owner UAT แยกจาก automated pass

## 2026-09-08 bounded execution evidence

`tools/benchmark/golden_labels.py` emits a provenance-first manifest that keeps
machine observations, teacher scoring decisions and independent visual labels in
separate fields. Conflicting fields (the historical key question 6) are excluded
from recognition metrics instead of being silently relabelled.

The real fixture benchmark reports active-question state counts, top-two density
margin diagnostics, registration and timing while keeping `auto_accept_count=0`.
`tools/benchmark/identity_benchmark.py` reports review-required numeric candidates;
its accuracy is explicitly null until an independent handwritten-number corpus is
available. Export tests cover renderer provenance, score ROI annotation, archive/
restore semantics, expected-number gaps and export registry persistence.
