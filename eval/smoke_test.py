"""Check the public extract.py contract against all supplied reports.

Run from the repository root: python eval/smoke_test.py
"""
from __future__ import annotations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from extract import extract  # noqa: E402

REQUIRED = {"test_name", "value", "unit", "reference_range"}
VALID_VALUE = (str, int, float, type(None))
VALID_TEXT = (str, type(None))


def main() -> None:
    schema = json.loads((ROOT / "schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["tests"]["type"] == "array"
    files = sorted((ROOT / "reports").glob("*"))
    if not files:
        raise SystemExit("No supplied reports found")
    total_rows = 0
    for path in files:
        output = extract(path)
        assert isinstance(output, dict) and isinstance(output.get("tests"), list), path.name
        for i, row in enumerate(output["tests"]):
            assert REQUIRED <= row.keys(), f"{path.name}[{i}] missing required fields"
            assert isinstance(row["test_name"], str) and row["test_name"].strip(), f"{path.name}[{i}] invalid name"
            assert isinstance(row["value"], VALID_VALUE), f"{path.name}[{i}] invalid value type"
            assert isinstance(row["unit"], VALID_TEXT), f"{path.name}[{i}] invalid unit type"
            assert isinstance(row["reference_range"], VALID_TEXT), f"{path.name}[{i}] invalid range type"
        total_rows += len(output["tests"])
        print(f"PASS {path.name}: {len(output['tests'])} rows")
    # Regression checks for the known multi-page coverage and a non-result note.
    multi_page = extract(ROOT / "reports" / "report_11.pdf")["tests"]
    assert any("T4" in row["test_name"] for row in multi_page), "multi-page T4 row was not recovered"
    advised_tests = extract(ROOT / "reports" / "report_12.jpg")["tests"]
    assert len(advised_tests) == 0, "a test-advice note should not be converted into completed results"
    print(f"PASS schema/entry-point contract: {len(files)} reports, {total_rows} rows emitted in this run")

if __name__ == "__main__":
    main()
