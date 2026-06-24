# Deploying the QueueSmart AI Lambdas

Five functions, one SAM stack. Backend invokes them by name with the frozen
contract JSON as the payload.

| § | Function name | Handler | AWS used |
|---|---------------|---------|----------|
| 3.1 | `ai-prevetting` | `app.handlers.prevetting` | Bedrock (Sonnet) + KB |
| 3.2 | `ai-smart-alert` | `app.handlers.smart_alert` | Location Service + Bedrock (Haiku) |
| 3.3 | `ai-routing` | `app.handlers.routing` | Bedrock (Sonnet) |
| 3.4 | `ai-manager-advice` | `app.handlers.manager_advice` | Bedrock (Sonnet) |
| 3.5 | `ai-doc-analysis` | `app.handlers.doc_analysis` | Textract + S3 + Bedrock (Haiku) |

## Prerequisites

- **AWS SAM CLI** and **Docker** (build uses a container so the compiled
  `pydantic-core` wheel matches the Lambda runtime).
- AWS credentials with permission to create the stack's Lambdas + IAM roles.
  > Note: the workshop `WSParticipantRole` may **not** allow IAM role / Lambda
  > creation. If `sam deploy` fails on `iam:CreateRole` or `lambda:CreateFunction`,
  > you need an admin/instructor role to deploy.
- The shared resources already exist (created during development): the Textract
  bucket, the Bedrock Knowledge Base (`UC64X5D8BU`, checklists ingested), and the
  Location route calculator (`queuesmart-routes`). Override them via the
  template parameters if yours differ.

## Build & deploy

```bash
sam build --use-container
sam deploy --guided        # first time: pick stack name, region us-west-2, confirm
# subsequent deploys:
sam deploy
```

`sam build` packages the `CodeUri: .` directory and installs `requirements.txt`
(the slim runtime set — not the dev/FastAPI deps). Build from a clean checkout;
the local `.venv/` is gitignored and should not be present in the build tree.

## Configuration

All config is passed as template parameters (with dev defaults) and surfaced to
the functions as environment variables — see `template.yaml`. Credentials come
from each function's execution role, **not** from `.env` (that file is local-only).
`AWS_REGION` is provided automatically by the Lambda runtime.

## Invoke (smoke test)

```bash
# §3.3 routing
aws lambda invoke --function-name ai-routing \
  --payload '{"queueId":"q_passport","counters":[],"waitingTickets":[],"serviceTimeStats":{}}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json

# §3.5 doc-analysis (object must already be in the Textract bucket)
aws lambda invoke --function-name ai-doc-analysis \
  --payload '{"s3Key":"tkt_123/id.pdf","expectedDocType":"Ghana Card"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

## Triggers

These are invoked directly by Backend (the event = the contract payload), so no
event-source mapping is defined here. If you later want `ai-doc-analysis` to fire
straight off an S3 upload, add an `Events: { S3: ... }` block — but note a raw S3
event carries only the object key, not `expectedDocType`, so Backend-invoke
remains the path that matches the §3.5 contract.

## Local development (no deploy)

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # same logic behind HTTP at /docs
```
