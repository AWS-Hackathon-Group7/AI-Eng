# QueueSmart — AI Engineering Team

> **Your mission:** Build the brain. QueueSmart isn't "another wait-time display" — **Amazon Bedrock (Claude) actively manages the queue.** You own the four smart features, the prompts, the Knowledge Base of document checklists, document reading with Textract, and travel-time reasoning with Location Service. You ship **Lambda functions with frozen JSON contracts** that the Backend team invokes.

---

## 1. The four AI features (this is the product)

| # | Feature | Plain English | Status for hackathon |
|---|---------|---------------|----------------------|
| 1 | **Dynamic queue routing** | If a counter is stuck on a hard task, move easy tasks to free counters so the line keeps moving. | If time |
| 2 | **Document pre-vetting** | In the in-app chat, Claude checks you have the right papers **before** you arrive. | ⭐ **Hero — build first** |
| 3 | **Just-in-time alerts** | The "leave now" message factors in your **location + live traffic**, not a fixed timer. | ⭐ **Hero — build first** |
| 4 | **Manager advice** | When waits spike, Claude tells the manager the exact problem and what to do. | If time |

> **Focus order for the demo:** #2 and #3 are the "hero AI" — they fully show off Bedrock and demo best. Build those to a polished state before touching #1 and #4.

---

## 2. What you own

| Capability | AWS service | Notes |
|------------|-------------|-------|
| Reasoning / chat | **Amazon Bedrock — Claude** | Use the latest available Claude model in the hackathon region (e.g. a Claude Sonnet for chat/advice; a smaller/faster Claude for cheap classification). |
| Document checklists | **Bedrock Knowledge Base** | Per-service required-documents docs in S3, indexed for retrieval so pre-vetting is accurate and grounded. |
| Document reading | **Amazon Textract** | Extract text/fields from uploaded IDs, forms, letters. |
| Travel time / traffic | **Amazon Location Service** | Route + live-traffic ETA from customer location → venue. |
| Stats for routing | **Amazon Timestream** | Read service-speed / wait-time history (Backend writes it). |
| Compute | **AWS Lambda** | One function per feature; Backend invokes you. |

You do **not** own API Gateway, the DB writes, the WebSocket, or sending notifications — **Backend invokes your Lambdas and persists/broadcasts your output.** Your job ends when you return clean JSON.

---

## 3. How you plug in (the integration contract)

Backend calls you on events / requests and writes your results back. **Freeze these JSON shapes with the Backend team on day one** and put them in the shared `models/`. (Mirrors Backend README §9.)

### 3.1 Pre-vetting chat — `ai-prevetting` Lambda  ⭐
Invoked by Backend's `POST /tickets/{id}/chat` handler.
```jsonc
// INPUT
{
  "ticketId": "tkt_...",
  "queueId": "q_passport",
  "serviceName": "Passport Renewal",
  "requiredDocuments": ["Old passport", "Ghana Card", "Passport photo"],
  "conversationHistory": [{ "role": "user|assistant", "content": "..." }],
  "userMessage": "I have my old passport and a photo",
  "documentAnalysis": [ /* optional, from §3.5 */ ]
}
// OUTPUT
{
  "reply": "Great — you still need your Ghana Card. Do you have it?",
  "prevettingStatus": "pending",        // pending | passed | failed
  "missingDocuments": ["Ghana Card"]
}
```
- Ground the checklist in the **Knowledge Base** (retrieve the doc list for `queueId`/service), don't rely on the model's memory.
- Be conversational and reassuring; one question at a time; confirm when fully ready (`passed`).

### 3.2 Smart "leave now" alert — `ai-smart-alert` Lambda  ⭐
Invoked by Backend's `position.threshold` event consumer.
```jsonc
// INPUT
{
  "ticketId": "tkt_...",
  "customerLocation": { "lat": 5.56, "lng": -0.20 },
  "venueLocation":    { "lat": 5.60, "lng": -0.18 },
  "estimatedCallTime": "2026-06-24T10:42:00Z",
  "position": 3
}
// OUTPUT
{
  "leaveAtIso": "2026-06-24T10:09:00Z",
  "leaveInSec": 600,
  "travelTimeSec": 1500,
  "message": "Leave now — with current traffic it's ~25 min, so you'll arrive 3 min before your turn."
}
```
- Use **Location Service** route calculator (with traffic) for `travelTimeSec`; subtract from `estimatedCallTime` minus a safety buffer to get `leaveAtIso`.
- Use Claude to phrase a short, friendly `message`. If no location, return a time-only fallback and say so.

### 3.3 Dynamic queue routing — `ai-routing` Lambda
Invoked by Backend on `ticket.created` / `ticket.served` / `counter.*`.
```jsonc
// INPUT
{
  "queueId": "q_passport",
  "counters": [{ "counterId":"c1","label":"Desk 1","status":"busy","skills":["renewal"],"currentTaskType":"new_application" }],
  "waitingTickets": [{ "ticketId":"...","taskType":"renewal","waitingSec":900 }],
  "serviceTimeStats": { "renewal": 240, "new_application": 900 }   // avg seconds from Timestream
}
// OUTPUT
{
  "reassignments": [{ "ticketId":"...", "fromCounterId":"c2", "toCounterId":"c1", "reason":"c1 is free and handles renewals fastest" }],
  "rationale": "Desk 2 is stuck on a new application; routing 3 quick renewals to Desk 1 to keep the line moving."
}
```
- Keep reassignments minimal and explainable. Return `[]` when no change is worthwhile (don't thrash the queue).

### 3.4 Manager advice — `ai-manager-advice` Lambda
Invoked by Backend on `queue.backed_up`.
```jsonc
// INPUT
{ "queueId": "q_passport",
  "metrics": { "avgWaitSec": 2700, "waitingCount": 24,
               "counters": [{ "label":"Desk 3","status":"busy","avgServiceSec":1200 }],
               "slowestCounterLabel": "Desk 3" } }
// OUTPUT
{ "advice": "Desk 3 is running ~2× slower than the others — move a staff member there or reassign its complex cases.",
  "severity": "high",                         // low | medium | high
  "suggestedActions": ["Add staff to Desk 3", "Route simple tasks to Desks 1–2"] }
```
- Be specific and actionable ("Desk 3 is slow — move staff now"), never generic ("consider optimizing").

### 3.5 Document analysis — `ai-doc-analysis` Lambda
Invoked by Backend after a customer uploads a file (S3 event).
```jsonc
// INPUT  { "s3Key": "tkt_.../ghana_card.jpg", "expectedDocType": "Ghana Card" }
// OUTPUT { "documentType": "Ghana Card", "fields": { "name":"...", "idNumber":"..." }, "isValid": true, "issues": [] }
```
- Run **Textract** to extract text/fields, then use Claude to classify the doc and judge whether it matches `expectedDocType` and looks complete. Feed the result back into pre-vetting (§3.1).

---

## 4. Knowledge Base (document checklists)

The accuracy of pre-vetting depends on this — build it early.
- Author a short doc per service (e.g. `passport-renewal.md`, `birth-certificate.md`) listing **required documents, common mistakes, and validity rules.** Store in S3.
- Create a **Bedrock Knowledge Base** over that bucket (managed vector store / OpenSearch Serverless).
- At chat time, **retrieve** the relevant checklist for the `queueId`/service and put it in the prompt context (RAG). This keeps Claude grounded and makes it trivial to add new services without code changes.

---

## 5. Repo structure

```
ai-engineering/
├── src/
│   ├── prevetting/         # §3.1 handler + prompt
│   ├── smart_alert/        # §3.2 handler + Location Service client
│   ├── routing/            # §3.3 handler + prompt
│   ├── manager_advice/     # §3.4 handler + prompt
│   ├── doc_analysis/       # §3.5 handler + Textract client
│   └── lib/
│       ├── bedrock.ts      # Claude invoke wrapper (model id, retries, JSON-mode parsing)
│       ├── kb.ts           # Knowledge Base retrieve
│       └── prompts/        # versioned prompt templates
├── knowledge-base/         # the service checklist docs (source of truth → synced to S3)
├── evals/                  # sample inputs + expected behavior per feature
└── README.md               # this file
```

---

## 6. Prompt engineering guidelines

- **Force structured output.** Every function (except the chat `reply`) must return strict JSON matching §3. Use a system prompt that says "respond only with JSON in this schema," validate the parse, and **repair/retry once** on bad JSON. Never let malformed output reach the Backend.
- **Ground, don't guess.** Pre-vetting and doc-analysis must use the Knowledge Base / Textract facts, not assumptions.
- **Be concise and human** in customer-facing text (chat replies, alert messages); be specific and directive in manager advice.
- **Latency matters** for chat — use a fast Claude model and stream if the Backend supports it; reserve heavier reasoning for routing/advice which run on events, not in the user's face.
- **Version your prompts** in `lib/prompts/` and note which model id each targets. Default to the **latest, most capable Claude** available in the hackathon region; check Bedrock model access is enabled on day one.
- **Cost/guardrails:** cap `max_tokens`, set sensible temperature (low for JSON tasks), and short-circuit obvious cases (e.g. routing returns `[]` when one counter is open).

---

## 7. Build order (mapped to the hackathon plan)

1. **Day-one setup:** confirm **Bedrock model access** in the region; stand up the `bedrock.ts` wrapper; agree the §3 JSON contracts with Backend and commit them to `models/`.
2. **Hero #2 — Pre-vetting chat:** Knowledge Base with 1–2 service checklists → `ai-prevetting` returning grounded replies + status. ✅ when the chat correctly tells a user what document they're missing.
3. **Hero #3 — Smart alert:** `ai-smart-alert` using Location Service traffic ETA → a real "leave now" time + message. ✅ when changing the mock customer location changes the leave time.
4. **Doc analysis:** wire Textract → feed results into pre-vetting.
5. **If time — #1 routing & #4 manager advice:** the event-driven Lambdas, so the manager dashboard shows live advice and the queue self-optimizes.

---

## 8. Definition of done (per feature)

- [ ] Input/output exactly matches the §3 contract (validated, typed in `models/`).
- [ ] JSON output is always parseable (schema-validated + retry on failure).
- [ ] Grounded in KB/Textract/Location data where applicable — not hallucinated.
- [ ] A sample in `evals/` proving the happy path **and** a tricky case (missing doc, no location, single counter).
- [ ] Sensible latency + token caps; errors return a safe fallback, never a 500 that breaks the user flow.
- [ ] Bedrock model id and region documented; access confirmed.

---

## 9. Coordinating with the other teams

- **Backend** invokes your Lambdas and persists/broadcasts your output — keep the §3 contracts frozen and tell them immediately if a shape must change. They give you: Lambda invoke wiring, the event names, Timestream read access, and S3 doc keys.
- **Frontend** renders your results: the chat `reply` + `prevettingStatus`/`missingDocuments` checklist, the `leave_now` banner/message, and the manager advice tile. Keep messages short and display-ready so they need zero post-processing.
