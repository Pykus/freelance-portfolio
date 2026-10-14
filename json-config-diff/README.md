# JSON Configuration Change Report

Compare two JSON files and generate a machine-readable report of added, removed and changed values. Useful for reviewing configuration exports, API responses and structured snapshots.

## Example

`before.json`:
```json
{"service":{"port":8000,"enabled":true}}
```

`after.json`:
```json
{"service":{"port":8080,"enabled":true},"region":"eu"}
```

Run:
```sh
python diff.py before.json after.json
python -m unittest discover -s . -p test_diff.py -v
```

The report shows `/service/port` as changed and `/region` as added. Paths use JSON Pointer-style escaping. List positions are compared by index; reordering a list may produce several changes. Empty containers are represented explicitly. Only Python standard-library modules are required.
