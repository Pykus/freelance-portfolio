# CSV Schema Validator

Validate exported business CSV files against a small JSON schema before import.

## Example

`schema.json`:
```json
{"fields":{"id":"integer","price":"decimal","description":"text"}}
```

`data.csv`:
```csv
id,price,description
1,10.50,Widget
2,12.00,Gadget
```

## Run
```sh
python validate.py data.csv schema.json
python -m unittest discover -s . -p test_validate.py -v
```

The command emits JSON with row count, validation errors and a validity flag. Exit code 0 indicates valid data; 1 indicates invalid data. Supported field types are text, integer and decimal. Fields are required and nonempty. Decimal validation rejects nonfinite values. The tool checks structure and types, not domain-specific business rules.
