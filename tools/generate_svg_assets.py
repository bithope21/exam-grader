from pathlib import Path

ill_dir = Path('/Users/zubinpijit/bithope/apps/bithope-web/public/exam-grader/illustrations')
icon_dir = Path('/Users/zubinpijit/bithope/apps/bithope-web/public/exam-grader/icons')
ill_dir.mkdir(parents=True, exist_ok=True)
icon_dir.mkdir(parents=True, exist_ok=True)

# 1. Notion-style 2D Answer Sheet SVG
answer_sheet_svg = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 340 460" fill="none" class="w-full h-auto">
  <defs>
    <filter id="paper-shadow" x="-8" y="-4" width="356" height="476" filterUnits="userSpaceOnUse">
      <feDropShadow dx="0" dy="8" stdDeviation="12" flood-color="#1c1917" flood-opacity="0.08" />
    </filter>
  </defs>
  
  <!-- Paper Background -->
  <rect x="10" y="10" width="320" height="440" rx="14" fill="#FFFFFF" stroke="#E7E5E4" stroke-width="1.5" filter="url(#paper-shadow)" />
  
  <!-- Header Bar -->
  <path d="M 10 24 Q 10 10 24 10 L 316 10 Q 330 10 330 24 L 330 42 L 10 42 Z" fill="#FBF9F5" />
  <line x1="10" y1="42" x2="330" y2="42" stroke="#E7E5E4" stroke-width="1" />
  
  <!-- Header Title -->
  <text x="26" y="28" font-family="var(--font-sans), system-ui, sans-serif" font-size="13" font-weight="700" fill="#1C1917">กระดาษคำตอบ (Answer Sheet)</text>
  <rect x="250" y="19" width="64" height="16" rx="8" fill="#ECFDF5" stroke="#A7F3D0" stroke-width="1" />
  <text x="282" y="30" font-family="var(--font-sans), system-ui, sans-serif" font-size="9" font-weight="600" fill="#047857" text-anchor="middle">10 ข้อ</text>

  <!-- Student Info Fields -->
  <g transform="translate(26, 56)">
    <text x="0" y="12" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" fill="#78716C">ชื่อ-สกุล:</text>
    <line x1="46" y1="14" x2="160" y2="14" stroke="#D6D3D1" stroke-dasharray="2 2" stroke-width="1" />
    <text x="50" y="11" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="500" fill="#292524">กานต์พิชชา ใจดี</text>
    
    <text x="175" y="12" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" fill="#78716C">ชั้น:</text>
    <text x="198" y="11" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="500" fill="#292524">ม.4/1</text>
    <line x1="195" y1="14" x2="225" y2="14" stroke="#D6D3D1" stroke-dasharray="2 2" stroke-width="1" />
    
    <text x="238" y="12" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" fill="#78716C">เลขที่:</text>
    <rect x="268" y="0" width="22" height="17" rx="3" fill="#F5F5F4" stroke="#D6D3D1" stroke-width="1" />
    <text x="279" y="12" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="700" fill="#047857" text-anchor="middle">12</text>
  </g>

  <!-- Questions Table Header -->
  <g transform="translate(26, 92)">
    <rect x="0" y="0" width="288" height="22" rx="6" fill="#F5F5F4" />
    <text x="16" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C" text-anchor="middle">ข้อ</text>
    <text x="75" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C">ก</text>
    <text x="115" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C">ข</text>
    <text x="155" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C">ค</text>
    <text x="195" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C">ง</text>
    <text x="235" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="10" font-weight="600" fill="#78716C">จ</text>
    <text x="272" y="15" font-family="var(--font-sans), system-ui, sans-serif" font-size="9" font-weight="600" fill="#78716C" text-anchor="middle">ผล</text>
  </g>

  <!-- Rows 1-10 -->
  <!-- Q1 (Correct: B) -->
  <g transform="translate(26, 122)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">1</text>
    <circle cx="78" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="118" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <circle cx="158" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <path d="M 266 11 L 270 15 L 278 7" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <line x1="26" y1="147" x2="314" y2="147" stroke="#F5F5F4" stroke-width="1" />

  <!-- Q2 (Correct: C) -->
  <g transform="translate(26, 153)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">2</text>
    <circle cx="78" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="118" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="158" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <path d="M 266 11 L 270 15 L 278 7" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <line x1="26" y1="178" x2="314" y2="178" stroke="#F5F5F4" stroke-width="1" />

  <!-- Q3 (Incorrect: marked A instead of D) -->
  <g transform="translate(26, 184)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">3</text>
    <circle cx="78" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <circle cx="118" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="158" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <path d="M 267 7 L 277 17 M 277 7 L 267 17" stroke="#EF4444" stroke-width="2" stroke-linecap="round" fill="none" />
  </g>
  <line x1="26" y1="209" x2="314" y2="209" stroke="#F5F5F4" stroke-width="1" />

  <!-- Q4 (Uncertain mark / Review needed - highlighted in Amber) -->
  <g transform="translate(26, 215)">
    <rect x="-4" y="0" width="296" height="23" rx="4" fill="#FEF3C7" fill-opacity="0.5" stroke="#F59E0B" stroke-width="1" stroke-dasharray="3 3" />
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="700" fill="#B45309" text-anchor="middle">4</text>
    <circle cx="78" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <!-- Faint smudge on B -->
    <circle cx="118" cy="11" r="8.5" stroke="#9CA3AF" stroke-width="1" fill="#E5E7EB" />
    <line x1="114" y1="9" x2="122" y2="13" stroke="#6B7280" stroke-width="1.5" />
    <!-- Incomplete mark on C -->
    <circle cx="158" cy="11" r="8.5" stroke="#4B5563" stroke-width="1.2" fill="#9CA3AF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <rect x="261" y="4" width="22" height="15" rx="3" fill="#F59E0B" />
    <text x="272" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="9" font-weight="700" fill="#FFFFFF" text-anchor="middle">ตรวจ</text>
  </g>
  <line x1="26" y1="240" x2="314" y2="240" stroke="#F5F5F4" stroke-width="1" />

  <!-- Q5 (Correct: E) -->
  <g transform="translate(26, 246)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">5</text>
    <circle cx="78" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="118" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="158" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <path d="M 266 11 L 270 15 L 278 7" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <line x1="26" y1="271" x2="314" y2="271" stroke="#F5F5F4" stroke-width="1" />

  <!-- Q6-Q10 simplified rows -->
  <g transform="translate(26, 277)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">6</text>
    <circle cx="78" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <circle cx="118" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="158" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <path d="M 266 11 L 270 15 L 278 7" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <line x1="26" y1="302" x2="314" y2="302" stroke="#F5F5F4" stroke-width="1" />

  <g transform="translate(26, 308)">
    <text x="16" y="14" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="600" fill="#44403C" text-anchor="middle">7</text>
    <circle cx="78" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="118" cy="11" r="8.5" fill="#292524" stroke="#1C1917" stroke-width="1.2" />
    <circle cx="158" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="198" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <circle cx="238" cy="11" r="8.5" stroke="#D6D3D1" stroke-width="1.2" fill="#FFFFFF" />
    <path d="M 266 11 L 270 15 L 278 7" stroke="#10B981" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" fill="none" />
  </g>
  <line x1="26" y1="333" x2="314" y2="333" stroke="#F5F5F4" stroke-width="1" />

  <!-- Score Summary Badge at bottom -->
  <g transform="translate(26, 360)">
    <rect x="0" y="0" width="288" height="66" rx="10" fill="#FBF9F5" stroke="#E7E5E4" stroke-width="1" />
    <text x="18" y="28" font-family="var(--font-sans), system-ui, sans-serif" font-size="12" fill="#78716C">คะแนนรวมที่ได้</text>
    <text x="18" y="49" font-family="var(--font-sans), system-ui, sans-serif" font-size="20" font-weight="800" fill="#047857">8 <tspan font-size="13" font-weight="500" fill="#78716C">/ 10 คะแนน</tspan></text>
    <rect x="188" y="18" width="84" height="28" rx="6" fill="#10B981" />
    <text x="230" y="36" font-family="var(--font-sans), system-ui, sans-serif" font-size="11" font-weight="700" fill="#FFFFFF" text-anchor="middle">ตรวจผ่าน ✓</text>
  </g>
</svg>"""

ill_dir.joinpath("paper-answer-sheet-2d.svg").write_text(answer_sheet_svg, encoding="utf-8")
print("Saved paper-answer-sheet-2d.svg")

# 2. Workflow Step Icons
step_import = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
  <rect width="48" height="48" rx="12" fill="#ECFDF5"/>
  <path d="M14 18C14 15.7909 15.7909 14 18 14H30C32.2091 14 34 15.7909 34 18V32C34 34.2091 32.2091 36 30 36H18C15.7909 36 14 34.2091 14 32V18Z" stroke="#059669" stroke-width="2"/>
  <circle cx="24" cy="25" r="4" stroke="#059669" stroke-width="2"/>
  <path d="M20 14V12C20 11.4477 20.4477 11 21 11H27C27.5523 11 28 11.4477 28 12V14" stroke="#059669" stroke-width="2"/>
</svg>"""

step_detect = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
  <rect width="48" height="48" rx="12" fill="#EFF6FF"/>
  <rect x="15" y="12" width="18" height="24" rx="3" stroke="#2563EB" stroke-width="2"/>
  <circle cx="20" cy="18" r="1.5" fill="#2563EB"/>
  <circle cx="24" cy="18" r="1.5" stroke="#93C5FD" stroke-width="1"/>
  <circle cx="28" cy="18" r="1.5" stroke="#93C5FD" stroke-width="1"/>
  <circle cx="20" cy="24" r="1.5" stroke="#93C5FD" stroke-width="1"/>
  <circle cx="24" cy="24" r="1.5" fill="#2563EB"/>
  <circle cx="28" cy="24" r="1.5" stroke="#93C5FD" stroke-width="1"/>
  <line x1="12" y1="28" x2="36" y2="28" stroke="#3B82F6" stroke-width="2" stroke-dasharray="2 2"/>
</svg>"""

step_review = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
  <rect width="48" height="48" rx="12" fill="#FFFBEB"/>
  <circle cx="22" cy="22" r="8" stroke="#D97706" stroke-width="2"/>
  <path d="M28 28L35 35" stroke="#D97706" stroke-width="2.5" stroke-linecap="round"/>
  <path d="M19 22L21 24L25 19" stroke="#D97706" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
</svg>"""

step_export = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" fill="none">
  <rect width="48" height="48" rx="12" fill="#F0FDF4"/>
  <path d="M14 12C14 10.8954 14.8954 10 16 10H27L34 17V36C34 37.1046 33.1046 38 32 38H16C14.8954 38 14 37.1046 14 36V12Z" stroke="#16A34A" stroke-width="2"/>
  <path d="M26 10V18H34" stroke="#16A34A" stroke-width="1.5"/>
  <line x1="19" y1="24" x2="29" y2="24" stroke="#16A34A" stroke-width="2" stroke-linecap="round"/>
  <line x1="19" y1="29" x2="29" y2="29" stroke="#16A34A" stroke-width="2" stroke-linecap="round"/>
</svg>"""

icon_dir.joinpath("step-import.svg").write_text(step_import, encoding="utf-8")
icon_dir.joinpath("step-detect.svg").write_text(step_detect, encoding="utf-8")
icon_dir.joinpath("step-review.svg").write_text(step_review, encoding="utf-8")
icon_dir.joinpath("step-export.svg").write_text(step_export, encoding="utf-8")
print("Saved step icons SVGs")
