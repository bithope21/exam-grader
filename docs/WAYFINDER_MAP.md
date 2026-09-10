# Exam Grader — canonical local map

Label: `wayfinder:map` | Owner: Codex | Updated: 2026-09-08

## Destination

โปรแกรม offline ที่ครูติดตั้งและตรวจข้อสอบจริงได้ทั้ง Mac/Windows พร้อม review uncertainty และหลักฐานคะแนนย้อนกลับได้ ตาม PRODUCT_SPEC และ handoff เดิม

## Tracker status

Workspace ยังไม่มี Git repository หรือ issue tracker ที่กำหนด จึงใช้เอกสารนี้เป็น **local staging map** ตามแนว Wayfinder; ยังไม่ได้สร้าง root issue, labels หรือ native blocking relationships บน tracker และไม่อ้างว่าทำแล้ว เมื่อเลือก tracker ให้ย้าย map/ticket ไปที่นั่นและใช้ลิงก์ redirect แทนการมีสองแหล่งสถานะ

## Frontier

| Ticket | Question | Owner | Status | Blocks |
|---|---|---|---|---|
| [WF-001](decisions/WF-001-form-contract.md) | ฟอร์มเป้าหมายและหลักฐานเพียงพอจะกำหนด registration contract หรือยัง? | Codex | Claimed; inventory complete, geometry validation pending | G2 production template, G3 accuracy claim |

Claim ก่อนเริ่ม investigation; หนึ่ง session resolve decision ticket ไม่เกินหนึ่งรายการ Antigravity ทำ bounded evidence task ภายใต้ ticket นี้ ไม่ปิด product decision เอง

## Decisions so far

- Product baseline: offline / existing paper / CV answers / narrow digit ML / human review / immutable originals มาจาก handoff
- Role assignment: Codex ตรวจรับ; Antigravity implement มาจากคำสั่งล่าสุด
- ยังไม่ล็อก template, model, packaging tool หรือ scoring policy
- Product Owner ยืนยันเริ่มแบบหลักหนึ่งแบบก่อน; แบบอื่นเพิ่มภายหลัง

## Not yet specified

- Real dataset acquisition, independent ground truth และเกณฑ์ release accuracy ที่ Product Owner ยอมรับ
- Exact scoring / active questions / identity semantics
- Benchmark model candidates, confidence calibration, segmentation fallback
- Supported OS matrix, packaging selection, license/distribution/signing requirements
- Annotation appearance, output compression, performance budget บนเครื่องครู

Graduate เป็น decision tickets เมื่อมี evidence และเป็น blocker ถัดไป ไม่ pre-create execution tickets ยาวทั้งโปรเจกต์

## Out of scope

ตาม PRODUCT_SPEC: cloud, accounts, sync, redesign paper, OCR ชื่อเต็ม
