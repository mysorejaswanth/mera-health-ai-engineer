# Evaluation results

> Reproduce with `python eval/evaluate.py`. The local OCR baseline is not the supplied Gemini result; no API was called.

| Metric | Local baseline | Final |
|---|---:|---:|
| Exact-row precision | 67.4% | 83.0% |
| Exact-row recall | 46.4% | 81.2% |
| Exact-row F1 | 54.9% | 82.1% |
| Predicted rows / gold rows | 95 / 138 | 135 / 138 |
| Mean latency per labelled report | 1.984s | 2.028s |
| API cost per report | $0.00 | $0.00 |

## Per-report exact-row results

| Report | Gold rows | Baseline exact | Final exact | Baseline rows | Final rows |
|---|---:|---:|---:|---:|---:|
| report_01 | 14 | 0 | 13 | 0 | 14 |
| report_02 | 16 | 14 | 16 | 16 | 16 |
| report_03 | 8 | 6 | 8 | 9 | 8 |
| report_05 | 14 | 1 | 3 | 13 | 11 |
| report_06 | 12 | 6 | 6 | 12 | 12 |
| report_08 | 6 | 4 | 5 | 5 | 6 |
| report_09 | 14 | 6 | 7 | 10 | 14 |
| report_11 | 54 | 27 | 54 | 30 | 54 |

## Field accuracy (denominator = all gold rows; missing rows count as incorrect)

| Field | Local baseline | Final |
|---|---:|---:|
| test_name | 68.1% | 97.8% |
| value | 52.9% | 89.1% |
| unit | 52.2% | 84.1% |
| reference_range | 58.0% | 88.4% |

## Label audit

`report_01` gold labels Platelet Count as 304000, but the PDF's readable text says 340000. The supplied label is not edited; this row is marked incorrect in the primary score.
