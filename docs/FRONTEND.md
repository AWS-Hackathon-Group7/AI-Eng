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

## Hosted public URL (Render)

For a shareable, browser-openable URL the project ships a Render blueprint
([`render.yaml`](../render.yaml)). The AWS account blocks public Lambda Function
URLs, so Render is how we expose a public `/docs`.

Deploy (one time):
1. Push this repo to GitHub (if not already).
2. Render Dashboard → **New → Blueprint** → connect the repo → it reads
   `render.yaml` and creates the `queuesmart-ai` web service.
3. In the service's **Environment**, set the three secret vars:
   `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and (only for temporary
   workshop keys) `AWS_SESSION_TOKEN`.
4. Deploy → you get `https://queuesmart-ai.onrender.com` with `/docs` public.

> ⚠️ The app calls Bedrock/Textract/Location, so those AWS keys must stay valid.
> Workshop STS keys expire in a few hours — for a stable demo URL, use
> long-lived IAM user keys from an account you control (then omit
> `AWS_SESSION_TOKEN`). On Render's free plan the service also sleeps after
> inactivity and cold-starts in ~30s.

In production the Backend reaches the five feature functions via **Lambda
invoke** (see `DEPLOY.md`), not over HTTP — Render is just the testing/demo
surface.
