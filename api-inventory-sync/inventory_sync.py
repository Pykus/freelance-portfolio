"""Idempotent inventory reconciliation over an HTTP JSON API.

This is an example client of a deliberately small API contract, not an SDK for
the business or systems mentioned in the source job posting.
"""
import json
import re
from urllib import error, request


class SyncError(Exception):
    """Invalid data, HTTP failures, or mismatched API responses."""


def validate_document(data):
    """Return a sorted, validated list of inventory items."""
    if not isinstance(data, dict) or set(data) != {"items"} or not isinstance(data["items"], list):
        raise SyncError("expected a JSON object with exactly one 'items' array")
    seen = set()
    output = []
    for position, item in enumerate(data["items"], start=1):
        if not isinstance(item, dict) or set(item) != {"sku", "price_cents", "quantity"}:
            raise SyncError(f"item {position}: expected sku, price_cents, quantity")
        sku = item["sku"]
        if not isinstance(sku, str) or not re.fullmatch(r"[A-Z0-9-]{3,24}", sku):
            raise SyncError(f"item {position}: invalid sku")
        price = item["price_cents"]
        quantity = item["quantity"]
        if isinstance(price, bool) or not isinstance(price, int) or not 1 <= price <= 10_000_000:
            raise SyncError(f"item {position}: price_cents must be a positive integer (max 10000000)")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 1_000_000:
            raise SyncError(f"item {position}: quantity must be an integer from 0 to 1000000")
        if sku in seen:
            raise SyncError(f"item {position}: duplicate sku {sku}")
        seen.add(sku)
        output.append({"sku": sku, "price_cents": price, "quantity": quantity})
    return sorted(output, key=lambda item: item["sku"])


class InventoryClient:
    """HTTP client for GET /items, POST /items, PUT/DELETE /items/{sku}."""
    def __init__(self, base_url, token, timeout=3):
        if not isinstance(base_url, str) or not base_url.startswith("http"):
            raise SyncError("base_url must be an HTTP(S) URL")
        if not isinstance(token, str) or not token:
            raise SyncError("a token is required")
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self.method_counts = {"GET": 0, "POST": 0, "PUT": 0, "DELETE": 0}

    def send(self, method, path, payload=None):
        if method not in self.method_counts:
            raise SyncError("unsupported method")
        headers = {"Authorization": f"Bearer {self.token}", "Accept": "application/json"}
        body = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body = json.dumps(payload).encode("utf-8")
        req = request.Request(self.base_url + path, data=body, headers=headers, method=method)
        self.method_counts[method] += 1
        try:
            with request.urlopen(req, timeout=self.timeout) as response:
                data = response.read()
                if not data:
                    return None
                return json.loads(data.decode("utf-8"))
        except error.HTTPError as exc:
            status = exc.code
            exc.close()
            raise SyncError(f"{method} {path}: HTTP {status}") from exc
        except (error.URLError, TimeoutError, UnicodeError, json.JSONDecodeError) as exc:
            raise SyncError(f"{method} {path}: HTTP/JSON response failed: {type(exc).__name__}") from exc


def synchronize(client, desired_items):
    """Plan and execute changes, then verify the final state by a second GET."""
    desired = validate_document({"items": desired_items})
    incoming = client.send("GET", "/items")
    existing = validate_document(incoming)
    before = {item["sku"]: item for item in existing}
    target = {item["sku"]: item for item in desired}
    created = sorted(target.keys() - before.keys())
    deleted = sorted(before.keys() - target.keys())
    updated = sorted(sku for sku in target.keys() & before.keys() if target[sku] != before[sku])
    unchanged = sorted(sku for sku in target.keys() & before.keys() if target[sku] == before[sku])

    for sku in created:
        client.send("POST", "/items", target[sku])
    for sku in updated:
        client.send("PUT", "/items/" + sku, target[sku])
    for sku in deleted:
        client.send("DELETE", "/items/" + sku)

    actual = validate_document(client.send("GET", "/items"))
    if actual != desired:
        raise SyncError("remote state does not match the desired state after synchronization")
    counts = dict(client.method_counts)
    return {
        "source_items": len(desired),
        "initial_items": len(existing),
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "unchanged": unchanged,
        "final_items": actual,
        "http_calls": sum(counts.values()),
        "http_methods": counts,
    }
