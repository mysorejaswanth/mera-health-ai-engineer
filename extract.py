"""Extract structured lab results from a PDF or image report without an API key.

Usage:
    python extract.py reports/report_01.pdf

Prints JSON with a top-level `tests` array matching schema.json.
Requires Poppler (pdftotext/pdftoppm) and Tesseract OCR on PATH.
"""
from __future__ import annotations
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from PIL import Image

# Labels and spelling variants commonly used in clinical laboratory reports.
# The parser detects labels anywhere within a visual row, allowing paired columns.
LABELS = [
    "Glycosylated Haemoglobin (HbA1c)", "Glycosylated Hemoglobin (HbA1c)",
    "Packed Cell Volume (PCV)", "Aspartate Aminotransferase", "Alanine Aminotransferase",
    "Albumin/Globulin Ratio", "Mean Corpuscular Volume", "Mean Corpuscular Hb Conc.",
    "Mean Corpuscular Hb", "Mean Corp. Hb Conc.", "Thyroid Stimulating Hormone",
    "Triiodothyronine (T3)", "Hemoglobin (Hb)", "E.S.R. (Westergren)",
    "Total Leucocyte Count", "Total WBC Count", "Total RBC Count", "RBC Count",
    "Squamous Epithelial Cells", "Serum Triglycerides", "Cholesterol - Total",
    "Cholesterol - HDL", "Cholesterol - LDL", "Cholesterol - VLDL", "TC/HDL Ratio",
    "LDL-C (Direct)", "25-Hydroxy Vitamin D", "Cyanocobalamin (B12)",
    "Glucose - Fasting", "Glucose - PP", "Total Bilirubin", "Direct Bilirubin",
    "Indirect Bilirubin", "Serum Uric Acid", "Serum Globulin", "Serum Albumin",
    "Specific Gravity", "Sp. Gravity", "Ketone Bodies", "Urine Protein", "Urine Glucose",
    "Pus Cells (WBC)", "Epithelial Cells", "Haemoglobin", "Hemoglobin", "Platelet Count",
    "Platelets", "Hematocrit", "MCV", "MCHC", "MCH", "RDW-CV", "RDW", "Neutrophils",
    "Lymphocytes", "Eosinophils", "Monocytes", "Basophils", "S. Cholesterol", "Total Cholesterol",
    "Triglycerides", "TG", "1G", "HDL-C", "HDL", "LDL-C", "LDL", "VLDL", "Chol/HDL",
    "AST", "SGOT", "ALT", "SGPT", "ALP", "Protein Total", "Thyroxine (T4)", "T3", "T4", "TSH (Ultrasensitive)",
    "TSH", "Vit D Total", "Vitamin D", "Vit B12", "Glycated Hb", "HbA1c", "FBS", "PPBS",
    "Urea", "Creatinine", "Sodium (Na+)", "Sodium", "Potassium (K+)", "Potassium",
    "Chloride (Cl-)", "Chloride", "Colour", "Color", "Clarity", "Appearance", "Reaction (pH)",
    "pH", "Albumin", "Sugar", "Ketones", "Leucocytes", "Erythrocytes", "CRP", "RBC",
    "REC Count", "ROW",
]
LABELS = sorted(set(LABELS), key=len, reverse=True)
LABEL_RE = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(x) for x in LABELS) + r")(?![A-Za-z0-9])", re.I)

NUM = r"\d[\d,]*(?:\.\d+)?"
NUM_RANGE_RE = re.compile(rf"(?:[<>≤≥]\s*)?{NUM}\s*(?:-|–|—|\bto\b)\s*(?:[<>≤≥]\s*)?{NUM}\s*$", re.I)
COMPARATOR_RE = re.compile(rf"[<>≤≥]\s*{NUM}\s*$")
CATEGORY_RANGE_RE = re.compile(r"(?:Pale\s+Yellow|Negative|Clear|Nil|Absent|Normal|None)\s*$", re.I)
UNIT_SUFFIXES = [
    "million/cumm", "mill/cumm", "lakh/cumm", "µIU/mL", "uIU/mL", "mIU/mL", "µg/dL", "ug/dL",
    "ng/mL", "ng/dL", "pg/mL", "mg/dL", "g/dL", "mmol/L", "mmol/l", "U/L", "IU/L",
    "mm/hr", "mm/h", "cells/cumm", "/cumm", "/hpf", "fl", "fL", "pg", "%o", "%",
]
UNIT_RE = re.compile(r"\s*(" + "|".join(re.escape(x) for x in sorted(UNIT_SUFFIXES, key=len, reverse=True)) + r")\s*$", re.I)
QUALITATIVE_VALUES = {
    "negative", "positive", "present", "present (+)", "present (-)", "absent", "trace",
    "nil", "clear", "cloudy", "turbid", "pale yellow", "dark yellow", "yellow", "straw",
    "amber", "colorless", "colourless", "light yellow", "red", "brown", "orange", "normal",
    "abnormal", "not detected", "non reactive", "non-reactive", "reactive", "few", "many",
    "occasional", "rare", "moderate", "scanty", "increased", "decreased",
}
SKIP_LINE_RE = re.compile(
    r"\b(?:patient name|sample id|age\s*/\s*sex|collected on|reported on|referred by|"
    r"end of report|normal range|ref\.? range|reference range|biological ref|observed value|"
    r"test name|investigation|parameter|method:|profile\s*\(|\bprofile\b|\bpanel\b)\b", re.I
)

# Correct two frequent OCR confusions without inferring or changing clinical values.
NAME_CORRECTIONS = {"1g": "TG", "rec count": "RBC Count", "row": "RDW"}


def _run(command: list[str], *, text: bool = False) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, check=True, capture_output=True, text=text)
    except FileNotFoundError as exc:
        tool = command[0]
        hint = "Install Poppler (pdftotext and pdftoppm)." if tool in {"pdftotext", "pdftoppm"} else "Install Tesseract OCR."
        raise RuntimeError(f"Required tool '{tool}' is missing. {hint}") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr if isinstance(exc.stderr, str) else (exc.stderr or b"").decode(errors="replace")
        raise RuntimeError(f"Command '{command[0]}' failed: {detail[:300]}") from None


def _ocr_image(path: Path, psm: str = "6") -> str:
    return _run(["tesseract", str(path), "stdout", "--oem", "3", "--psm", psm, "-l", "eng"], text=True).stdout


def _ocr_views(image_path: Path, scratch: Path, page_tag: str, include_crops: bool = True) -> list[tuple[str, bool]]:
    """Read the whole image in two layout modes plus half-page crops for two-column tables.

    The boolean indicates whether generic numeric-row fallback is allowed; crop-only
    views require an analyte label so isolated unit/range columns cannot become fake tests.
    """
    views: list[tuple[str, bool]] = [(_ocr_image(image_path, "6"), True), (_ocr_image(image_path, "4"), True)]
    if include_crops:
        with Image.open(image_path) as source:
            image = source.convert("RGB")
            midpoint = image.width // 2
            crops = [("left", (0, 0, midpoint, image.height)), ("right", (midpoint, 0, image.width, image.height))]
            for side, box in crops:
                crop_path = scratch / f"{page_tag}_{side}.png"
                image.crop(box).save(crop_path)
                views.append((_ocr_image(crop_path, "6"), False))
    return views


def load_document_views(path: Path) -> list[tuple[str, bool]]:
    """Use the PDF text layer when available; otherwise OCR every page at 200 DPI."""
    if not path.exists() or not path.is_file():
        raise RuntimeError(f"Input file does not exist: {path}")
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp"}:
        with tempfile.TemporaryDirectory(prefix="lab-image-") as td:
            return _ocr_views(path, Path(td), path.stem)
    if suffix != ".pdf":
        raise RuntimeError(f"Unsupported file type '{suffix}'. Use PDF, JPG, PNG, TIF or BMP.")

    digital = _run(["pdftotext", "-layout", str(path), "-"], text=True).stdout
    # Scan PDFs may have a tiny invisible text layer but no actual table text.
    if len(digital.strip()) >= 100 and len(LABEL_RE.findall(digital)) >= 3:
        return [(digital, True)]

    with tempfile.TemporaryDirectory(prefix="lab-report-") as td:
        temp_dir = Path(td)
        prefix = temp_dir / "page"
        _run(["pdftoppm", "-r", "200", "-png", str(path), str(prefix)])
        page_images = sorted(temp_dir.glob("page-*.png"), key=lambda p: int(p.stem.rsplit("-", 1)[1]))
        if not page_images:
            single = prefix.with_suffix(".png")
            if single.exists():
                page_images = [single]
        views: list[tuple[str, bool]] = []
        for page_index, image in enumerate(page_images, start=1):
            views.extend(_ocr_views(image, temp_dir, f"page{page_index}", include_crops=False))
        return views


def _split_reference(text: str) -> tuple[str, str | None]:
    source = re.sub(r"[\s|;,:]+$", "", text.strip())
    for pattern in (NUM_RANGE_RE, COMPARATOR_RE, CATEGORY_RANGE_RE):
        match = pattern.search(source)
        if match:
            reference = re.sub(r"\s+", " ", match.group(0).strip())
            reference = re.sub(r"\s*[-–—]\s*", " - ", reference)
            return source[:match.start()].strip(" |;,:"), reference
    return source, None


def _parse_value_and_unit(text: str) -> tuple[str | None, str | None]:
    value_text = text.strip().strip(" |:;,.\t\"'`_=~")
    value_text = re.sub(r"\s+(?:HH|LL|H|L|\*{1,3})\s*$", "", value_text, flags=re.I).strip()
    unit = None
    unit_match = UNIT_RE.search(value_text)
    if unit_match:
        unit = unit_match.group(1)
        value_text = value_text[:unit_match.start()].strip(" |:;,.\t\"'`_=~")
        if unit.casefold() == "%o":
            unit = "%"
    value_text = re.sub(r"\s+(?:HH|LL|H|L|\*{1,3})\s*$", "", value_text, flags=re.I).strip()
    if not value_text:
        return None, unit

    number_match = re.match(rf"^([<>≤≥]?\s*{NUM}(?:\s*[-–—]\s*{NUM})?)", value_text)
    if number_match:
        value = re.sub(r"\s*[-–—]\s*", " - ", number_match.group(1).strip())
        return value, unit

    # In noisy OCR, a result number may be preceded by speckles or a short artifact.
    numeric_tokens = list(re.finditer(rf"(?<![A-Za-z0-9])([<>≤≥]?\s*{NUM})(?![A-Za-z0-9])", value_text))
    if numeric_tokens and len(value_text) <= 40:
        token = numeric_tokens[-1].group(1).strip()
        prefix = value_text[:numeric_tokens[-1].start()].strip(" |:;,.\t\"'`_=~")
        if len(prefix) <= 12 and not re.search(r"[A-Za-z]{3,}", prefix):
            return token, unit

    # Qualitative results are valid, but arbitrary OCR prose is not a lab result.
    qualitative = re.sub(r"\s+", " ", value_text).strip(" |:;,. ").casefold()
    if qualitative in QUALITATIVE_VALUES or re.fullmatch(r"present\s*\([+-]\)", qualitative):
        return re.sub(r"\s+", " ", value_text).strip(" |:;, ."), unit
    return None, unit


def _parse_generic_numeric_row(line: str) -> dict | None:
    """Fallback for unfamiliar analytes in ordinary one-row-per-line tables."""
    before_reference, reference = _split_reference(line)
    unit = None
    unit_match = UNIT_RE.search(before_reference)
    if unit_match:
        unit = unit_match.group(1)
        if unit.casefold() == "%o":
            unit = "%"
        before_value = before_reference[:unit_match.start()].strip(" |:;,.\t\"'`_=~")
    else:
        before_value = before_reference.strip(" |:;,.\t\"'`_=~")
    # Only attempt generic row parsing if the line contains table evidence. This avoids
    # interpreting addresses, dates, prescriptions, and narrative text as lab rows.
    if not before_value or (reference is None and unit is None):
        return None
    # Use the last numeric token so analyte names like T3 and 25-Hydroxy Vitamin D survive.
    tokens = list(re.finditer(rf"(?<![A-Za-z0-9])([<>≤≥]?\s*{NUM}(?:\s*[-–—]\s*{NUM})?)(?![A-Za-z0-9])", before_value))
    if not tokens:
        return None
    result_match = tokens[-1]
    # More than one number before the result usually means OCR merged adjacent columns.
    # Permit a hyphenated analyte prefix like 25-Hydroxy, reject ambiguous merged rows.
    for prior in tokens[:-1]:
        tail = before_value[prior.end():]
        if not re.match(r"-\s*[A-Za-z]", tail):
            return None
    result = re.sub(r"\s*[-–—]\s*", " - ", result_match.group(1).strip())
    name = before_value[:result_match.start()].strip(" |:;,.\t\"'`_=~-—")
    name = re.sub(r"\s+(?:H|L|HH|LL|\*{1,3})$", "", name, flags=re.I).strip()
    if not re.search(r"[A-Za-z]{3,}", name) or len(name) > 64:
        return None
    if re.search(r"\b(?:patient name|sample id|age|collected|reported|referred|method|result|range|unit|test name|investigation|parameter|normal|reference)\b", name, re.I):
        return None
    return {"test_name": name, "value": result, "unit": unit, "reference_range": reference}


def parse_rows(text: str, allow_generic: bool = True) -> list[dict]:
    """Extract test-like rows; does not invent missing ranges or clinical status."""
    tests: list[dict] = []
    seen: set[tuple] = set()
    for raw_line in text.splitlines():
        line = re.sub(r"[\t\u00a0]+", " ", raw_line).strip()
        if not line or len(line) < 3:
            continue
        matches = list(LABEL_RE.finditer(line))
        if not matches:
            if SKIP_LINE_RE.search(line):
                continue
            generic_row = _parse_generic_numeric_row(line) if allow_generic else None
            if generic_row:
                key = tuple(str(generic_row.get(k) or "").casefold() for k in ("test_name", "value", "unit", "reference_range"))
                if key not in seen:
                    seen.add(key)
                    tests.append(generic_row)
            continue
        # Regex alternation is longest-first; discard any overlapping alias matches.
        unique = []
        for match in matches:
            if unique and match.start() < unique[-1].end():
                continue
            unique.append(match)
        for index, match in enumerate(unique):
            observed_name = match.group(1).strip()
            name = NAME_CORRECTIONS.get(observed_name.casefold(), observed_name)
            rest_end = unique[index + 1].start() if index + 1 < len(unique) else len(line)
            rest = line[match.end():rest_end].strip(" |:;\t")
            if not rest or re.search(r"\b(?:normal range|ref\.? range|observed value|test name|parameter)\b", rest, re.I):
                continue
            before_reference, reference = _split_reference(rest)
            value, unit = _parse_value_and_unit(before_reference)
            if value is None or len(value) > 32:
                continue
            # Do not accept a label embedded in a title/section header with no numeric or categorical result.
            if re.fullmatch(r"[A-Za-z /()_-]+", value) and value.casefold() in {"thyroid profile", "liver profile", "renal profile", "lipid panel", "glycaemic profile", "diabetes panel"}:
                continue
            key = (name.casefold(), value.casefold(), (unit or "").casefold(), (reference or "").casefold())
            if key in seen:
                continue
            seen.add(key)
            tests.append({"test_name": name, "value": value, "unit": unit, "reference_range": reference})
    return tests


def _merge_name_key(name: str) -> str:
    key = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
    key = re.sub(r"\s+", " ", key)
    key = NAME_CORRECTIONS.get(key, key)
    aliases = {
        "haemoglobin": "hemoglobin", "hemoglobin hb": "hemoglobin", "hemoglobin": "hemoglobin",
        "total rbc count": "rbc count", "rec count": "rbc count", "rbc count": "rbc count",
        "packed cell volume pcv": "hematocrit", "hematocrit": "hematocrit",
        "mean corpuscular volume": "mcv", "mcv": "mcv", "mean corpuscular hb": "mch", "mch": "mch",
        "mean corpuscular hb conc": "mchc", "mean corp hb conc": "mchc", "mchc": "mchc",
        "rdw cv": "rdw", "rdw": "rdw", "total wbc count": "wbc count", "total leucocyte count": "wbc count",
        "platelet count": "platelets", "platelets": "platelets", "serum triglycerides": "triglycerides", "tg": "triglycerides",
        "cholesterol total": "total cholesterol", "s cholesterol": "total cholesterol", "cholesterol hdl": "hdl", "hdl c": "hdl",
        "cholesterol ldl": "ldl", "ldl c direct": "ldl", "cholesterol vldl": "vldl",
        "tc hdl ratio": "chol hdl ratio", "chol hdl": "chol hdl ratio", "1g": "triglycerides",
        "triiodothyronine t3": "t3", "thyroxine t4": "t4", "thyroid stimulating hormone": "tsh", "tsh ultrasensitive": "tsh",
        "vit d total": "vitamin d", "25 hydroxy vitamin d": "vitamin d", "vit b12": "vitamin b12",
        "glycated hb": "hba1c", "glycosylated haemoglobin hba1c": "hba1c", "glycosylated hemoglobin hba1c": "hba1c",
        "fbs": "fasting glucose", "glucose fasting": "fasting glucose", "ppbs": "postprandial glucose", "glucose pp": "postprandial glucose",
        "sodium na": "sodium", "sodium": "sodium", "s sodium": "sodium", "potassium k": "potassium", "potassium": "potassium", "s potassium": "potassium",
        "chloride cl": "chloride", "chloride": "chloride", "s chloride": "chloride", "serum uric acid": "uric acid", "uric acid": "uric acid",
        "colour": "urine colour", "color": "urine colour", "clarity": "urine clarity", "appearance": "urine clarity",
        "reaction ph": "urine ph", "ph": "urine ph", "specific gravity": "specific gravity", "sp gravity": "specific gravity",
        "ketone bodies": "ketones", "ketones": "ketones", "leucocytes": "pus cells", "pus cells wbc": "pus cells",
        "erythrocytes": "urine rbc", "rbc": "urine rbc", "esr westergren": "esr",
    }
    return aliases.get(key, key)


def _normal_field(field: str, value):
    if value is None:
        return ""
    text = str(value).strip().casefold()
    if field == "value":
        text = text.replace(",", "")
        text = re.sub(r"\s*[-–—]\s*", "-", text)
    elif field == "unit":
        text = re.sub(r"\s+", "", text).replace("μ", "µ")
    elif field == "reference_range":
        text = re.sub(r"\s*[-–—]\s*", "-", text)
        text = re.sub(r"\s+", "", text)
    return text


def _merge_views(parsed_views: list[list[dict]]) -> list[dict]:
    """Merge duplicate OCR views by field consensus, keeping the first view as tie-breaker."""
    groups: dict[str, list[tuple[int, int, dict, int]]] = {}
    sequence = 0
    view_sizes = [max(1, len(rows)) for rows in parsed_views]
    for view_idx, rows in enumerate(parsed_views):
        for row_idx, row in enumerate(rows):
            key = _merge_name_key(row["test_name"])
            # Preserve distinct analytes; do not merge an empty/uncertain OCR label.
            if not key:
                continue
            groups.setdefault(key, []).append((view_idx, row_idx, row, view_sizes[view_idx]))
            sequence += 1
    merged_with_rank = []
    for key, candidates in groups.items():
        # Keep the most common readable name, preferring the full-page/first view on ties.
        name_counts = {}
        for view_idx, row_idx, row, size in candidates:
            name_counts.setdefault(row["test_name"], []).append(view_idx)
        name = min(name_counts, key=lambda n: (-len(name_counts[n]), min(name_counts[n]), len(n)))
        merged = {"test_name": name}
        for field in ("value", "unit", "reference_range"):
            options = [(v, i, r.get(field)) for v, i, r, _ in candidates if r.get(field) not in (None, "")]
            if not options:
                merged[field] = None
                continue
            counts = {}
            for view_idx, row_idx, value in options:
                normal = _normal_field(field, value)
                counts.setdefault(normal, []).append((view_idx, row_idx, value))
            chosen_norm = min(counts, key=lambda val: (-len(counts[val]), min(x[0] for x in counts[val]), len(val)))
            chosen = min(counts[chosen_norm], key=lambda x: (x[0], x[1]))
            merged[field] = chosen[2]
        # Average normalized position gives rows found only in secondary views a reasonable place.
        rank = sum(row_idx / max(1, size) for _, row_idx, _, size in candidates) / len(candidates)
        first_view = min(x[0] for x in candidates)
        merged_with_rank.append((rank, first_view, merged))
    merged_with_rank.sort(key=lambda item: (item[0], item[1]))
    return [item[2] for item in merged_with_rank]


def extract(path: Path) -> dict:
    views = load_document_views(path)
    parsed_views = [parse_rows(text, allow_generic=allow_generic) for text, allow_generic in views]
    # A single digital text layer is authoritative; OCR variants are merged conservatively.
    tests = parsed_views[0] if len(parsed_views) == 1 else _merge_views(parsed_views)
    return {"tests": tests}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    try:
        print(json.dumps(extract(Path(sys.argv[1])), indent=2, ensure_ascii=False))
    except RuntimeError as error:
        sys.exit(str(error))
