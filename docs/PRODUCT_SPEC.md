# Product contract v0.1

Source: handoff เดิม + คำสั่งผู้ใช้ 2026-09-08 สถานะ: baseline สำหรับวางแผน ไม่ใช่การรับรอง production

## Required behavior

| ID | Requirement | Gate |
|---|---|---|
| R01 | Offline desktop, macOS + Windows, ผู้ใช้ไม่ต้องติดตั้ง Python | G1, G7 |
| R02 | ใช้กระดาษเดิม; deterministic CV สำหรับ answers; ML เฉพาะเลขที่ | G2, G3, G4 |
| R03 | เฉลยจากภาพ ต้องให้ครูตรวจและ approve version ก่อนใช้ | G5, G6 |
| R04 | Single / multi-file / folder / drag-drop import, EXIF orientation | G2, G6 |
| R05 | Blank / single / multiple / uncertain / invalid แยกสถานะ | G3, G5 |
| R06 | เลขที่ไม่ชัด/ซ้ำ/ผิดช่วง และ alignment failure เข้าคิวแก้ไข | G4, G6 |
| R07 | Final grade ใช้เฉลย approved + review ที่ resolve แล้วเท่านั้น | G5, G6 |
| R08 | Original immutable; derived checked image มีเลขที่ คะแนน หลักฐาน | G1, G5 |
| R09 | Excel: No., Score, Max, Status, Source File; JSON + provenance | G5, G6 |
| R10 | Batch responsive, cancel/resume, one-file failure isolated | G1, G6 |
| R11 | Key/correction changes ทำให้ผลเดิม stale และ regrade ได้ | G5, G6 |
| R12 | Thai/Unicode paths, collision-safe output, recoverable export | G1, G6, G7 |

Missing expected number ตรวจได้เฉพาะเมื่อมี expected set/range ที่ครูกำหนด ไม่อนุมาน roster เอง

## Observed form evidence

ตรวจภาพ 4 ไฟล์ด้วยสายตา: ทุกภาพเห็น 4 กลุ่ม กลุ่มละ 15 ข้อ รวม 60 ข้อ และ 5 คอลัมน์ ก ข ค ง จ / A B C D E / 1 2 3 4 5 มีช่องเลขที่ใน header

นี่เป็น observation ของ reference ไม่ใช่การอนุมัติว่า exam ต้องใช้ครบ 60 ข้อหรือรับรองว่าทั้งหมดเป็น template เดียว ภาพบางใบมีกรอบเล็กในเซลล์ แสงสะท้อน และสัดส่วนต่างกัน ไม่มีลายมือเลขที่หรือคำตอบที่ใช้วัด accuracy ได้

## Confirmed support scope (2026-09-08)

Product Owner เลือก **แบบหลักหนึ่งแบบก่อน แล้วเพิ่มแบบอื่นภายหลัง** Candidate สำหรับสำรวจคือ `answer-sheet/ภาพถ่ายหน้าจอ 2569-09-08 เวลา 07.58.58.png` เพราะมองเห็น header, answer grid และขอบล่างครบ โดยยังต้อง validate geometry และไม่ถือภาพ screenshot นี้เป็น production-quality blank reference อัตโนมัติ

## Pending product rules

- ยืนยัน canonical geometry ของแบบหลักจาก evidence; แบบอื่นยังไม่อยู่ใน v1 support claim
- ต้องตรวจครบ 60 หรือเลือก active questions; ห้ามนับข้อที่ไม่อยู่ในข้อสอบเป็น blank ที่เสียคะแนน
- คะแนนต่อข้อ, blank/multiple ที่ครูยืนยันแล้ว, การแก้/ขีดฆ่า และข้อที่เฉลยว่าง
- รูปแบบเลขที่: เลขอารบิก/ไทย, leading zero, ช่วง, duplicate resolution
- Supported OS versions / CPU architectures / เครื่องใช้งานจริง

ข้อเหล่านี้ไม่ขวาง inventory และ disposable registration exploration แต่ต้องปิดก่อนใช้ policy นั้นใน production contract

## Boundaries

ไม่มี cloud OCR, backend, account, billing, sync, LMS, full Thai-name recognition หรือการบังคับเปลี่ยนแบบกระดาษ ไม่สัญญา HEIC/TIFF/WebP จนผ่าน decoder และ packaged tests ทั้งสอง OS
