"""§3.3 ai-routing: dynamic queue routing (move easy tasks to free counters).

INPUT
  { queueId,
    counters[{counterId,label,status,skills[],currentTaskType}],
    waitingTickets[{ticketId,taskType,waitingSec}],
    serviceTimeStats{taskType: avgSeconds} }
OUTPUT
  { reassignments[{ticketId,fromCounterId,toCounterId,reason}], rationale }

Pure Claude reasoning — keep reassignments minimal and explainable; return an
empty list when no change is worthwhile (don't thrash the queue). `route` is
HTTP-free for the Lambda.
"""

from __future__ import annotations

import boto3
from pydantic import BaseModel, Field

from .config import Settings

_TOOL_NAME = "propose_routing"

_TOOL_SPEC = {
    "toolSpec": {
        "name": _TOOL_NAME,
        "description": "Propose minimal, explainable queue reassignments.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "reassignments": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "ticketId": {"type": "string"},
                                "fromCounterId": {
                                    "type": "string",
                                    "description": "Counter the ticket would otherwise be served by (e.g. the stuck/busy one).",
                                },
                                "toCounterId": {
                                    "type": "string",
                                    "description": "Free/faster counter to move it to. Must have the required skill.",
                                },
                                "reason": {"type": "string"},
                            },
                            "required": ["ticketId", "fromCounterId", "toCounterId", "reason"],
                        },
                    },
                    "rationale": {
                        "type": "string",
                        "description": "One short explanation of the overall decision (or why no change).",
                    },
                },
                "required": ["reassignments", "rationale"],
            }
        },
    }
}

_SYSTEM = (
    "You optimise a single service queue. Counters have skills and a current "
    "task; some are busy on slow tasks while others are free. Waiting tickets "
    "have a task type and how long they've waited. serviceTimeStats gives the "
    "average seconds per task type. Move quick tasks to free or faster counters "
    "so the line keeps moving, BUT only when it clearly helps. Rules: never "
    "assign a task to a counter lacking the required skill; keep reassignments "
    "minimal and each one explainable; if nothing is clearly worth changing, "
    "return an empty reassignments list and say why in rationale. Always call "
    "the tool."
)


class RoutingRequest(BaseModel):
    queueId: str
    counters: list[dict] = Field(default_factory=list)
    waitingTickets: list[dict] = Field(default_factory=list)
    serviceTimeStats: dict[str, float] = Field(default_factory=dict)


class Reassignment(BaseModel):
    ticketId: str
    fromCounterId: str
    toCounterId: str
    reason: str


class RoutingResponse(BaseModel):
    reassignments: list[Reassignment] = Field(default_factory=list)
    rationale: str


def route(req: RoutingRequest, settings: Settings) -> RoutingResponse:
    prompt = (
        f"queueId: {req.queueId}\n"
        f"counters: {req.counters}\n"
        f"waitingTickets: {req.waitingTickets}\n"
        f"serviceTimeStats: {req.serviceTimeStats}"
    )
    client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    resp = client.converse(
        modelId=settings.bedrock_chat_model_id,
        system=[{"text": _SYSTEM}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        toolConfig={
            "tools": [_TOOL_SPEC],
            "toolChoice": {"tool": {"name": _TOOL_NAME}},
        },
        inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
    )
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block and block["toolUse"]["name"] == _TOOL_NAME:
            return RoutingResponse(**block["toolUse"]["input"])
    raise RuntimeError("Claude did not return the expected tool call")
