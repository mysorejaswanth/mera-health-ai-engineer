# Lab-report extractor — findings and decisions

## Run

Python 3.10+. Install Poppler (`pdftotext`, `pdftoppm`) and Tesseract OCR with English data.

```bash
python -m pip install -r requirements.txt
python extract.py reports/report_01.pdf  # one file -> JSON on stdout
python eval/evaluate.py                  # baseline/final metrics
python eval/smoke_test.py                # schema/entry-point check on all 12 files
```

Ubuntu: `sudo apt-get install poppler-utils tesseract-ocr`. macOS: `brew install poppler tesseract`. No API key or network call is used by the final pipeline. The original Gemini implementation is preserved in `eval/supplied_gemini_baseline.py`; its prompt and why it was not run are in `eval/prompts.md`.

## Results

The supplied Gemini baseline could not run without `GEMINI_API_KEY`; I do **not** claim these results beat Gemini. I measured a reproducible substitute: first PDF page at 200 DPI + Tesseract PSM 6 + a common label/range parser, then compared the final local pipeline on the same eight labelled reports (138 gold rows). `eval/results.json` has all per-report metrics and timings.

| Metric | Local OCR baseline | Final |
|---|---:|---:|
| Exact-row precision / recall / F1 | 66.7 / 43.5 / 52.6% | 83.0 / 81.2 / 82.1% |
| Field accuracy (name / value / unit / range) | 64.5 / 50.0 / 48.6 / 54.4% | 97.8 / 89.1 / 84.1 / 88.4% |
| Predicted / gold rows | 90 / 138 | 135 / 138 |
| Mean latency per labelled report | 4.438 s | 4.086 s |
| API cost per report | $0.00 | $0.00 |

Exact row = normalized test name, value, unit and report-provided reference range all match; missing rows/fields count as wrong. Numeric formatting (`3.0` vs `3`), case and whitespace are normalized. This is a small-data proxy, not clinical validation. Gold remains unchanged: report 01 labels Platelet Count as `304000`, but the readable PDF text says `340000`; the row remains scored wrong.

## Three failure categories

1. **Page coverage and resolution — report 11.** The supplied code renders PDFs at only 60 DPI and sends page 1; smaller table text is hard to read and later pages are omitted. The final uses the PDF text layer when available; otherwise it OCRs every page at 200 DPI. Report 11 rises from 27/54 to 54/54 exact rows.
2. **OCR loses decimals, hyphens and table associations — reports 05/06/10.** Report 06 yields pH `65` instead of `6.5` and Leucocytes `23` instead of `2-3`; units/ranges are also lost. Report 10's shadowed, two-column photo yields potassium `34` instead of `3.1` and misses most results. Multiple OCR layouts/crops help some rows but not these ambiguities; low-confidence outputs need improved image/table handling or human review.
3. **Unsafe value/range handling — starter `PROMPT`, `clean()`, `parse()`.** The prompt requests invented standard ranges and numeric-only values; `clean()` converts textual results and comparators to `null`, while malformed model JSON can silently become an empty list. The final preserves qualitative/comparator values, represents missing ranges as `null`, never invents ranges/status, and makes local-tool failures explicit.

## Failed experiment

A single-view PSM 6 pass scored **110/138 exact rows (F1 81.5%; mean 1.51 s/report)**. Adding multiple Tesseract layouts/crops with field consensus gave **112/138 (F1 82.1%; 2.03 s/report)**, but report 06 stayed at **6/12 exact rows**. The modest global gain costs more latency and does not solve the hardest scan; I kept it for the net improvement while documenting this limit.

## Unlabelled reports

- **04:** nine numeric renal/glycaemic rows from native PDF text; spot-checked visually.
- **07:** nine liver-profile rows found, but albumin/globulin OCR needs manual verification.
- **10:** only three electrolyte rows extracted from a larger thyroid/renal/electrolyte table; potassium is wrong (`34` vs `3.1`).
- **12:** a physician note listing advised tests, not completed results; zero rows is correct.

## RAG, fine-tuning, agents

- **RAG:** Not for first-pass extraction—retrieval cannot restore a missing decimal or associate a value with a row in a photo. A lab/unit dictionary may help normalize names after extraction; ranges must remain report-sourced or be separately labelled as external data.
- **Fine-tuning:** Not yet. Eight labelled reports and at least one noisy gold value are insufficient to justify tuning without overfitting. Collect diverse, corrected labels first and keep this evaluation fixed.
- **Multi-step agent:** Not earned. PDF text → OCR fallback → conservative parsing is easier to inspect and cheaper. An agent cannot safely infer lost medical values; route uncertain rows to review instead.

## Decision log

`PLAN.md` was committed first and not edited. With no Gemini key, I used and labelled a local comparator rather than fabricate results. I preserved `extract.py` as the required entry point, kept gold unchanged, checked report 01's conflicting platelet label against source text, and avoided report-specific value patches. Local CPU cost/energy is not monetized. This is a prototype, not clinically validated software.
