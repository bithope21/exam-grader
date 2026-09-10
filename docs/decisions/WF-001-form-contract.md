# WF-001 — Supported form and evidence contract

Type: investigation / product decision
Owner: Codex
Claimed: 2026-09-08 ก่อนตัดสิน support/template contract
Status: OPEN — ยังไม่มี verdict
Depends on: ไม่มี decision ticket อื่น
Blocks: production template freeze และการอ้าง OMR accuracy

## Question

จะรองรับ reference แบบใด และต้องมีหลักฐานใดก่อนเลือก canonical geometry ที่ไม่ตัดเซลล์/อ่านผิดข้อ?

## Evidence available

- Product Owner ยืนยัน scope: แบบหลักหนึ่งแบบก่อน แล้วเพิ่มแบบอื่นภายหลัง Candidate สำหรับ AG-001: ภาพเวลา 07.58.58; canonical geometry ยังไม่ freeze

- ภาพ PNG 4 ภาพใน `answer-sheet/`; ทั้งหมดเป็นภาพแบบฟอร์มเปล่า
- มองเห็นโครงสร้าง 60 × 5 และ header เลขที่; สัดส่วน/กรอบช่อง/ขอบกระดาษต่างกัน
- ยังไม่ยืนยันว่าเป็นภาพคนละ template หรือความต่างจากการถ่าย/พิมพ์
- ไม่มีภาพทำข้อสอบจริงหรือ ground truth ลายมือ

## Evidence task AG-001

Completed by Codex on user continuation request: [report](../evidence/AG-001/REPORT.md). Four inputs decoded, deterministic manifest verified, candidate confirmed for exploration. Ticket stays OPEN: numeric geometry/independent overlay validation is not yet done; production template is not frozen.

ดู AGENT_HANDOFF: inventory, hashes, dimensions, contact sheet และรายงานความแตกต่างโดยไม่แก้ originals ไม่ถือ similarity ทางสายตาเป็น registration pass

## Resolution criteria

1. Product Owner ระบุ supported form scope และแบบอ้างอิง
2. มี manifest อ้างไฟล์ด้วย hash และ candidate canonical reference
3. ระบุ supported/unknown variants, anchors, student ROI และ cell geometry ที่ต้อง validate
4. เขียนข้อจำกัด corpus และรายการข้อมูลจริงที่ยังขาด
5. Codex บันทึก verdict / rationale / revisit condition ใน DECISIONS และ update map

ถ้าไม่มี clean reference: ทำ exploratory transform ได้ แต่ห้ามประกาศ production template พร้อมใช้ ส่วน real marked-sheet benchmark จะยัง blocked จนมี corpus
