"""§3.4 ai-manager-advice: tell the manager the exact problem and what to do.

INPUT
  { queueId,
    metrics{ avgWaitSec, waitingCount,
             counters[{label,status,avgServiceSec}],
             slowestCounterLabel } }
OUTPUT
  { advice, severity: low|medium|high, suggestedActions[] }

Pure Claude reasoning — be specific and actionable ("Desk 3 is slow — move
staff now"), never generic. `advise` is HTTP-free for the Lambda.
"""

from __future__ import annotations

import boto3
from pydantic import BaseModel, Field

from .config import Settings

_TOOL_NAME = "give_manager_advice"

_TOOL_SPEC = {
    "toolSpec": {
        "name": _TOOL_NAME,
        "description": "Give the manager a specific diagnosis and concrete actions.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "advice": {
                        "type": "string",
                        "description": "One or two specific sentences naming the exact problem and fix.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                    },
                    "suggestedActions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Concrete, immediately actionable steps.",
                    },
                },
                "required": ["advice", "severity", "suggestedActions"],
            }
        },
    }
}

_SYSTEM = (
    "You advise a branch manager when a queue backs up. You get queue metrics: "
    "average wait, number waiting, per-counter service speed, and the slowest "
    "counter. Diagnose the SPECIFIC bottleneck (name the counter, compare its "
    "speed to the others) and give concrete actions a manager can take right "
    "now. Never be generic ('consider optimizing'); always be specific ('Desk 3 "
    "is ~2x slower — move a staff member there'). Set severity from the wait: "
    "low under ~10 min, medium ~10-30 min, high over ~30 min, also weighing how "
    "many are waiting. Always call the tool."
)


class ManagerAdviceRequest(BaseModel):
    queueId: str
    metrics: dict


class ManagerAdviceResponse(BaseModel):
    advice: str
    severity: str
    suggestedActions: list[str] = Field(default_factory=list)


def advise(req: ManagerAdviceRequest, settings: Settings) -> ManagerAdviceResponse:
    prompt = f"queueId: {req.queueId}\nmetrics: {req.metrics}"
    client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    resp = client.converse(
        modelId=settings.bedrock_chat_model_id,
        system=[{"text": _SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        toolConfig={
            "tools": [_TOOL_SPEC],
            "toolChoice": {"tool": {"name": _TOOL_NAME}},
        },
        inferenceConfig={"maxTokens": 512, "temperature": 0.3},
    )
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block and block["toolUse"]["name"] == _TOOL_NAME:
            return ManagerAdviceResponse(**block["toolUse"]["input"])
    raise RuntimeError("Claude did not return the expected tool call")
