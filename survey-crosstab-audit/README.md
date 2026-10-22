# Survey Cross-Tab and Data Quality Auditor

Turn fictional customer survey exports into auditable segment-by-answer frequency tables. The tool validates a JSON codebook, detects duplicate response identifiers, preserves missing-answer and invalid-answer counts, and computes **within-segment valid-response percentages**, not misleading percentages that include skipped questions.

## Why it is useful

Spreadsheet survey exports often mix empty cells, unexpected categories and repeated respondent IDs. A cross-tab can look reasonable even when its denominator is wrong. This project makes the accounting explicit: `respondents = valid + missing + invalid` for every `(segment, question)` pair. It never silently turns a missing answer into a negative answer.

## Reproduce the demonstration

Python 3.10 or later; **standard library only**.

```bash
python3 survey_audit.py \
  --responses examples/responses.csv \
  --codebook examples/codebook.json \
  --output output
python3 -m unittest discover -s tests -v
```

Outputs:

- `output/audit.json`: row counts, excluded rows, line-specific quality issues, per-question completion rates.
- `output/cross_tabs.csv`: every configured answer for each configured segment, including categories with zero observations.

The example has **nine** CSV data rows, **seven** included unique respondents, a duplicate response and a row with an unknown region. It also deliberately includes a missing answer and an unsupported answer. Check the generated JSON to see the three reported issues; missing answers are tracked as counts, not errors.

## Codebook contract

`id_column` identifies respondents. `segment_column` assigns a row to one allowed segment. `segments` is an ordered list, and `questions` maps CSV question columns to ordered `choices` and optional `missing` markers. Strings are trimmed when reading CSV; codebook choices must already be trimmed. The default missing markers are `""` and `"NA"` if `missing` is omitted. Empty strings are allowed in a missing-marker list, but never among valid choices.

First appearance of a nonempty response ID wins; repeated IDs are excluded, even when the later row has different answers. A row with an empty ID, malformed CSV fields or a region outside the codebook is excluded in full. Invalid answers affect only that question's valid-response denominator: the row can still contribute to other questions. These explicit policies are suitable for review, not universal survey-analysis rules.

`valid_pct` uses valid answers as its denominator; `completion_pct` uses included unique respondents for that segment. When there are no valid answers (or no respondents), the software emits `0.0` rather than dividing by zero. Never interpret that 0% as evidence of a zero population proportion; it denotes the chosen export convention for an empty denominator.

## Limitations

- Unweighted counts only, no inferential claims, confidence intervals, or survey design adjustments.
- Single-segment grouping, no multiple-response questions or longitudinal respondent matching.
- Exact code matching after surrounding-space trimming, no fuzzy category mapping.
- Inputs should be reviewed for sensitive respondent information before any publication; sample inputs are synthetic.
- Reports are written as ordinary files, not as an atomic transaction; use a fresh output directory for production runs.

All code, tests and example data are included for independent reproduction.
