# Prompt record

## Supplied Gemini prompt (verbatim)

```text
You are an expert at reading medical lab reports.

Look at this lab report and extract every test result from it.

Return JSON in exactly this format:
{"tests": [{"test_name": "...", "value": 0.0, "unit": "...", "reference_range": "...", "status": "normal"}]}

Rules:
- Use the standard medical name for each test.
- value must be a number.
- If a reference range is missing from the report, fill in the standard reference range for that test.
- status is "normal", "high" or "low", based on the value and the reference range.
- Be thorough. Do not miss any tests.
```

## Why it is shaped this way / whether it was run

This is copied from the supplied `extract.py`; it was not run in this environment because `GEMINI_API_KEY` was not configured. I did not create a replacement model prompt: the implemented extractor is deterministic local PDF-text/OCR/parsing code and makes no model call.

The supplied prompt has three risky constraints for this dataset: it requires numeric values (urinalysis contains qualitative results and results such as `<0.5`), instructs the model to fill missing reference ranges (invented clinical context), and asks for a `status` field absent from the required schema. The starter then converts every `value` to float, which can silently discard the very strings the prompt/schema should preserve. The local implementation keeps report-provided values and ranges, represents an absent range as `null`, and does not infer normal/high/low status.
