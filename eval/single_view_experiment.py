"""Reproduce the unsuccessful single-view OCR experiment.

Run from repo root: python eval/single_view_experiment.py
This deliberately limits scan/photo input to one full-page Tesseract PSM 6 pass.
It reuses the same labels, matching and scoring as eval/evaluate.py.
"""
from __future__ import annotations
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EVAL))
import extract  # noqa: E402
from evaluate import score_report  # noqa: E402

# Avoid work inside the multi-view helper; execute exactly one PSM 6 OCR pass.
def one_view(path: Path, scratch: Path, page_tag: str, include_crops: bool = True):
    return [(extract._ocr_image(path, "6"), True)]


def main() -> None:
    extract._ocr_views = one_view
    reports = []
    for gold_path in sorted((ROOT / "gold").glob("*.json")):
        report_path = ROOT / "reports" / f"{gold_path.stem}.pdf"
        if not report_path.exists():
            report_path = ROOT / "reports" / f"{gold_path.stem}.jpg"
        gold = json.loads(gold_path.read_text(encoding="utf-8"))["tests"]
        started = time.perf_counter()
        predicted = extract.extract(report_path)["tests"]
        latency = time.perf_counter() - started
        score = score_report(gold, predicted)
        reports.append({"report": gold_path.stem, **score, "latency_seconds": round(latency, 3)})
        print(f"{gold_path.stem}: {score['exact_rows']}/{score['gold_rows']} exact; {latency:.3f}s", flush=True)
    gold_rows = sum(r["gold_rows"] for r in reports)
    predicted_rows = sum(r["predicted_rows"] for r in reports)
    exact_rows = sum(r["exact_rows"] for r in reports)
    precision = exact_rows / predicted_rows if predicted_rows else 0
    recall = exact_rows / gold_rows if gold_rows else 0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
    result = {
        "experiment": "one full-page Tesseract PSM 6 view per image/scan page; same parser, gold and score as final",
        "gold_rows": gold_rows,
        "predicted_rows": predicted_rows,
        "exact_rows": exact_rows,
        "exact_row_precision": round(precision, 4),
        "exact_row_recall": round(recall, 4),
        "exact_row_f1": round(f1, 4),
        "mean_latency_seconds": round(sum(r["latency_seconds"] for r in reports) / len(reports), 3),
        "report_06_exact_rows": next({"exact_rows": r["exact_rows"], "gold_rows": r["gold_rows"]} for r in reports if r["report"] == "report_06"),
        "reports": reports,
    }
    (EVAL / "single_view_experiment.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "reports"}, indent=2))

if __name__ == "__main__":
    main()
