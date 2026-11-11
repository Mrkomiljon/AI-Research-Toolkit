# Foydalanuvchi qo'llanmasi (o'zbek tilida)

AI Research Toolkit — Claude Code yoki OpenAI Codex ichida ishlaydigan 15 ta "skill" (ko'nikma) va ularga xizmat
qiluvchi Python dvigateli (`rtk`). U tadqiqotchiga **yordamchi**, avtonom tadqiqotchi emas: maqola topadi, tahlil
qiladi, taqqoslaydi, bo'shliq nomzodlarini taklif qiladi, qo'lyozma tuzilmasini yaratadi, iqtiboslarni tekshiradi,
taqriz simulyatsiyasini beradi va jarayonni hisoblaydi. Hech qachon maqola, DOI, natija yoki raqam o'ylab topmaydi.

## 1. O'rnatish (qisqa)

```bash
python -m pip install ai-research-toolkit
cd C:\Users\siz\tadqiqot
npx skills add Mrkomiljon/AI-Research-Toolkit -a claude-code   # yoki -a codex
```

Node.js bo'lmasa: repo'ni klon qilib `python scripts/install.py --agent all --scope project --project-dir C:\Users\siz\tadqiqot` ishlating.

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
| "Qo'lyozmadagi da'volarni tekshir" | claim-verifier | `reviews/claims.json`, `claim-verification.md`, `claim-verification.xlsx` |
| "Bu bo'shliq allaqachon o'rganilganmi?" | gap-validator | `analysis/gap-counterevidence.json`, `gap-validation.md`, `gap-validation.xlsx` |
| "Tadqiqot konsepsiyasini tuzib ber" | research-concept-builder | `manuscript/gap-canvas.md`, `concept-paper.md`, `concept-paper.docx` |
| "Tadqiqotimda qayerdaman?" | research-progress | `progress/project-status.json`, `research-progress.xlsx`, `next-actions.md` |
| "Matnni ilmiy uslubda tahrirla" | academic-writing | `manuscript/writing-report.md` (har bir o'zgarish ro'yxati), `edited-draft.md`, `style-checklist.md` |
| "Maqolani xalqaro nashr standartlariga moslashtir" | journal-standards | `reviews/reporting-checklist.xlsx` (CONSORT/STROBE/STARD/TRIPOD/PRISMA…), `journal-compliance.md`, `cover-letter-draft.docx` |

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

To'liq matn olish: agent `rtk fetch` bilan ochiq (open-access) PDF'larni avtomatik topadi — arXiv, Europe PMC, Unpaywall, OpenAlex — va `papers/PDFs/` ga yuklaydi; manba `FULL_TEXT` bo'ladi. Pullik maqolalar `ABSTRACT_ONLY` qoladi: PDF'ni o'zingiz `papers/PDFs/` ga ko'chiring va agentga ayting (`rtk sources attach-pdf`).

## 6. Dalil (evidence) tizimi

Har bir da'vo `src-…` (manba) va `ev-…` (dalil) identifikatorlari bilan bog'lanadi. Dalilda `verified_by` bo'ladi:
`tool` (so'zma-so'z parcha matnda topildi), `human` (siz tasdiqladingiz), `llm` (faqat model o'qidi — bu holat
hech qachon "verified" hisoblanmaydi). Sintez yoki bo'shliq matnida identifikatorsiz paragraf bo'lsa, tekshiruv
(`rtk review validate-links`) uni rad etadi.

## 7. Jarayon holati

`rtk status` yoki "Qayerdaman?" so'rovi bosqichlarni faqat diskdagi fayllar asosida hisoblaydi:
`not_started` → `in_progress` → `awaiting_user_review` → `completed`, yoki `blocked` (sabab bilan). Foizlar
taxmin qilinmaydi; "8 bosqichdan 3 tasi bajarildi" kabi sanoq beriladi.

## 7a. Jarayonni kuzatish

Agentni interaktiv ochsangiz (`claude` yoki `codex`, terminalda yoki VS Code kengaytmasida), har bir qadam jonli
ko'rinadi: reja, tasdiq so'rovi, har bir `rtk` chaqiruvi va yozilgan fayllar. Qo'shimcha ravishda ikkinchi terminalda:

```bash
rtk log -p workspace/<slug> --follow     # workflow/runs.jsonl ni jonli kuzatadi
rtk status -p workspace/<slug>
```

Natijalar oddiy fayllar (`.md`, `.xlsx`, `.docx`, `.json`) — VS Code, Excel yoki Word'da ochiladi.

## 8. Uzilib qolsa

Agent yoki kompyuter o'chib qolsa, hamma narsa `workflow/plan.yaml` va `workflow/runs.jsonl` da saqlangan.
"Davom et" deysiz — agent `rtk resume` qiladi, tugallangan va hali ham to'g'ri bosqichlarni qayta bajarmaydi.

## 8a. Yozish va nashr standartlari (1.2 dan)

- **academic-writing** matnni *qanday* yozilganini yaxshilaydi: aniqlik, qisqalik, zamon/majhul nisbat, qisqartmalar, hedging. *Nima* da'vo qilinganini o'zgartirmaydi: raqamlar, iqtiboslar va xulosalar o'zgarishsiz qoladi, dvigatel buni avtomatik solishtiradi. Har bir tahrir `writing-report.md` da "asl → tahrir (sabab)" ko'rinishida yoziladi, siz qabul qilasiz yoki rad etasiz.
- **journal-standards** tadqiqot turiga mos xalqaro hisobot checklistini (masalan, diagnostika uchun STARD, AI modellari uchun TRIPOD+AI) va jurnal talablarini (so'z limiti, abstrakt formati, deklaratsiyalar: etika, manfaatlar to'qnashuvi, ma'lumot/kod mavjudligi, AI-use) tekshiradi, cover letter qoralamasini beradi. Jurnal talablarini siz `reviews/journal-guidelines.txt` ga qo'yasiz; bo'lmasa limitlar "tekshirilmadi" deb yoziladi.
- Plagiat bo'yicha: `academic-integrity` to'g'ri iqtibos va parafraza qoidalarini tekshiradi; o'xshashlik detektorlarini aldash yoki "plagiatdan xoli" sertifikat — yo'q.

## 8b. Tekshiruv va konsepsiya (1.4 dan)

- **Skan qilingan PDF (OCR).** `python -m pip install "ai-research-toolkit[ocr]"` (Docling; katta yuklama) yoki Tesseract o'rnatilsa, matn qatlami yo'q sahifalar avtomatik o'qiladi. `rtk ocr status` holatni ko'rsatadi. OCR matnida xato bo'lishi mumkin, shuning uchun bunday sahifalardan olingan iqtiboslar "skan bilan solishtiring" deb belgilanadi. OCR bo'lmasa, sahifa "o'qilmadi" deb yoziladi va mazmuni taxmin qilinmaydi.
- **claim-verifier** har bir iqtibosli gap uchun hukm chiqaradi: `supported` (tasdiqlaydi), `contradicted` (zid), `insufficient` (dalil yetarli emas). Hukm faqat manbadan so'zma-so'z parcha topilgandagina qabul qilinadi; parcha topilmasa yoki boshqa manbadan bo'lsa, dvigatel hukmni `insufficient`ga tushiradi. `citation-verifier` faqat DOI/metadata'ni tekshiradi, bu skill esa mazmunni.
- **gap-validator** har bir bo'shliq nomzodi uchun "buni allaqachon kim qilgan?" degan maqsadli qidiruv o'tkazadi va `open` / `partially_addressed` / `already_addressed` / `inconclusive` belgisini qo'yadi. `open` — shu qidiruvda qarshi dalil topilmadi degani, ilmiy yangilik isboti emas (Scopus, Web of Science qidirilmaydi).
- **research-concept-builder** tanlangan bo'shliqdan Gap Canvas va konsepsiya hujjatini (Word) tuzadi. Metod, ma'lumot, resurs va muddatlarni siz berasiz; siz bermagan qism `[AUTHOR INPUT NEEDED: …]` bo'lib qoladi, agent taklif qilgan qism esa `UNCONFIRMED` deb belgilanadi.
- Uchala natija ham `human_review: pending` holatida turadi: yakuniy qaror tadqiqotchi va ekspertniki.

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
