# TASK — Build Exam Grader Landing Page

## Goal

สร้าง landing page สำหรับ **Exam Grader** ที่ route:

```text
https://bithope.app/exam-grader
```

Repo:

```text
/Users/zubinpijit/bithope/apps/bithope-web
```

ให้เป็นหน้า product/download ที่พร้อมต่อ wiring จริงภายหลัง โดย **ห้ามกระทบ business logic / routes / shared components เดิมที่ทำงานดีอยู่แล้ว**

---

## 1) Required Skill

ก่อนเริ่มงาน ให้ inspect environment แล้วติดตั้ง/เปิดใช้ skill นี้:

```text
https://github.com/nutlope/hallmark
```

ใช้ Hallmark เป็นส่วนหนึ่งของ workflow สำหรับยกระดับ landing page, interaction, motion และ visual polish

หาก repo/agent มี frontend / UX/UI skills ที่เหมาะสมอยู่แล้ว ให้ใช้ร่วมกันได้ แต่ต้องรักษา design system ของ `bithope.app`

---

## 2) Design Direction

ภาพรวม:

- minimal, calm, professional, teacher-friendly
- ไม่ corporate แข็ง ๆ และไม่ playful จนดูเป็นของเด็ก
- ใช้ **LocalSend landing page เป็น reference ด้าน information architecture / product-download clarity เท่านั้น — ห้าม copy UI**
- logo/hero visual: **กระดาษคำตอบแบบ minimal / Notion-style**
- background ให้มีกลิ่นอาย **ห้องเรียนแบบ minimal**
- ใช้ decorative assets ที่เกี่ยวกับโรงเรียนอย่างพอดี เช่น โต๊ะเรียน กระดาษ ดินสอ กระเป๋า หนังสือ
- มีนักเรียน/ครู minimal illustration น่ารัก ๆ เป็นองค์ประกอบรอง
- หลีกเลี่ยง gradient ฉูดฉาด, glassmorphism หนัก, neon, visual noise
- spacing / typography / alignment ต้องดู “ตั้งใจทำ” ระดับ UX/UI มืออาชีพ

Animation:

- ใช้ subtle motion / micro-interaction ในจุดที่ช่วยสื่อสาร
- เช่น floating paper, hover response, section reveal, answer-mark animation, score transition
- มี interactive process demo แบบเบา ๆ ให้ user เข้าใจ workflow
- ห้ามใส่ animation เยอะจนรบกวนการอ่านหรือกระทบ performance
- respect `prefers-reduced-motion`

---

## 3) Recommended Page Structure

### Header

มีอย่างน้อย:

- Exam Grader / logo
- Features
- How it works
- Docs
- GitHub
- Download

Header responsive และ mobile-friendly

---

### Hero

ต้องตอบให้เข้าใจภายในไม่กี่วินาทีว่า:

> โปรแกรมตรวจข้อสอบจากภาพกระดาษคำตอบแบบ offline สำหรับครู  
> ใช้งานได้บน macOS และ Windows

ประกอบด้วย:

- headline กระชับ
- supporting copy สั้น
- CTA:
  - `Download for macOS`
  - `Download for Windows`
- secondary CTA:
  - `View on GitHub`
- minimal answer-sheet visual / illustration
- subtle school/classroom background elements

**CTA ทั้งหมดยังเป็น mock/placeholder ก่อน**

---

### Real App Preview

ใช้ **screenshots จาก Exam Grader app จริงที่มีอยู่ใน project/assets**

ให้ agent inspect และเลือกภาพที่สื่อ workflow ได้ดีที่สุด

Presentation:

- ใส่ screenshot ใน polished macOS-style app/window frame
- responsive
- มี subtle depth แต่ไม่ glossy
- ถ้ามีหลายภาพ ให้ทำ carousel / stacked preview / interactive tabs แบบเรียบง่าย

ห้ามสร้าง UI ปลอมที่ทำให้เข้าใจผิดว่าเป็น app จริง หากมี screenshot จริงให้ใช้ของจริงเป็นหลัก

---

### How It Works

ทำเป็น polished visual flow:

```text
1. สร้าง/เลือกข้อสอบ
2. ใส่เฉลย
3. นำเข้าภาพกระดาษคำตอบ
4. ระบบอ่านและตรวจแบบ offline
5. ตรวจทานเฉพาะจุดที่ไม่มั่นใจ
6. Export คะแนนและผลลัพธ์
```

ควรมี animation/interaction ที่ช่วยอธิบาย เช่น:

- กระดาษเลื่อนเข้า scanner frame
- answer marks ถูก detect
- score ปรากฏ
- uncertain item แยกไป review

ต้อง minimal และ lightweight

---

### Key Product Benefits

เน้นจากตัว product จริง:

- Offline / local processing
- ไม่ต้องอัปโหลดกระดาษคำตอบขึ้น cloud
- รองรับ workflow ครู
- Human review สำหรับจุดที่ระบบไม่มั่นใจ
- Preserve original evidence
- Export คะแนน/ผลลัพธ์ได้
- ใช้งานบน macOS + Windows

อย่า claim capability ที่ app ยังไม่มีจริง

---

### Download Section

ทำโครงให้เหมือน product download page ที่ดี:

#### macOS

- Download for macOS
- supported architecture/version placeholder
- installer format placeholder
- release/version placeholder

#### Windows

- Download for Windows
- supported architecture/version placeholder
- installer format placeholder
- release/version placeholder

ตอนนี้ให้ mock link ไว้ก่อน เช่น central config:

```ts
const EXAM_GRADER_LINKS = {
  macDownload: "#",
  windowsDownload: "#",
  github: "#",
  issues: "#",
  sponsor: "#",
  docs: "#",
};
```

หรือ pattern ที่เหมาะกับ codebase มากกว่า

**อย่ากระจาย URL placeholder หลายที่ใน component**

---

### Open Source / Support

มี section/card สำหรับ:

- GitHub repository
- Report a bug → GitHub Issues
- Docs
- Sponsor / Support project

ให้ polish แบบเรียบง่ายคล้าย product open-source page ที่ดี

ทุก link mock ไว้ก่อน เพื่อ wire ภายหลังได้ในจุดเดียว

---

### Footer

อย่างน้อย:

- bithope>_
- Exam Grader
- GitHub
- Docs
- Issues
- Sponsor
- copyright / project note ที่เหมาะสม

---

## 4) UX / Engineering Requirements

ต้องทำให้ครบ:

- responsive: desktop / tablet / mobile
- light/dark behavior ต้องไม่พัง หาก bithope มี theme system อยู่แล้ว
- semantic HTML
- keyboard accessible
- visible focus states
- contrast อ่านง่าย
- optimize images
- lazy-load non-critical media
- avoid layout shift
- animation performant
- no autoplay-heavy media
- SEO metadata
- OpenGraph/Twitter metadata
- sensible title/description
- route must work directly at `/exam-grader`
- no regression to existing bithope routes/pages

หาก project ใช้ Next.js conventions อยู่แล้ว ให้ทำตาม architecture เดิม ไม่สร้าง parallel system ใหม่โดยไม่จำเป็น

---

## 5) Asset Handling

ก่อนสร้าง asset ใหม่:

1. inspect assets/screenshots ที่มีอยู่
2. reuse ของจริงก่อน
3. หากต้องสร้าง decorative illustration เพิ่ม ให้สร้างเฉพาะที่ช่วย composition
4. แยก marketing assets ของ Exam Grader ให้เป็นระเบียบ เช่น:

```text
public/
└── exam-grader/
    ├── screenshots/
    ├── illustrations/
    └── icons/
```

ปรับ path ตาม architecture จริงของ repo

---

## 6) Content Tone

ภาษาไทยเป็นหลัก ใช้คำสั้น อ่านง่าย เหมาะกับครู

หลีกเลี่ยงคำอธิบาย technical internals เช่น:

- homography
- OpenCV pipeline
- ONNX
- CV confidence threshold

ให้แปลงเป็นภาษาผู้ใช้ เช่น:

> “ระบบจะให้คุณตรวจเฉพาะจุดที่ไม่มั่นใจ”

---

## 7) Agent Execution Loop

ทำงานแบบ:

```text
Inspect existing bithope design system
→ Install/use Hallmark
→ Inspect existing Exam Grader screenshots/assets
→ Plan page/component structure
→ Implement
→ Run lint/typecheck/build/tests relevant to repo
→ Launch locally
→ Inspect screenshots at desktop/tablet/mobile
→ Fix overflow/alignment/theme/motion/accessibility issues
→ Re-test
→ Stop only when acceptance criteria pass
```

ใช้ screenshot inspection จริง ไม่ใช่ดู code แล้วสรุปว่า UI ดีเอง

---

## 8) Acceptance Criteria

ถือว่างานเสร็จเมื่อ:

- `/exam-grader` เปิดได้จริง
- visual quality ดูเป็น product landing page ที่พร้อม launch
- hero สื่อ product ได้ทันที
- macOS + Windows download CTA ชัดเจน
- GitHub / Issues / Sponsor / Docs พร้อม placeholder wiring
- มี real app screenshots ใน polished frames
- มี minimal interactive/animated workflow section
- desktop/tablet/mobile ไม่มี overflow หรือ broken layout
- animation สุภาพและไม่รบกวน usability
- accessibility / reduced motion ใช้งานได้
- SEO metadata ครบ
- build/lint/typecheck ตาม repo ผ่าน
- existing bithope pages/routes/business logic ไม่ regression
- ไม่มี dead code / temporary experiment / asset รกค้าง

---

## Final Deliverable

เมื่อเสร็จ ให้รายงานแบบกระชับ:

1. files changed
2. route ที่สร้าง
3. assets ที่ใช้/เพิ่ม
4. checks/tests ที่ผ่าน
5. screenshots ที่ตรวจจริงในแต่ละ breakpoint
6. จุดที่ยังเป็น mock link และตำแหน่ง config สำหรับ wire URL จริง
