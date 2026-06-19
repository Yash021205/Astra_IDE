# API Reference

All endpoints are mounted under `/api/v1`. Auth header: `Authorization: Bearer <jwt>`.

Interactive docs (Swagger UI) are served at `/api/v1/docs` when the backend is running.

## Auth

### POST `/auth/register`

```json
Request:  { "email": "...", "username": "...", "password": "..." }
201:      { "access_token": "...", "token_type": "bearer", "user": { ... } }
409:      { "detail": "Email or username already registered" }
```

### POST `/auth/login`  (OAuth2 form-encoded)

```
Content-Type: application/x-www-form-urlencoded
Body:    username=<username_or_email>&password=...

200:     { "access_token": "...", "token_type": "bearer", "user": { ... } }
401:     { "detail": "Incorrect username/email or password" }
```

### GET `/auth/me`

```
200:     UserOut
401:     missing/invalid token
```

## Workspaces

### POST `/workspaces`

```json
Request: {
  "name": "my-project",
  "language": "python",
  "network_access": false,
  "filesystem_write": true,
  "cpu_request": 0.5,
  "memory_request": 512,
  "initial_code": ""
}

201:     WorkspaceOut    (risk_score and sandbox_tier set by backend)
```

### GET `/workspaces`

```
200:     { "total": N, "items": [WorkspaceOut, ...] }
```

### GET `/workspaces/{id}`

```
200:     WorkspaceOut
404:     not found / not owned by user
```

### PATCH `/workspaces/{id}`

```json
Request: { "name": "...", "status": "..." }   (both optional)
200:     WorkspaceOut
```

### POST `/workspaces/{id}/start`

Transitions status to `RUNNING`. In Phase ≥ 1 this also launches a pod.

```
200:     WorkspaceOut
```

### POST `/workspaces/{id}/stop`

```
200:     WorkspaceOut (status=STOPPED)
```

### DELETE `/workspaces/{id}`

```
204:     no body
```

## Schemas

### `UserOut`

```json
{
  "id": 1,
  "email": "...",
  "username": "...",
  "trust_score": 0.5,
  "preferred_lang": "python"
}
```

### `WorkspaceOut`

```json
{
  "id": 1,
  "name": "my-project",
  "language": "python",
  "status": "RUNNING",                  // PENDING | PREWARMED | RUNNING | STOPPED | FAILED | ARCHIVED
  "sandbox_tier": "gvisor",             // runc | gvisor | firecracker
  "risk_score": 0.40,
  "network_access": true,
  "filesystem_write": true,
  "cpu_request": 0.5,
  "memory_request": 512,
  "cluster_id": "cluster-a",
  "node_name": "node-3",
  "pod_name": "ws-1-abc12345",
  "yjs_room": "ws-abc123def456",        // used by frontend to join collab
  "owner_id": 1,
  "created_at": "2026-05-14T10:00:00Z",
  "updated_at": "2026-05-14T10:05:00Z",
  "last_active_at": "2026-05-14T10:05:00Z"
}
```

## Carbon intensity

### GET `/carbon/intensity?zone=DK-DK1`

Returns current grid carbon intensity in gCO2eq/kWh for the requested zone.
Falls back to a static historical average if the API is unreachable or quota
is exhausted (so the scheduler always gets a number).

```json
200: {
  "zone":             "DK-DK1",
  "carbon_intensity": 53.0,
  "is_estimated":     true,
  "is_fallback":      false,
  "source":           "api",
  "timestamp":        1715703600.5
}
```

## Health endpoints

| Path | Service |
|------|---------|
| `GET /healthz`        | Backend         |
| `GET :1234/healthz`   | Collab server   |
| `GET :1234/stats`     | Collab server (per-room metrics) |
