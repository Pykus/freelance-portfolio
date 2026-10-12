# Inventory REST API Synchronizer (Offline Demo)

A compact, reproducible Python integration project that **compares a desired product inventory against a remote inventory over real HTTP**, then uses **GET, POST, PUT and DELETE** to make both match. The remote service in this demo is a local-only, disposable HTTP server with completely synthetic data. It does not contact or modify any live retailer or third-party API.

## Business problem and capabilities

A business manages product prices and stock quantities in a master JSON export. A remote API is out of date: one item needs a quantity change, one is missing, and one is obsolete. A predictable synchronization tool should make only necessary updates and show exactly what changed.

- Read and validate two complete JSON input datasets; reject malformed schemas, invalid SKUs, duplicate SKUs, non-integer money, non-positive prices and invalid stock quantities.
- GET existing inventory as actual HTTP JSON, compare by SKU, POST missing products, PUT changed products, DELETE obsolete products and leave unchanged products alone.
- Include a `Bearer` authorization header in every HTTP client request; report non-success HTTP codes without exposing token contents. See the mock-server limitation below.
- Use **integer cents** rather than floats to represent prices, and sort records for deterministic results.
- GET the final remote inventory and **verify it exactly matches the desired inventory**.
- Write three tangible JSON files: an operation report, final server state and an ordered HTTP request log.
- Repeat synchronization against the same server without unnecessary writes (idempotence). Python standard library only (Python 3.9+).

## Complete input #1: initial remote inventory

Entire committed file [`examples/initial.json`](examples/initial.json):

```json
{
  "items": [
    {
      "sku": "SKU-100",
      "price_cents": 1250,
      "quantity": 5
    },
    {
      "sku": "SKU-200",
      "price_cents": 600,
      "quantity": 3
    },
    {
      "sku": "SKU-OLD",
      "price_cents": 9900,
      "quantity": 1
    }
  ]
}
```

## Complete input #2: desired inventory

Entire committed file [`examples/desired.json`](examples/desired.json):

```json
{
  "items": [
    {
      "sku": "SKU-100",
      "price_cents": 1250,
      "quantity": 5
    },
    {
      "sku": "SKU-200",
      "price_cents": 600,
      "quantity": 8
    },
    {
      "sku": "SKU-300",
      "price_cents": 450,
      "quantity": 2
    }
  ]
}
```

All records are fictional. The unit `price_cents: 1250` means **$12.50**, not $1,250.

## Exact command (run from this project directory)

```bash
python demo.py --desired examples/desired.json --initial examples/initial.json --out-dir output
```

`demo.py` starts a temporary HTTP server bound to **127.0.0.1** on an available local port, performs real HTTP requests with `inventory_sync.py`, shuts down the server, and saves the evidence. No internet connection, external accounts, API keys or third-party packages are required.

**Terminal summary from the example run:**

```text
{
  "source_items": 3,
  "created": [
    "SKU-300"
  ],
  "updated": [
    "SKU-200"
  ],
  "deleted": [
    "SKU-OLD"
  ],
  "unchanged": [
    "SKU-100"
  ],
  "http_calls": 5
}
Output files: output/report.json, output/final-state.json, output/http-log.json
```

This terminal text is a convenience summary: the actual data and detailed report are saved in the three files below.

## Row-level transformations and HTTP operations

| SKU | Initial state | Desired state | Action | Effect |
| --- | --- | --- | --- | --- |
| SKU-100 | $12.50, 5 units | $12.50, 5 units | none | unchanged |
| SKU-200 | $6.00, 3 units | $6.00, 8 units | PUT /items/SKU-200 | stock quantity changes 3 to 8 |
| SKU-300 | absent | $4.50, 2 units | POST /items | created |
| SKU-OLD | $99.00, 1 unit | absent | DELETE /items/SKU-OLD | removed |

The sync makes **2 GET + 1 POST + 1 PUT + 1 DELETE = 5 HTTP calls**: first GET to discover the state, one operation per changed record, and a second GET to verify the final state.

## Actual output file #1: output/report.json

Complete actual contents (committed reference: [examples/expected-report.json](examples/expected-report.json)):

```json
{
  "source_items": 3,
  "initial_items": 3,
  "created": [
    "SKU-300"
  ],
  "updated": [
    "SKU-200"
  ],
  "deleted": [
    "SKU-OLD"
  ],
  "unchanged": [
    "SKU-100"
  ],
  "final_items": [
    {
      "sku": "SKU-100",
      "price_cents": 1250,
      "quantity": 5
    },
    {
      "sku": "SKU-200",
      "price_cents": 600,
      "quantity": 8
    },
    {
      "sku": "SKU-300",
      "price_cents": 450,
      "quantity": 2
    }
  ],
  "http_calls": 5,
  "http_methods": {
    "GET": 2,
    "POST": 1,
    "PUT": 1,
    "DELETE": 1
  }
}
```

## Actual output file #2: output/final-state.json

Full final dataset (reference [examples/expected-final-state.json](examples/expected-final-state.json)):

```json
{
  "items": [
    {
      "sku": "SKU-100",
      "price_cents": 1250,
      "quantity": 5
    },
    {
      "sku": "SKU-200",
      "price_cents": 600,
      "quantity": 8
    },
    {
      "sku": "SKU-300",
      "price_cents": 450,
      "quantity": 2
    }
  ]
}
```

## Actual output file #3: output/http-log.json

Complete HTTP operation log including status codes (reference [examples/expected-http-log.json](examples/expected-http-log.json)):

```json
[
  {
    "method": "GET",
    "path": "/items",
    "status": 200
  },
  {
    "method": "POST",
    "path": "/items",
    "status": 201
  },
  {
    "method": "PUT",
    "path": "/items/SKU-200",
    "status": 200
  },
  {
    "method": "DELETE",
    "path": "/items/SKU-OLD",
    "status": 204
  },
  {
    "method": "GET",
    "path": "/items",
    "status": 200
  }
]
```

## Automated tests

From this directory:

```bash
python -m unittest discover -s tests -v
```

The test suite covers loopback HTTP GET/POST/PUT/DELETE, full output fixture comparisons, CLI output creation, idempotent synchronization, input validation, HTTP conflict handling, and configuration validation.

## File creation and overwrite behavior

- Input files [examples/initial.json](examples/initial.json) and [examples/desired.json](examples/desired.json) are **read**, never modified.
- The three committed **expected-*.json** files are reference fixtures, never modified by the CLI.
- **output/report.json** is created or overwritten with the summary, actions and observed final items.
- **output/final-state.json** is created or overwritten with the final product records.
- **output/http-log.json** is created or overwritten with the ordered real loopback HTTP requests and status codes.
- The **output/** directory is created as needed and excluded from Git by .gitignore. Old output files with these names are overwritten.
- The temporary mock API is bound to 127.0.0.1 and lives only in memory during a run. On exit, it shuts down without persisting an external database.

## Limitations, caveats and safety

This is a **disposable simulated REST service**, not a production connection. The HTTP client sends a Bearer authentication header, but the simplified local mock server **does not validate credentials**. Therefore this sample demonstrates sending authorization headers, not production security. A real integration needs credential storage, TLS, rate-limit handling, retry/backoff policies, pagination, concurrency controls, request tracing, and secure authorization checks. The current client stops on the first HTTP error; it does not automatically retry.

**Deletes are intentionally destructive** within the simulated inventory: SKUs absent from the desired state are deleted. Do not point adapted code at a real business API without written authorization, access controls, backups and a dry-run mode. Calling synchronize() repeatedly against the same in-memory server is idempotent, but calling demo.py again starts from the original synthetic initial.json, deliberately replaying the same changes. The CLI writes output JSON files sequentially; a disk error could leave partial output. This example covers only one fixed REST JSON contract and does **not** implement Cloudflare, webhooks, GPT APIs, a live website, or any client-specific requirements.
