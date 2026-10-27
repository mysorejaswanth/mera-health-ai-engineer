"""Evaluate baseline and final extraction against the supplied eight gold labels.

Run from the repository root: python eval/evaluate.py
"""
from __future__ import annotations
import json
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(EVAL_DIR))
from extract import extract as final_extract  # noqa: E402
from baseline_extract import extract as baseline_extract  # noqa: E402

ALIASES = {
    "haemoglobin": "hemoglobin", "hemoglobin hb": "hemoglobin", "hemoglobin": "hemoglobin",
    "total rbc count": "rbc count", "rec count": "rbc count", "rbc count": "rbc count",
    "packed cell volume pcv": "hematocrit", "hematocrit": "hematocrit",
    "mean corpuscular volume": "mcv", "mcv": "mcv",
    "mean corpuscular hb": "mch", "mch": "mch",
    "mean corp hb conc": "mchc", "mean corpuscular hb conc": "mchc", "mchc": "mchc",
    "rdw cv": "rdw", "rdw": "rdw",
    "total wbc count": "wbc count", "total leucocyte count": "wbc count",
    "platelet count": "platelets", "platelets": "platelets",
    "serum triglycerides": "triglycerides", "triglycerides": "triglycerides", "tg": "triglycerides",
    "cholesterol total": "total cholesterol", "s cholesterol": "total cholesterol", "total cholesterol": "total cholesterol",
    "cholesterol hdl": "hdl", "hdl c": "hdl", "hdl": "hdl",
    "cholesterol ldl": "ldl", "ldl c direct": "ldl", "ldl c": "ldl", "ldl": "ldl",
    "cholesterol vldl": "vldl", "vldl": "vldl",
    "tc hdl ratio": "chol hdl ratio", "chol hdl": "chol hdl ratio",
    "aspartate aminotransferase": "ast", "ast": "ast", "sgot": "ast",
    "alanine aminotransferase": "alt", "alt": "alt", "sgpt": "alt",
    "albumin globulin ratio": "a g ratio", "albumin globulin ratio": "a g ratio",
    "tri iodothyronine t3": "t3", "triiodothyronine t3": "t3", "t3": "t3",
    "thyroxine t4": "t4", "t4": "t4",
    "thyroid stimulating hormone": "tsh", "tsh ultrasensitive": "tsh",
    "vit d total": "vitamin d", "25 hydroxy vitamin d": "vitamin d", "vitamin d": "vitamin d",
    "vit b12": "vitamin b12", "cyanocobalamin b12": "vitamin b12",
    "glycated hb": "hba1c", "glycosylated haemoglobin hba1c": "hba1c", "glycosylated hemoglobin hba1c": "hba1c", "hba1c": "hba1c",
    "fbs": "fasting glucose", "glucose fasting": "fasting glucose",
    "ppbs": "postprandial glucose", "glucose pp": "postprandial glucose",
    "sodium na": "sodium", "sodium": "sodium", "potassium k": "potassium", "potassium": "potassium",
    "chloride cl": "chloride", "chloride": "chloride",
    "colour": "urine colour", "color": "urine colour",
    "clarity": "urine clarity", "appearance": "urine clarity",
    "reaction ph": "urine ph", "ph": "urine ph",
    "specific gravity": "specific gravity", "sp gravity": "specific gravity",
    "ketone bodies": "ketones", "ketones": "ketones",
    "urine protein": "urine albumin", "albumin": "urine albumin", "urine glucose": "urine sugar", "sugar": "urine sugar",
    "leucocytes": "pus cells", "pus cells wbc": "pus cells", "erythrocytes": "urine rbc", "rbc": "urine rbc",
    "esr westergren": "esr", "crp": "crp", "urea": "urea", "creatinine": "creatinine",
    "serum uric acid": "uric acid", "uric acid": "uric acid", "protein total": "total protein",
    "serum albumin": "serum albumin", "serum globulin": "serum globulin", "alp": "alp",
    "total bilirubin": "total bilirubin", "direct bilirubin": "direct bilirubin", "indirect bilirubin": "indirect bilirubin",
    "neutrophils": "neutrophils", "lymphocytes": "lymphocytes", "eosinophils": "eosinophils",
    "monocytes": "monocytes", "basophils": "basophils", "pale yellow": "pale yellow",
}


def norm_name(value) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()
    value = re.sub(r"\s+", " ", value)
    return ALIASES.get(value, value)


def norm_value(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().replace(",", "")
    s = re.sub(r"\s*[-–—]\s*", "-", s)
    s = re.sub(r"\s+", " ", s).casefold()
    try:
        # Decimal equality avoids treating 3.0 and 3 as different values.
        return "num:" + str(Decimal(s))
    except InvalidOperation:
        return "txt:" + s


def norm_unit(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().casefold().replace("μ", "µ")
    s = re.sub(r"\s+", "", s)
    return {"g/dl": "g/dl", "pg": "pg", "fl": "fl", "u/l": "u/l", "mmol/l": "mmol/l"}.get(s, s)


def norm_range(value) -> str:
    if value is None:
        return ""
    s = str(value).strip().casefold().replace("≤", "<").replace("≥", ">")
    s = re.sub(r"\s*[-–—]\s*", " - ", s)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*(<|>)\s*", r"\1 ", s)
    return s.strip()


def score_report(gold: list[dict], predicted: list[dict]) -> dict:
    remaining = set(range(len(predicted)))
    matches = []
    for g in gold:
        key = norm_name(g.get("test_name"))
        candidates = [i for i in remaining if norm_name(predicted[i].get("test_name")) == key]
        if not candidates:
            matches.append((g, None))
            continue
        def candidate_score(i):
            p = predicted[i]
            return sum([
                norm_value(p.get("value")) == norm_value(g.get("value")),
                norm_unit(p.get("unit")) == norm_unit(g.get("unit")),
                norm_range(p.get("reference_range")) == norm_range(g.get("reference_range")),
            ])
        selected = max(candidates, key=candidate_score)
        remaining.remove(selected)
        matches.append((g, predicted[selected]))

    field_ok = {k: 0 for k in ("test_name", "value", "unit", "reference_range")}
    exact_rows = 0
    name_matches = 0
    errors = []
    for g, p in matches:
        if p is None:
            errors.append({"test_name": g.get("test_name"), "issue": "missing row"})
            continue
        name_matches += 1
        field_ok["test_name"] += 1
        flags = {}
        for field, normalizer in (("value", norm_value), ("unit", norm_unit), ("reference_range", norm_range)):
            flags[field] = normalizer(g.get(field)) == normalizer(p.get(field))
            field_ok[field] += int(flags[field])
        if all(flags.values()):
            exact_rows += 1
        else:
            errors.append({"test_name": g.get("test_name"), "predicted": {k: p.get(k) for k in ("value", "unit", "reference_range")},
                           "gold": {k: g.get(k) for k in ("value", "unit", "reference_range")}, "field_matches": flags})

    total = len(gold)
    precision = exact_rows / len(predicted) if predicted else 0.0
    recall = exact_rows / total if total else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {
        "gold_rows": total, "predicted_rows": len(predicted), "name_recall": round(name_matches / total, 4) if total else 0,
        "exact_rows": exact_rows, "exact_row_precision": round(precision, 4), "exact_row_recall": round(recall, 4),
        "exact_row_f1": round(f1, 4),
        "field_accuracy": {k: round(v / total, 4) if total else 0 for k, v in field_ok.items()},
        "errors": errors,
    }


def main() -> None:
    reports = []
    for gold_path in sorted((ROOT / "gold").glob("*.json")):
        report_path = ROOT / "reports" / f"{gold_path.stem}.pdf"
        if not report_path.exists():
            report_path = ROOT / "reports" / f"{gold_path.stem}.jpg"
        gold = json.loads(gold_path.read_text(encoding="utf-8"))["tests"]
        started = time.perf_counter()
        baseline = baseline_extract(report_path)["tests"]
        baseline_latency = time.perf_counter() - started
        started = time.perf_counter()
        final = final_extract(report_path)["tests"]
        final_latency = time.perf_counter() - started
        reports.append({
            "report": gold_path.stem,
            "baseline": {**score_report(gold, baseline), "latency_seconds": round(baseline_latency, 3), "cost_usd_per_report": 0.0},
            "final": {**score_report(gold, final), "latency_seconds": round(final_latency, 3), "cost_usd_per_report": 0.0},
            "gold": gold,
        })
        print(f"evaluated {gold_path.stem}: baseline={len(baseline)} rows, final={len(final)} rows; final_latency={reports[-1]['final']['latency_seconds']:.3f}s", flush=True)
    def aggregate(which: str) -> dict:
        total_gold = sum(r[which]["gold_rows"] for r in reports)
        total_pred = sum(r[which]["predicted_rows"] for r in reports)
        exact = sum(r[which]["exact_rows"] for r in reports)
        name_correct = sum(round(r[which]["name_recall"] * r[which]["gold_rows"]) for r in reports)
        field_counts = {k: sum(round(r[which]["field_accuracy"][k] * r[which]["gold_rows"]) for r in reports)
                        for k in ("test_name", "value", "unit", "reference_range")}
        precision = exact / total_pred if total_pred else 0.0
        recall = exact / total_gold if total_gold else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        return {
            "gold_rows": total_gold, "predicted_rows": total_pred, "name_recall": round(name_correct / total_gold, 4),
            "exact_rows": exact, "exact_row_precision": round(precision, 4), "exact_row_recall": round(recall, 4),
            "exact_row_f1": round(f1, 4),
            "field_accuracy": {k: round(v / total_gold, 4) for k, v in field_counts.items()},
            "mean_latency_seconds": round(sum(r[which]["latency_seconds"] for r in reports) / len(reports), 3),
            "cost_usd_per_report": 0.0,
        }

    result = {
        "methodology": {
            "labelled_reports": len(reports),
            "matching": "greedy row matching after documented common-name synonym normalization; numeric values use Decimal equality; unit/range comparison is case/spacing normalized",
            "full_row": "test name, value, unit and report-provided reference range must all match; missing prediction counts as incorrect",
            "cost": "zero API spend; local CPU time and energy are not monetized",
            "baseline_note": "local first-page 200-DPI Tesseract OCR baseline; not the supplied Gemini result, which could not be run without a key",
        },
        "aggregate": {"baseline": aggregate("baseline"), "final": aggregate("final")},
        "reports": [{k: v for k, v in r.items() if k != "gold"} for r in reports],
        "gold_mismatch_audit": [{"report": "report_01", "test_name": "Platelet Count", "gold_value": "304000", "source_value": "340000",
                                 "note": "The supplied gold label conflicts with the readable PDF. Kept unchanged in the primary score."}],
        "unlabelled_manual_review": [
            {"report": "report_04", "assessment": "9 numeric renal/glycaemic rows extracted from native PDF text; spot-checked against visible table."},
            {"report": "report_07", "assessment": "9 liver-profile rows extracted from scan OCR; OCR is noisy on albumin/globulin values, so those rows require manual verification."},
            {"report": "report_10", "assessment": "Manual review shows a two-column thyroid/renal/electrolyte table. The parser extracts only three electrolyte rows and OCR reads potassium as 34 rather than 3.1; substantial table-aware OCR work remains."},
            {"report": "report_12", "assessment": "No completed lab results are present: the image is a physician note listing tests advised. Zero extracted rows is the expected behavior."},
        ],
    }
    (EVAL_DIR / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def pct(x):
        from decimal import ROUND_HALF_UP
        return f"{(Decimal(str(x)) * Decimal(100)).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}%"
    rows = [
        "# Evaluation results", "",
        "> Reproduce with `python eval/evaluate.py`. The local OCR baseline is not the supplied Gemini result; no API was called.", "",
        "| Metric | Local baseline | Final |", "|---|---:|---:|",
    ]
    b, f = result["aggregate"]["baseline"], result["aggregate"]["final"]
    for label, key in [("Exact-row precision", "exact_row_precision"), ("Exact-row recall", "exact_row_recall"), ("Exact-row F1", "exact_row_f1")]:
        rows.append(f"| {label} | {pct(b[key])} | {pct(f[key])} |")
    rows += [
        f"| Predicted rows / gold rows | {b['predicted_rows']} / {b['gold_rows']} | {f['predicted_rows']} / {f['gold_rows']} |",
        f"| Mean latency per labelled report | {b['mean_latency_seconds']:.3f}s | {f['mean_latency_seconds']:.3f}s |",
        "| API cost per report | $0.00 | $0.00 |", "",
        "## Per-report exact-row results", "", "| Report | Gold rows | Baseline exact | Final exact | Baseline rows | Final rows |", "|---|---:|---:|---:|---:|---:|",
    ]
    for r in reports:
        rows.append(f"| {r['report']} | {r['baseline']['gold_rows']} | {r['baseline']['exact_rows']} | {r['final']['exact_rows']} | {r['baseline']['predicted_rows']} | {r['final']['predicted_rows']} |")
    rows += ["", "## Field accuracy (denominator = all gold rows; missing rows count as incorrect)", "", "| Field | Local baseline | Final |", "|---|---:|---:|"]
    for k in ("test_name", "value", "unit", "reference_range"):
        rows.append(f"| {k} | {pct(b['field_accuracy'][k])} | {pct(f['field_accuracy'][k])} |")
    rows += ["", "## Label audit", "", "`report_01` gold labels Platelet Count as 304000, but the PDF's readable text says 340000. The supplied label is not edited; this row is marked incorrect in the primary score.", ""]
    (EVAL_DIR / "results.md").write_text("\n".join(rows), encoding="utf-8")
    print(json.dumps({"aggregate": result["aggregate"], "results_markdown": str(EVAL_DIR / "results.md")}, indent=2))

if __name__ == "__main__":
    main()
