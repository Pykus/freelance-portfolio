"""Report deterministic changes between two JSON configuration documents."""
import json
import sys
from pathlib import Path

def flatten(value, prefix=""):
    if isinstance(value, dict):
        result = {}
        for key in sorted(value):
            if not isinstance(key, str):
                raise ValueError("object keys must be strings")
            path = prefix + "/" + key.replace("~", "~0").replace("/", "~1")
            result.update(flatten(value[key], path))
        if not value:
            result[prefix or "/"] = {}
        return result
    if isinstance(value, list):
        result = {}
        for i, item in enumerate(value):
            result.update(flatten(item, prefix + "/" + str(i)))
        if not value:
            result[prefix or "/"] = []
        return result
    return {prefix or "/": value}

def compare(before, after):
    left, right = flatten(before), flatten(after)
    return {
        "added": {k: right[k] for k in sorted(right.keys() - left.keys())},
        "removed": {k: left[k] for k in sorted(left.keys() - right.keys())},
        "changed": {k: {"before": left[k], "after": right[k]}
                    for k in sorted(left.keys() & right.keys()) if type(left[k]) != type(right[k]) or left[k] != right[k]}
    }

if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python diff.py before.json after.json")
    left = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    right = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    print(json.dumps(compare(left, right), indent=2, sort_keys=True))
