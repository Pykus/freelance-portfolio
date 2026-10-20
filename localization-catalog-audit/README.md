# Translation Catalog QA — Catch Broken Localization Before a Release

## A real business problem

A software company is about to ship its app in Spanish. Its English text catalog defines button labels and messages such as "Welcome, {user}!". Translations arrive from a language vendor in a CSV. A missing translation leaves a blank screen, while accidentally replacing the variable **{user}** with **{client}** can crash formatting at runtime.

Reviewing hundreds of localization keys in Excel is slow and error-prone. This Python command-line tool **compares the original and translated CSV catalogs** and produces a human-reviewable report. It works offline, uses no credentials, and requires only Python's standard library.

## The included worked example

The fictional source catalog contains 6 English app messages. The Spanish CSV has 6 rows too, but one key is missing and a different unexpected key was added.

| Key | English | Spanish | Result |
| --- | --- | --- | --- |
| welcome | Welcome, {user}! | ¡Bienvenido, {user}! | OK |
| cart | You have {count} items | Tienes {count} artículos | OK |
| reset | Reset your password | (empty) | Empty translation |
| checkout | Finish your order of {count} items | Finaliza tu pedido de {total} artículos | Placeholder mismatch |
| faq | Frequently asked questions | (missing key) | Missing key |
| status | Current status: {state} | Estado: {state | Invalid brace syntax |
| extra | (not in English catalog) | Más información | Unexpected key |

**Result: 5 issues requiring review.** The original strings remain unchanged.

## Run it

Use Python 3.10+; from this directory:

~~~sh
python3 catalog_audit.py \
  --source examples/english.csv \
  --target examples/spanish.csv \
  --locale es \
  --output output

cat output/summary.json
cat output/issues.csv
~~~

Read [the expected issues CSV](examples/expected-issues.csv) directly on GitHub without running anything.

The summary for the included fictional example:

~~~json
{
  "issue_count": 5,
  "issues_by_code": {
    "empty_translation": 1,
    "invalid_format": 1,
    "missing_key": 1,
    "placeholder_mismatch": 1,
    "unexpected_key": 1
  },
  "locale": "es",
  "source_keys": 6,
  "target_keys": 6
}
~~~

The script returns an input error for malformed CSV files, duplicated/invalid keys or malformed base-language templates. A malformed *translation* is instead recorded as a review issue, so the QA process can continue. The output has deterministic ordering and protects spreadsheet users from formula-like exported text.

## How this prevents a production incident

Consider a checkout message with a source placeholder **{count}**. The translated file accidentally contains **{total}**. A runtime formatter that receives only the named variable "count" may fail to render that message. The audit catches the incompatible string **before the build is released**. Similarly, it lists screens missing a translation.

It recognizes named Python-style placeholders (including repeated variables) and escaped braces. It deliberately rejects attribute lookups, index expressions, conversions and format specifications; this makes supported syntax explicit rather than silently misreading a template. If an application uses ICU MessageFormat or another localization format, it needs a different parser.

## Tests

~~~sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q catalog_audit.py tests
~~~

Tests cover a complete CLI run, 5 issue categories, placeholder multiplicity, escaped braces, invalid syntax, duplicate/invalid keys, UTF-8 BOM input, formula-safe CSV exports and deterministic results.

**Scope:** This is a QA helper, not a translation service or a language-quality model. It does not decide whether Spanish wording is fluent or contextually correct. All sample companies and strings are fictional; this is an independent reproducible portfolio project, not client work.
