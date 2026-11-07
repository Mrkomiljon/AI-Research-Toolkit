# Foydalanuvchi qo'llanmasi (o'zbek tilida)

AI Research Toolkit — Claude Code yoki OpenAI Codex ichida ishlaydigan 10 ta "skill" (ko'nikma) va ularga xizmat
qiluvchi Python dvigateli (`rtk`). U tadqiqotchiga **yordamchi**, avtonom tadqiqotchi emas: maqola topadi, tahlil
qiladi, taqqoslaydi, bo'shliq nomzodlarini taklif qiladi, qo'lyozma tuzilmasini yaratadi, iqtiboslarni tekshiradi,
taqriz simulyatsiyasini beradi va jarayonni hisoblaydi. Hech qachon maqola, DOI, natija yoki raqam o'ylab topmaydi.

## 1. O'rnatish (qisqa)

```bash
git clone https://github.com/Mrkomiljon/AI-Research-Toolkit.git
cd AI-Research-Toolkit
python -m pip install -e .
python scripts/install.py --agent claude --scope project --project-dir C:\Users\siz\tadqiqot   # yoki --agent codex
python scripts/doctor.py
```

Agentni (Claude Code yoki Codex) `C:\Users\siz\tadqiqot` papkasida oching. Batafsil: `docs/installation.md`.

## 1a. Xarajatlar va obunalar

Toolkit'ning o'zi bepul (MIT), OpenAlex va Crossref API'lari ham bepul va kalit talab qilmaydi. Pul faqat agent uchun to'lanadi:

| Agent | Nima kerak | Izoh |
|---|---|---|
| Claude Code | Claude Pro yoki Max obunasi, **yoki** Anthropic API kaliti (token bo'yicha to'lov) | Pro'da soatlik limit tezroq tugaydi; uzun sessiyalar uchun Max qulay |
| Codex | ChatGPT Plus / Pro / Business / Edu / Enterprise, **yoki** OpenAI API kaliti | `codex login` bilan kiriladi |

Bitta agent yetarli; skill'lar ikkalasida bir xil ishlaydi. Narxlar va limitlar tez o'zgaradi: claude.com/pricing va openai.com/chatgpt/pricing sahifalarini tekshiring.

## 2. Loyihani boshlash

Agentga yozing:

> Use research-orchestrator. Mening PhD tadqiqotimni "sun'iy intellekt yordamida paxta hosildorligini bashorat qilish" mavzusida boshlab ber.

Agent qisqa so'rovnoma o'tkazadi: mavzu, maqsadlar, soha, chiqish tili, yillar oralig'i, jurnal (ixtiyoriy), mavjud
PDF'lar, maxfiylik cheklovlari. Natijada `workspace/<slug>/` papkasi va `project.yaml` yaratiladi.

**Muhim eslatma:** Claude Code / Codex sizning so'rovlaringizni va agent o'qigan matnlarni o'z provayderining bulutiga
yuboradi. "Local-first" — fayllar kompyuteringizda qoladi degani, lekin modelning o'zi oflayn emas.

## 3. Oddiy so'rovlar va qaysi skill ishlaydi

| Siz yozasiz | Ishlaydigan skill(lar) | Natija fayllari |
|---|---|---|
| "2021 yildan beri paxta hosildorligi va ML bo'yicha 20 ta maqola top" | literature-search | `literature/papers.xlsx`, `papers.csv`, `search-strategy.md`, `search-log.json`, `sources/references.bib` |
| "Bu PDF'ni tahlil qil" | paper-analyzer | `analysis/<src-id>/paper-analysis.md/.json`, `evidence/evidence.jsonl` |
| "Bu maqolalarni taqqosla" | paper-analyzer (faqat yetishmaganlari) → literature-review | `literature/literature-matrix.xlsx`, `literature-synthesis.md` |
| "Tadqiqot bo'shliqlarini top" | search → analyzer → review → research-gap-finder | `analysis/research-gaps.md`, `candidate-hypotheses.md`, `feasibility-report.md` |
| "Maqolamni tayyorla" | manuscript-builder → citation-verifier → academic-integrity → peer-reviewer | `manuscript/`, `reviews/` |
| "Qo'lyozmamni tekshir" | citation-verifier → academic-integrity → peer-reviewer | `reviews/citation-audit.md`, `integrity-audit.md`, `peer-review-report.md` |
| "Tadqiqotimda qayerdaman?" | research-progress | `progress/project-status.json`, `research-progress.xlsx`, `next-actions.md` |

Orkestrator avval **rejani ko'rsatadi** (qaysi bosqichlar, qaysi fayllar, API xarajat toifasi: `none`/`low`/
`potentially_paid`), ruxsat kerak bo'lsa so'raydi, keyin bajaradi.

## 4. Siz tasdiqlashingiz shart bo'lgan narsalar

- Ilmiy talqin, bo'shliq/yangilik da'volari, qo'lyozma matni, taqrizchiga javoblar — `awaiting_user_review` holatida
  turadi, siz "tasdiqlayman" deganingizdan keyin `completed` bo'ladi.
- Maqola sonini byudjetdan oshirish, tashqi API'larni maxfiylik rejimida ishlatish, fayllarni tashqariga yuborish.
- Siz tahrirlagan qo'lyozma faylini qayta yozish (agent `--force`siz rad etadi).

## 5. Kirish darajasi (access level) nimani anglatadi

| Belgi | Ma'nosi | Cheklov |
|---|---|---|
| `FULL_TEXT` | PDF mavjud va matn ajratildi | sahifa ko'rsatkichli (`p.4`) iqtiboslar mumkin |
| `ABSTRACT_ONLY` | faqat annotatsiya bor | metod/natija tafsilotlari haqida da'vo qilib bo'lmaydi |
| `METADATA_ONLY` | faqat sarlavha/mualliflar/DOI | faqat bibliografik ma'lumot |

PDF qo'shish: faylni `papers/PDFs/` ga ko'chiring va agentga ayting, u `rtk sources attach-pdf` bilan bog'laydi.

## 6. Dalil (evidence) tizimi

Har bir da'vo `src-…` (manba) va `ev-…` (dalil) identifikatorlari bilan bog'lanadi. Dalilda `verified_by` bo'ladi:
`tool` (so'zma-so'z parcha matnda topildi), `human` (siz tasdiqladingiz), `llm` (faqat model o'qidi — bu holat
hech qachon "verified" hisoblanmaydi). Sintez yoki bo'shliq matnida identifikatorsiz paragraf bo'lsa, tekshiruv
(`rtk review validate-links`) uni rad etadi.

## 7. Jarayon holati

`rtk status` yoki "Qayerdaman?" so'rovi bosqichlarni faqat diskdagi fayllar asosida hisoblaydi:
`not_started` → `in_progress` → `awaiting_user_review` → `completed`, yoki `blocked` (sabab bilan). Foizlar
taxmin qilinmaydi; "8 bosqichdan 3 tasi bajarildi" kabi sanoq beriladi.

## 8. Uzilib qolsa

Agent yoki kompyuter o'chib qolsa, hamma narsa `workflow/plan.yaml` va `workflow/runs.jsonl` da saqlangan.
"Davom et" deysiz — agent `rtk resume` qiladi, tugallangan va hali ham to'g'ri bosqichlarni qayta bajarmaydi.

## 9. Nima qilmaydi

- Jurnalga yubormaydi, institut tizimlariga kirmaydi, e-mail yubormaydi, ma'lumot yuklamaydi.
- "Plagiatdan xoli" sertifikat bermaydi, AI-detektorlarni aldashga yordam bermaydi, qabul qilinishni kafolatlamaydi.
- Siz bermagan metod, natija, statistika, ishtirokchilarni yozmaydi — o'rniga `[MISSING: …]` qo'yadi va
  `manuscript/missing-information.md` da ro'yxat beradi.

## 10. Namuna so'rovlar

- "Use research-orchestrator. 2020–2025 yillar, Sentinel-2 va mashinali o'qitish bilan bug'doy hosildorligi bo'yicha 15 ta maqola top, keyin bo'shliqlarni aniqla."
- "Use paper-analyzer. papers/PDFs/karimov2023.pdf faylini 'qaysi xususiyatlar aniqlikni oshiradi' savoli bo'yicha tahlil qil."
- "Use citation-verifier. manuscript/draft.docx dagi iqtiboslarni sources/references.bib bilan tekshir."
- "Use research-progress. Nima qildik, nima qoldi, nima bloklangan?"

Misol ish maydoni: `examples/agriculture-research/` (haqiqiy OpenAlex/Crossref ma'lumotlari bilan).
