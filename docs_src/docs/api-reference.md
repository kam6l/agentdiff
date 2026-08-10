# API Reference

REST API reference for AgentDiff (when running in server mode).

> **Note:** AgentDiff is primarily a CLI/library. The HTTP API is experimental and available when running `agentdiff serve`.

## Server Mode

```bash
# Start API server
agentdiff serve --host 0.0.0.0 --port 8080

# With authentication
agentdiff serve --host 0.0.0.0 --port 8080 --api-key YOUR_KEY
```

---

## Authentication

```bash
# Header
Authorization: Bearer YOUR_API_KEY

# Or query parameter
?api_key=YOUR_API_KEY
```

---

## Endpoints

### `POST /api/v1/runs`

Execute a transaction.

**Request:**
```json
{
  "argv": ["python3", "agent.py"],
  "task_description": "Fix the parser",
  "policy": { ... },  // optional, uses default policy if omitted
  "timeout": 300,
  "dry_run": false
}
```

**Response (202 Accepted):**
```json
{
  "run_id": "a1b2c3d4",
  "status": "running",
  "started_at": "2026-01-15T10:30:00Z"
}
```

---

### `GET /api/v1/runs/{run_id}`

Get run status and results.

**Response (200 OK):**
```json
{
  "run_id": "a1b2c3d4",
  "task_description": "Fix the parser",
  "argv": ["python3", "agent.py"],
  "status": "completed",
  "transaction_status": "DENY",
  "blast_radius": {
    "score": 77,
    "raw_score": 77,
    "level": "high",
    "counts": {
      "files_changed": 3,
      "files_deleted": 0,
      "unexpected_files": 2,
      "sensitive_files": 1,
      "dependency_changes": 1,
      "orphan_processes": 0,
      "ports_opened": 0,
      "budget_violations": 0
    },
    "components": [
      {
        "name": "review_mutation",
        "count": 1,
        "weight": 4,
        "points": 4,
        "detail": "modified: pyproject.toml"
      },
      {
        "name": "denied_mutation",
        "count": 1,
        "weight": 30,
        "points": 30,
        "detail": "created: .env"
      },
      {
        "name": "sensitive_path",
        "count": 1,
        "weight": 35,
        "points": 35,
        "detail": ".env"
      }
    ]
  },
  "mutations": [
    {
      "path": "src/parser.py",
      "change_type": "modified",
      "decision": "allow",
      "rule": "filesystem.allow_write[0]",
      "pattern": "src/**"
    },
    {
      "path": "pyproject.toml",
      "change_type": "modified",
      "decision": "review",
      "rule": "filesystem.review[0]",
      "pattern": "pyproject.toml"
    },
    {
      "path": ".env",
      "change_type": "created",
      "decision": "deny",
      "rule": "filesystem.deny[0]",
      "pattern": ".env*"
    }
  ],
  "processes": [
    {
      "pid": 12345,
      "create_time": 1705312200.123,
      "cleanup_status": "verified",
      "cmdline": ["python3", "agent.py"]
    }
  ],
  "ports": {
    "opened": [],
    "closed": []
  },
  "started_at": "2026-01-15T10:30:00Z",
  "completed_at": "2026-01-15T10:30:15Z"
}
```

---

### `GET /api/v1/runs`

List runs.

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| `limit` | integer | Max results (default: 20, max: 100) |
| `offset` | integer | Pagination offset |
| `since` | ISO 8601 | Filter runs after date |
| `status` | string | Filter: running, completed, failed |

**Response:**
```json
{
  "runs": [
    {
      "run_id": "a1b2c3d4",
      "task_description": "Fix the parser",
      "status": "completed",
      "transaction_status": "DENY",
      "blast_radius_score": 77,
      "started_at": "2026-01-15T10:30:00Z",
      "completed_at": "2026-01-15T10:30:15Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

---

### `POST /api/v1/runs/{run_id}/rollback`

Rollback a run.

**Request:**
```json
{
  "safe_only": true,
  "decisions": ["deny", "review"],
  "dry_run": false
}
```

**Response:**
```json
{
  "reverted": [".env", "config.yaml"],
  "conflicts": ["src/main.py"],
  "allowed": ["src/parser.py"],
  "errors": []
}
```

---

### `POST /api/v1/policy/explain`

Explain a path against policy.

**Request:**
```json
{
  "path": ".env",
  "policy": { ... }  // optional
}
```

**Response:**
```json
{
  "path": ".env",
  "decision": "deny",
  "rule": "filesystem.deny[0]",
  "pattern": ".env*",
  "reason": "matched filesystem.deny[0] pattern '.env*'"
}
```

---

### `POST /api/v1/policy/validate`

Validate policy.

**Request:**
```json
{
  "policy": { ... }
}
```

**Response:**
```json
{
  "valid": true,
  "warnings": [],
  "errors": []
}
```

---

### `POST /api/v1/policy/simulate`

Simulate policy against historical runs.

**Request:**
```json
{
  "policy": { ... },
  "run_ids": ["a1b2c3d4", "e5f6g7h8"]
}
```

**Response:**
```json
{
  "results": [
    {
      "run_id": "a1b2c3d4",
      "blast_radius": 69,
      "level": "high",
      "changes_from_current": {
        "score_delta": -8,
        "new_violations": 0
      }
    }
  ]
}
```

---

## Webhooks

Configure webhooks for run completion:

```bash
agentdiff serve \
  --webhook-url https://your-app.com/webhook \
  --webhook-events completed,failed,threshold_exceeded
```

**Payload:**
```json
{
  "event": "completed",
  "run_id": "a1b2c3d4",
  "task_description": "Fix the parser",
  "transaction_status": "DENY",
  "blast_radius_score": 77,
  "completed_at": "2026-01-15T10:30:15Z"
}
```

---

## Error Responses

```json
{
  "error": {
    "code": "RUN_NOT_FOUND",
    "message": "Run a1b2c3d4 not found",
    "details": {}
  }
}
```

| Code | HTTP Status | Description |
|------|-------------|-------------|
| `RUN_NOT_FOUND` | 404 | Run ID doesn't exist |
| `POLICY_INVALID` | 400 | Policy validation failed |
| `RUN_RUNNING` | 409 | Run still in progress |
| `BLAST_RADIUS_EXCEEDED` | 422 | Score exceeded threshold |
| `UNAUTHORIZED` | 401 | Invalid/missing API key |
| `RATE_LIMITED` | 429 | Too many requests |

---

## OpenAPI Spec

Available at `/openapi.json` when server is running.

```bash
curl http://localhost:8080/openapi.json | jq .
```

---

## Next Steps

- [SDK Reference](sdk-reference.md) — Python SDK
- [CLI Reference](cli.md) — Command-line interface
- [Integrations](integrations/langchain.md) — Framework integrations