"""Local-only mock inventory API for demos."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from inventory_sync import SyncError, validate_document

class InventoryServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, initial):
        super().__init__(("127.0.0.1", 0), InventoryHandler)
        self.items = {item['sku']: item for item in validate_document(initial)}
        self.events = []

    @property
    def base_url(self):
        return f"http://127.0.0.1:{self.server_address[1]}"


class InventoryHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def respond(self, status, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        self.server.events.append({"method": self.command, "path": self.path, "status": status})
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        if body:
            self.send_header("Content-Type", "application/json")
        self.end_headers()
        if body:
            self.wfile.write(body)

    def read_payload(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 1 <= length <= 4096:
            raise ValueError("invalid body length")
        data = json.loads(self.rfile.read(length).decode("utf-8"))
        return validate_document({"items": [data]})[0]

    def do_GET(self):
        if self.path != "/items":
            return self.respond(404, {"error": "not found"})
        self.respond(200, {"items": sorted(self.server.items.values(), key=lambda item: item["sku"])})

    def do_POST(self):
        if self.path != "/items":
            return self.respond(404, {"error": "not found"})
        try:
            item = self.read_payload()
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, SyncError):
            return self.respond(400, {"error": "invalid item"})
        if item["sku"] in self.server.items:
            return self.respond(409, {"error": "duplicate sku"})
        self.server.items[item["sku"]] = item
        self.respond(201, item)

    def do_PUT(self):
        if not self.path.startswith("/items/"):
            return self.respond(404, {"error": "not found"})
        sku = self.path[len("/items/"):]
        if sku not in self.server.items:
            return self.respond(404, {"error": "unknown sku"})
        try:
            item = self.read_payload()
        except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, SyncError):
            return self.respond(400, {"error": "invalid item"})
        if sku != item["sku"]:
            return self.respond(400, {"error": "sku mismatch"})
        self.server.items[sku] = item
        self.respond(200, item)

    def do_DELETE(self):
        if not self.path.startswith("/items/"):
            return self.respond(404, {"error": "not found"})
        sku = self.path[len("/items/"):]
        if sku not in self.server.items:
            return self.respond(404, {"error": "unknown sku"})
        del self.server.items[sku]
        self.respond(204)
