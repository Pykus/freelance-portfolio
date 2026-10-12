import csv
import json
import sys
from decimal import Decimal

def read(path):
    data = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            key = row["id"].strip()
            if not key or key in data:
                raise ValueError("missing or duplicate ID")
            value = Decimal(row["amount"])
            if not value.is_finite() or value.as_tuple().exponent < -2:
                raise ValueError("invalid amount")
            data[key] = value
    return data

def compare(a, b):
    old, new = read(a), read(b)
    return {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(k for k in old.keys() & new.keys() if old[k] != new[k]),
        "unchanged": sum(old[k] == new[k] for k in old.keys() & new.keys()),
    }

if __name__ == "__main__":
    print(json.dumps(compare(sys.argv[1], sys.argv[2]), indent=2))
