"""Shared, provider-independent parsing helpers for the local evaluation."""
from __future__ import annotations
import re

# Common analytes and report labels, not report-specific row offsets or values.
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
    "Pus Cells (WBC)", "Epithelial Cells", "Mean Corpuscular Hb", "Haemoglobin",
    "Hemoglobin", "Platelet Count", "Platelets", "Hematocrit", "MCV", "MCHC", "MCH",
    "RDW-CV", "RDW", "Neutrophils", "Lymphocytes", "Eosinophils", "Monocytes",
    "Basophils", "Investigation", "Cholesterol - Total", "S. Cholesterol", "Total Cholesterol",
    "Serum Triglycerides", "Triglycerides", "HDL-C", "HDL", "LDL-C", "LDL", "VLDL",
    "Chol/HDL", "Total Bilirubin", "AST", "SGOT", "ALT", "SGPT", "ALP", "Protein Total",
    "T3", "T4", "TSH (Ultrasensitive)", "TSH", "Vit D Total", "Vitamin D", "Vit B12",
    "Glycated Hb", "HbA1c", "FBS", "PPBS", "Urea", "Creatinine", "Sodium (Na+)",
    "Sodium", "Potassium (K+)", "Potassium", "Chloride (Cl-)", "Chloride", "Colour", "Color",
    "Clarity", "Appearance", "Reaction (pH)", "pH", "Albumin", "Sugar", "Ketones",
    "Leucocytes", "Erythrocytes", "CRP", "RBC", "Pale Yellow", "Pale yellow",
]
LABELS = sorted(set(LABELS), key=len, reverse=True)
_LABEL_RE = re.compile(r"(?<![A-Za-z0-9])(" + "|".join(re.escape(x) for x in LABELS) + r")(?![A-Za-z0-9])", re.I)

_NUM = r"\d[\d,]*(?:\.\d+)?"
_NUM_RANGE = re.compile(rf"(?:[<>≤≥]\s*)?{_NUM}\s*(?:-|–|—|\bto\b)\s*(?:[<>≤≥]\s*)?{_NUM}\s*$", re.I)
_COMPARATOR = re.compile(rf"[<>≤≥]\s*{_NUM}\s*$")
_CATEGORY_RANGE = re.compile(r"(?:Pale\s+Yellow|Negative|Clear|Nil|Absent|Normal|None)\s*$", re.I)
_UNIT_SUFFIXES = [
    "million/cumm", "mill/cumm", "lakh/cumm", "µIU/mL", "uIU/mL", "mIU/mL", "µg/dL", "ug/dL",
    "ng/mL", "ng/dL", "pg/mL", "mg/dL", "g/dL", "mmol/L", "mmol/l", "U/L", "IU/L",
    "mm/hr", "mm/h", "/cumm", "/hpf", "cells/cumm", "fl", "fL", "pg", "%",
]
_UNIT_RE = re.compile(r"\s*(" + "|".join(re.escape(x) for x in sorted(_UNIT_SUFFIXES, key=len, reverse=True)) + r")\s*$", re.I)


def split_reference(text: str) -> tuple[str, str | None]:
    """Split a report-provided reference interval from the right-hand edge."""
    s = text.strip().strip("|;,:")
    for rx in (_NUM_RANGE, _COMPARATOR, _CATEGORY_RANGE):
        m = rx.search(s)
        if m:
            ref = re.sub(r"\s+", " ", m.group(0).strip())
            ref = re.sub(r"\s*[-–—]\s*", " - ", ref)
            return s[:m.start()].strip(" |;,:"), ref
    return s, None


def parse_value_unit(text: str) -> tuple[str | None, str | None]:
    """Parse a result and recognized trailing unit while preserving text values."""
    s = re.sub(r"^[\s|:;.,]+|[\s|:;.,]+$", "", text)
    # Common analyzer flags (H/L/asterisk) are metadata, not part of the result.
    s = re.sub(r"\s+(?:H|L|HH|LL|\*{1,3})\s*$", "", s, flags=re.I)
    unit = None
    um = _UNIT_RE.search(s)
    if um:
        unit = um.group(1)
        s = s[:um.start()].strip()
    s = re.sub(r"\s+(?:H|L|HH|LL|\*{1,3})\s*$", "", s, flags=re.I).strip()
    if not s:
        return None, unit
    # Keep numeric comparators and observed ranges as strings: they are not a scalar.
    m = re.match(rf"^([<>≤≥]?\s*{_NUM}(?:\s*[-–—]\s*{_NUM})?)", s)
    if m:
        value = re.sub(r"\s*[-–—]\s*", " - ", m.group(1).strip())
        return value, unit
    # Avoid emitting table headers or arbitrary prose as a result.
    if len(s) <= 32 and not re.search(r"\b(?:result|range|value|unit|investigation|parameter|test name)\b", s, re.I):
        return re.sub(r"\s+", " ", s).strip(" |:;,."), unit
    return None, unit


def parse_rows(text: str) -> list[dict]:
    """Extract table-like lines by recognized analyte labels and trailing columns."""
    tests = []
    seen = set()
    for raw_line in text.splitlines():
        line = re.sub(r"[\t\u00a0]+", " ", raw_line).strip()
        if not line or len(line) < 3:
            continue
        matches = list(_LABEL_RE.finditer(line))
        # Discard obvious table/header matches; longest-first regex avoids partial labels.
        matches = [m for m in matches if m.group(1).casefold() not in {
            "investigation", "pale yellow"
        }]
        if not matches:
            continue
        # Remove duplicate overlapping matches and anything in boilerplate after report end.
        unique = []
        for m in matches:
            if unique and m.start() < unique[-1].end():
                continue
            unique.append(m)
        for i, m in enumerate(unique):
            name = m.group(1).strip()
            start = m.end()
            end = unique[i + 1].start() if i + 1 < len(unique) else len(line)
            rest = line[start:end].strip(" |:;\t")
            # Some labels may occur in a section heading, without any result columns.
            if not rest or re.search(r"\b(?:normal range|ref\.? range|observed value|test name|parameter)\b", rest, re.I):
                continue
            before_ref, ref = split_reference(rest)
            value, unit = parse_value_unit(before_ref)
            if value is None:
                continue
            # Avoid section headings/date/metadata accidentally parsed under an analyte word.
            if len(value) > 32:
                continue
            key = (name.casefold(), value.casefold(), (unit or "").casefold(), (ref or "").casefold())
            if key in seen:
                continue
            seen.add(key)
            tests.append({"test_name": name, "value": value, "unit": unit, "reference_range": ref})
    return tests
