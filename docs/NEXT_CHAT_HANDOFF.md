# Fresh-chat handoff

Repository: `/Users/zubinpijit/private/exam-grader`

อ่านก่อน: `progress.md`, `docs/TASK_SPEC.md`, `docs/ARCHITECTURE.md`,
`docs/DECISIONS.md` และหลักฐานล่าสุด. Git baseline: `2f1479e`; local only,
ไม่มี remote/push.

TASK ถัดไป: `Custom Answer-Sheet Template / Calibration System`

ให้ agy ออกแบบและ implement เฉพาะระบบ template/calibration ที่จำเป็นต่อการ
ลดงานครู โดยตรวจ source/data contract จริงก่อน และรักษา business logic เดิม
ทั้งหมด: key confirmation, sparse-roster skip/restore, immutable originals,
provenance, stale-key protection, multi-answer scoring และ fail-closed
uncertainty. ห้ามอ่าน frozen teacher labels เข้า algorithm, ห้ามเดาเงียบ,
ห้ามปรับ threshold เพื่อผลลัพธ์สวย, และห้าม claim accuracy ทั่วไป.

ใช้ vol.1/vol.2/vol.3 เป็น regression baseline; เพิ่ม evidence ของ calibration
แยกจากผลเดิม. ต้องมี diagnostics/provenance/preview และ teacher confirmation
สำหรับ calibration ที่ไม่ชัดเจน. ตรวจ visual output และรัน pytest, Ruff, Mypy,
build, codesign, self-check, smoke-ui และ real-fixture UAT ก่อนสรุป.

`DETAIL: [รอ Product Owner บอกใน chat ใหม่]`
