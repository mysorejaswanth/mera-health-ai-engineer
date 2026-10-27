"""No-key comparison baseline: first page rasterized at 200 DPI, then Tesseract.

This is a reproducible local comparison baseline, NOT a claim about Gemini's output.
The supplied Gemini baseline cannot be executed without a user-provided API key. The 200-DPI render is a practical local quality/speed trade-off; results are not comparable to the supplied Gemini API baseline.
"""
from __future__ import annotations
import subprocess
import tempfile
from pathlib import Path
from common import parse_rows

DPI = 200


def get_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / "page"
            subprocess.run([
                "pdftoppm", "-f", "1", "-l", "1", "-singlefile", "-r", str(DPI),
                "-png", str(path), str(prefix)
            ], check=True, capture_output=True)
            image = prefix.with_suffix(".png")
            return subprocess.run(["tesseract", str(image), "stdout", "--psm", "6"],
                                  check=True, capture_output=True, text=True).stdout
    return subprocess.run(["tesseract", str(path), "stdout", "--psm", "6"],
                          check=True, capture_output=True, text=True).stdout


def extract(path: Path) -> dict:
    return {"tests": parse_rows(get_text(path))}

if __name__ == "__main__":
    import json, sys
    print(json.dumps(extract(Path(sys.argv[1])), indent=2, ensure_ascii=False))
