# QueueSmart AI: Endpoint Integration & Logic Guide

This guide describes how each of the five QueueSmart AI endpoints operates, the payloads they accept and return, the internal code functions they trigger, and how the backend should interact with them.

---

## 1. Do We Need a Cron Job?

> [!IMPORTANT]
> **No, you do not need to implement any cron jobs for the AI service.**
> The AI service is designed as a set of **event-driven, stateless functions** (either running inside AWS Lambda or exposed via FastAPI endpoints). They do not retain database state or run background schedules on their own. 
> Instead, the Backend triggers the AI endpoints on-demand when specific user actions or system events occur. The Backend is responsible for maintaining the state, tracking wait times, and firing events.

---

## 2. Endpoints: Inputs, Outputs, and Logic Flows

```
  AWS Lambda Handler             FastAPI Route             Business Logic Code File
  app.handlers.doc_analysis  -->  POST /doc-analysis  -->  app/doc_analysis.py
  app.handlers.prevetting     -->  POST /prevetting     -->  app/prevetting.py
  app.handlers.smart_alert    -->  POST /smart-alert    -->  app/smart_alert.py
  app.handlers.routing        -->  POST /routing        -->  app/routing.py
  app.handlers.manager_advice -->  POST /manager-advice -->  app/manager_advice.py
```

---

### 2.1 Document Analysis (`ai-doc-analysis`)

#### Trigger Event (Backend Interaction)
* **When**: Triggers immediately after a customer uploads a document file (e.g. JPG, PNG, PDF) to the designated S3 bucket.
* **Backend Action**: The Backend catches the upload event, then invokes this Lambda (or calls the HTTP API) to process the document.

#### API Payload Contracts

**Input Payload (`DocAnalysisRequest`)**
```json
{
  "s3Key": "tickets/tkt_9876/ghana_card.jpg",
  "expectedDocType": "Ghana Card"
}
```

**Output Response (`DocAnalysisResponse`)**
```json
{
  "documentType": "Ghana Card",
  "fields": {
    "name": "Kofi Mensah",
    "idNumber": "GHA-720192839-0"
  },
  "isValid": true,
  "issues": []
}
```

#### Code Flow & Execution Logic
1. **FastAPI Route / Handler**: Receives `s3Key` and `expectedDocType`.
2. **Text Extraction**: Calls [app/textract.py](file:///c:/Users/User/Music/AI/AWS%20Hackathon/AI-Eng/app/textract.py) -> `extract_text_from_s3(s3_key)`.
   * Sends an asynchronous document text detection request to AWS Textract (`start_document_text_detection`).
   * Polls Textract until the job finishes.
   * Collects all pages and joins `LINE` blocks together into a single plain-text string.
3. **Classification**: Calls [app/bedrock.py](file:///c:/Users/User/Music/AI/AWS%20Hackathon/AI-Eng/app/bedrock.py) -> `classify(text, expected_doc_type)`.
   * Invokes **Claude 4.5 Haiku** via Bedrock Runtime Converse API.
   * Passes the extracted OCR text and the expected document type.
   * Forcefully requests a tool call to return structured JSON.
   * Claude checks:
     * Does the text represent the expected document type?
     * Are required fields visible?
     * Is the document expired?
4. **Response**: Returns if it is valid, the identified document type, extracted fields, and a list of issues (e.g. `["Document is expired"]`).

---

### 2.2 Document Pre-vetting Chat (`ai-prevetting`)

#### Trigger Event (Backend Interaction)
* **When**: Triggers whenever a customer sends a message in the pre-vetting chat interface (`POST /tickets/{id}/chat`).
* **Backend Action**: The Backend fetches the conversation history, aggregates any previously executed `documentAnalysis` results (from step 2.1), and calls this endpoint to get the assistant's response.

#### API Payload Contracts

**Input Payload (`PrevetRequest`)**
```json
{
  "ticketId": "tkt_9876",
  "queueId": "q_passport",
  "serviceName": "Passport Renewal",
  "requiredDocuments": ["Old passport", "Ghana Card", "Passport photo"],
  "conversationHistory": [
    { "role": "user", "content": "Hi, I want to verify my documents." },
    { "role": "assistant", "content": "Hello! Please upload your Ghana Card and old passport." }
  ],
  "userMessage": "I just uploaded my Ghana Card. Do I need anything else?",
  "documentAnalysis": [
    {
      "documentType": "Ghana Card",
      "fields": { "name": "Kofi Mensah", "idNumber": "GHA-720192839-0" },
      "isValid": true,
      "issues": []
    }
  ]
}
```

**Output Response (`PrevetResponse`)**
```json
{
  "reply": "Thank you! Your Ghana Card looks perfect. Next, please upload your original Old Passport to complete verification.",
  "prevettingStatus": "pending",
  "missingDocuments": ["Old passport", "Passport photo"]
}
```

#### Code Flow & Execution Logic
1. **Knowledge Retrieval**: Calls [app/knowledge_base.py](file:///c:/Users/User/Music/AI/AWS%20Hackathon/AI-Eng/app/knowledge_base.py) -> `retrieve_checklist(serviceName, queueId)`.
   * Query is run against the **Bedrock Knowledge Base** vector index (e.g., retrieving guidelines from `passport-renewal.md`).
2. **Context Assembly**: Calls [app/prevetting.py](file:///c:/Users/User/Music/AI/AWS%20Hackathon/AI-Eng/app/prevetting.py) -> `_build_system()`.
   * Integrates the retrieved document rules, input checklist (`requiredDocuments`), and text-extracted facts (`documentAnalysis`) into the system prompt.
3. **Claude Chat Reasoning**:
   * Invokes **Claude 3.5 Sonnet** (retains higher conversational reasoning).
   * Passes the conversation history + the system prompt.
   * Restricts output using tool calls (`respond_to_customer`).
4. **Rules & Constraints**:
   * Must ask for only **one missing document at a time** to avoid overwhelming the user.
   * If all documents are validated: sets status to `"passed"` and congratulates the user.
   * If any document fails validation: sets status to `"failed"` and details how to fix it.

---

### 2.3 Smart "Leave Now" Alert (`ai-smart-alert`)

#### Trigger Event (Backend Interaction)
* **When**: Triggers periodically (e.g. every few minutes) or when a queue state update changes the ticket's position or estimated call time.
* **Backend Action**: The Backend tracks user location updates and queue movement, then checks if it needs to recalculate a departure warning for tickets with active travel options.

#### API Payload Contracts

**Input Payload (`SmartAlertRequest`)**
```json
{
  "ticketId": "tkt_9876",
  "customerLocation": { "lat": 5.556, "lng": -0.201 }, 
  "venueLocation": { "lat": 5.602, "lng": -0.187 },
  "estimatedCallTime": "2026-06-25T12:00:00Z",
  "position": 3
}
```

**Output Response (`SmartAlertResponse`)**
```json
{
  "leaveAtIso": "2026-06-25T11:25:00Z",
  "leaveInSec": 1500,
  "travelTimeSec": 1800,
  "message": "Leave now — with current traffic, it will take about 30 minutes to arrive, placing you there 5 minutes before your turn."
}
```

#### Code Flow & Execution Logic
1. **Location Routing Service**:
   * If `customerLocation` is provided, calls `_travel_time_seconds()` which initiates `geo:CalculateRoute` via the **Amazon Location Service**.
   * It requests driving routes with `DepartNow=True` to calculate the real-time travel duration (incorporating live traffic data).
2. **Leave-Time Calculation**:
   * Calculation: `leave_at = estimatedCallTime - travelTimeSec - arrival_buffer` (default safety buffer is 5 minutes).
   * Calculates `leaveInSec` as the seconds between current time (`now`) and the calculated `leave_at` time.
3. **Claude Message Phrasing**:
   * Calls **Claude 4.5 Haiku** to generate a single-sentence friendly push notification message explaining when to leave based on traffic.
   * **Location Fallback**: If `customerLocation` is `null`, it skips route calculation, sets `leave_at = estimatedCallTime - arrival_buffer`, and directs Claude to write a push message reminding the user to start moving, indicating that live traffic could not be checked without location access.

---

### 2.4 Dynamic Queue Routing (`ai-routing`)

#### Trigger Event (Backend Interaction)
* **When**: Triggers on queue events: a new ticket is created (`ticket.created`), a counter finishes serving a customer (`ticket.served`), or a staff member changes their status (`counter.status_changed`).
* **Backend Action**: The Backend sends the list of waiting tickets, desks, and current wait-time stats to request an optimized configuration.

#### API Payload Contracts

**Input Payload (`RoutingRequest`)**
```json
{
  "queueId": "q_passport",
  "counters": [
    { "counterId": "c1", "label": "Desk 1", "status": "idle", "skills": ["renewal", "first_time"] },
    { "counterId": "c2", "label": "Desk 2", "status": "busy", "skills": ["renewal"], "currentTaskType": "new_application" }
  ],
  "waitingTickets": [
    { "ticketId": "tkt_101", "taskType": "renewal", "waitingSec": 120 },
    { "ticketId": "tkt_102", "taskType": "new_application", "waitingSec": 450 }
  ],
  "serviceTimeStats": {
    "renewal": 300,
    "new_application": 1200
  }
}
```

**Output Response (`RoutingResponse`)**
```json
{
  "reassignments": [
    {
      "ticketId": "tkt_101",
      "fromCounterId": "c2",
      "toCounterId": "c1",
      "reason": "Desk 1 is currently free and can process renewals quickly, resolving congestion."
    }
  ],
  "rationale": "Moved renewal ticket 101 to idle Desk 1 so Desk 2 is not overwhelmed by simple renewals while processing a complex new application."
}
```

#### Code Flow & Execution Logic
1. **Reasoning Engine**:
   * Sends the current arrangement of counters, waiting tasks, and service-duration historical statistics to **Claude 3.5 Sonnet**.
2. **Rules & Constraints**:
   * Claude must respect skills (never route a task to a desk without that skill).
   * Proposes only high-value movements.
   * If there is no clear benefit (e.g. only one counter is open), returns an empty `reassignments` list to prevent desk-swapping overhead.
3. **Response**: Proposes reassignments with short, client-safe justification reasons.

---

### 2.5 Manager Advice (`ai-manager-advice`)

#### Trigger Event (Backend Interaction)
* **When**: Triggers when queue congestion metrics exceed a pre-defined threshold (e.g. average wait time goes above 30 minutes, or the queue length exceeds 15 people).
* **Backend Action**: The Backend fires a `queue.backed_up` trigger and invokes this function to render operational diagnostics in the manager's administration dashboard.

#### API Payload Contracts

**Input Payload (`ManagerAdviceRequest`)**
```json
{
  "queueId": "q_passport",
  "metrics": {
    "avgWaitSec": 2400,
    "waitingCount": 18,
    "counters": [
      { "label": "Desk 1", "status": "busy", "avgServiceSec": 300 },
      { "label": "Desk 2", "status": "busy", "avgServiceSec": 1400 }
    ],
    "slowestCounterLabel": "Desk 2"
  }
}
```

**Output Response (`ManagerAdviceResponse`)**
```json
{
  "advice": "Desk 2 is currently averaging 1400 seconds per transaction, which is roughly 4x slower than Desk 1. This bottleneck is driving the 40-minute average wait time.",
  "severity": "high",
  "suggestedActions": [
    "Move a staff member to assist Desk 2 with document intake",
    "Route simple renewal requests exclusively to Desk 1"
  ]
}
```

#### Code Flow & Execution Logic
1. **Diagnosis Engine**:
   * Takes the average branch wait times, waitlist length, and counter speeds.
   * Passes statistics to **Claude 3.5 Sonnet**.
2. **Logic Rules**:
   * Compares the slowest counter's rate against the other desks.
   * Determines severity: `"low"` (wait times < 10 mins), `"medium"` (10-30 mins), `"high"` (wait times > 30 mins, or extremely long backlogs).
   * Generates actionable branch solutions instead of general business tips.
