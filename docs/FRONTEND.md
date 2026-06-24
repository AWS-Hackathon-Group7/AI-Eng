# Frontend testing guide

The AI service is a FastAPI app with auto-generated Swagger docs. Two ways to
work with it:

## 1. Interactive docs (recommended for trying endpoints)

```bash
pip install -r requirements-dev.txt     # one time
cp .env.example .env                     # add AWS creds + TEXTRACT_BUCKET
uvicorn app.main:app --reload
```

Open **http://localhost:8000/docs** — full Swagger UI with "Try it out" on every
endpoint. Requests hit real AWS (Bedrock / Textract / Location), so you get live
responses. http://localhost:8000/redoc is the read-only reference view.

## 2. OpenAPI schema (for client generation / Postman)

[`docs/openapi.json`](openapi.json) is the committed schema. Import it into
Postman or Insomnia, or generate a typed client (e.g. `openapi-typescript`,
`openapi-generator`). Regenerate after route/model changes:

```bash
python scripts/export_openapi.py
```

## Endpoints

| Method | Path | Body → returns |
|--------|------|----------------|
| GET  | `/health` | — |
| POST | `/extract` | multipart `file` (pdf/image) → raw OCR text |
| POST | `/doc-analysis` | `{s3Key, expectedDocType}` → `{documentType, fields, isValid, issues}` |
| POST | `/prevetting` | `{ticketId, queueId, serviceName, requiredDocuments, conversationHistory, userMessage, documentAnalysis?}` → `{reply, prevettingStatus, missingDocuments}` |
| POST | `/smart-alert` | `{ticketId, customerLocation?, venueLocation, estimatedCallTime, position}` → `{leaveAtIso, leaveInSec, travelTimeSec, message}` |
| POST | `/routing` | `{queueId, counters, waitingTickets, serviceTimeStats}` → `{reassignments, rationale}` |
| POST | `/manager-advice` | `{queueId, metrics}` → `{advice, severity, suggestedActions}` |

Exact field types are in `docs/openapi.json`.

## Note on a hosted URL

The same app is deployed on AWS (Lambda + Function URL), but the workshop account
blocks **public** Function URLs at the org level, so it only accepts AWS-signed
(IAM) requests — a browser can't open its `/docs` directly. For interactive
testing use the local server above. In production the Backend reaches the five
feature functions via Lambda invoke (see `DEPLOY.md`), not over HTTP.
