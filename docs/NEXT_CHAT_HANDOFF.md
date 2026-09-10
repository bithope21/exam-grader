# Fresh-chat handoff

Repository: `/Users/zubinpijit/private/exam-grader`

อ่านก่อน: `progress.md`, `docs/TASK_SPEC.md`, `docs/AGENT_HANDOFF.md`, `docs/DECISIONS.md`

สถานะ: bounded polish pass เสร็จ, pytest 45 ผ่าน, Ruff/Mypy ผ่าน, real-fixture
registration 6/6, auto-accept 0, originals immutable, checked renderer มีแล้ว

ขอบเขตถัดไป:

- ทำ student-number recognition จาก answer sheet จริงใน fixed registered ROI
- ทำให้การเขียนคะแนนรวมลงช่องคะแนนรวมของกระดาษจริงตรงตำแหน่ง
- เก็บ candidate, confidence/diagnostics, human correction และ source→checked provenance
- ใช้ fail-closed; ห้ามเดาเงียบและห้ามอ้าง production accuracy โดยไม่มี corpus

`DETAIL: [รอ Product Owner บอกใน chat ใหม่]`
