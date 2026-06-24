# Deploying the QueueSmart AI Lambdas

Five functions, invoked by the Backend team by name with the frozen contract
JSON as the payload.

| § | Function name | Handler | AWS used |
|---|---------------|---------|----------|
| 3.1 | `ai-prevetting` | `app.handlers.prevetting` | Bedrock (Sonnet) + KB |
| 3.2 | `ai-smart-alert` | `app.handlers.smart_alert` | Location Service + Bedrock (Haiku) |
| 3.3 | `ai-routing` | `app.handlers.routing` | Bedrock (Sonnet) |
| 3.4 | `ai-manager-advice` | `app.handlers.manager_advice` | Bedrock (Sonnet) |
| 3.5 | `ai-doc-analysis` | `app.handlers.doc_analysis` | Textract + S3 + Bedrock (Haiku) |

## Primary: `scripts/deploy.py` (boto3, no SAM)

This is how the stack is actually deployed in the workshop account. It builds a
Linux deployment zip, ensures the execution role has the needed permissions, and
creates-or-updates all five functions. Idempotent — re-run it to push changes.

```bash
pip install -r requirements-dev.txt    # boto3 + build tooling (one time)
python scripts/deploy.py               # uses creds from .env / the boto3 chain
```

Why not SAM here:
- The workshop `WSParticipantRole` **can** create Lambdas + `PassRole`, but
  **cannot** create IAM roles — SAM's default flow needs `iam:CreateRole`.
- The installed SAM CLI is built for macOS 13+ and won't load on macOS 12.

So the script **reuses an existing execution role** (`ec2-ubuntu-kiro-workshop-lambda-role`,
which already had `bedrock:InvokeModel` + `bedrock:Retrieve`) and adds one
scoped, additive inline policy for the rest.

### The inline policy it adds
`QueueSmartTextractLocationS3` on the exec role — `geo:CalculateRoute` (on the
calculator), `textract:Start/GetDocumentTextDetection`, and `s3:GetObject` (on
the Textract bucket only). Needed by smart-alert and doc-analysis. Remove with:

```bash
aws iam delete-role-policy \
  --role-name ec2-ubuntu-kiro-workshop-lambda-role \
  --policy-name QueueSmartTextractLocationS3
```

### Configuration
Override any of these via environment variables before running the script
(defaults target the workshop account): `AWS_REGION`, `AWS_ACCOUNT_ID`,
`LAMBDA_EXEC_ROLE`, `TEXTRACT_BUCKET`, `KNOWLEDGE_BASE_ID`,
`LOCATION_CALCULATOR_NAME`, `BEDROCK_MODEL_ID`, `BEDROCK_CHAT_MODEL_ID`. These
are also set as each function's Lambda environment variables; credentials come
from the execution role, not `.env`.

## Alternative: AWS SAM (`template.yaml`)

For an account that **does** allow IAM role creation and a working SAM CLI,
`template.yaml` defines the same five functions with per-function scoped roles:

```bash
sam build --use-container     # container build matches the Lambda runtime
sam deploy --guided
```

The shared resources (Textract bucket, KB `UC64X5D8BU` with checklists ingested,
Location calculator `queuesmart-routes`) must already exist; override via the
template parameters.

## Invoke (smoke test)

```bash
aws lambda invoke --function-name ai-routing \
  --payload '{"queueId":"q_passport","counters":[],"waitingTickets":[],"serviceTimeStats":{}}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

## Triggers

Invoked directly by Backend (event = contract payload), so no event-source
mapping is defined. To later fire `ai-doc-analysis` straight off an S3 upload,
add an S3 event — but note a raw S3 event carries only the object key, not
`expectedDocType`, so Backend-invoke remains the path matching the §3.5 contract.

## Local development (no deploy)

```bash
pip install -r requirements-dev.txt
uvicorn app.main:app --reload      # same logic behind HTTP at /docs
```
