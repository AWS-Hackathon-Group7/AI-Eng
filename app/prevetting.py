"""§3.1 ai-prevetting: conversational document pre-vetting (the hero feature).

INPUT
  { ticketId, queueId, serviceName, requiredDocuments[],
    conversationHistory[{role, content}], userMessage,
    documentAnalysis[]  // optional, from §3.5 }
OUTPUT
  { reply, prevettingStatus: pending|passed|failed, missingDocuments[] }

Grounded in the Knowledge Base checklist (§4); falls back to the request's
requiredDocuments if nothing is indexed yet. `prevet` is HTTP-free so it drops
into the Lambda the Backend invokes.
"""

from __future__ import annotations

import boto3
from pydantic import BaseModel, Field

from .config import Settings
from .knowledge_base import KnowledgeBase

_TOOL_NAME = "respond_to_customer"

_TOOL_SPEC = {
    "toolSpec": {
        "name": _TOOL_NAME,
        "description": "Reply to the customer and report pre-vetting status.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "reply": {
                        "type": "string",
                        "description": "Conversational, reassuring reply. Ask for one missing document at a time.",
                    },
                    "prevettingStatus": {
                        "type": "string",
                        "enum": ["pending", "passed", "failed"],
                        "description": "passed = all required docs confirmed valid; failed = a provided doc is wrong/invalid and must be corrected; pending = still gathering.",
                    },
                    "missingDocuments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Required documents not yet confirmed present and valid.",
                    },
                },
                "required": ["reply", "prevettingStatus", "missingDocuments"],
            }
        },
    }
}


class PrevetRequest(BaseModel):
    ticketId: str
    queueId: str
    serviceName: str
    requiredDocuments: list[str] = Field(default_factory=list)
    conversationHistory: list[dict] = Field(default_factory=list)
    userMessage: str
    documentAnalysis: list[dict] = Field(default_factory=list)


class PrevetResponse(BaseModel):
    reply: str
    prevettingStatus: str
    missingDocuments: list[str] = Field(default_factory=list)


def _build_system(req: PrevetRequest, checklist: str) -> str:
    parts = [
        "You are QueueSmart's document pre-vetting assistant for a government "
        "service queue. Your job is to confirm — before the customer travels to "
        "the office — that they have every required document, and that any "
        "documents already uploaded are valid.",
        "",
        "Behaviour:",
        "- Be warm, concise, and reassuring.",
        "- Ask for only ONE missing document at a time.",
        "- Ground your checklist ONLY in the information below; do not invent "
        "requirements.",
        "- When every required document is confirmed present and valid, set "
        "prevettingStatus to 'passed' and congratulate them.",
        "- If an uploaded document is the wrong type or invalid, set status to "
        "'failed' and clearly explain what to fix.",
        "- Otherwise status is 'pending'. Always call the tool.",
        "",
        f"Service: {req.serviceName} (queueId: {req.queueId})",
        f"Required documents (from intake): {req.requiredDocuments}",
    ]
    if checklist:
        parts += ["", "Knowledge Base checklist (authoritative):", checklist]
    if req.documentAnalysis:
        parts += [
            "",
            "Documents already uploaded and analysed (from §3.5 doc-analysis):",
            str(req.documentAnalysis),
        ]
    return "\n".join(parts)


def _to_messages(req: PrevetRequest) -> list[dict]:
    messages = []
    for turn in req.conversationHistory:
        role = turn.get("role")
        if role in ("user", "assistant") and turn.get("content"):
            messages.append({"role": role, "content": [{"text": turn["content"]}]})
    messages.append({"role": "user", "content": [{"text": req.userMessage}]})
    # Converse requires the conversation to start with a user turn.
    if messages and messages[0]["role"] != "user":
        messages.insert(0, {"role": "user", "content": [{"text": "(start)"}]})
    return messages


def prevet(req: PrevetRequest, settings: Settings) -> PrevetResponse:
    checklist = KnowledgeBase(settings).retrieve_checklist(
        req.serviceName, req.queueId
    )
    client = boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
    resp = client.converse(
        modelId=settings.bedrock_chat_model_id,
        system=[{"text": _build_system(req, checklist)}],
        messages=_to_messages(req),
        toolConfig={
            "tools": [_TOOL_SPEC],
            "toolChoice": {"tool": {"name": _TOOL_NAME}},
        },
        inferenceConfig={"maxTokens": 1024, "temperature": 0.2},
    )
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block and block["toolUse"]["name"] == _TOOL_NAME:
            return PrevetResponse(**block["toolUse"]["input"])
    raise RuntimeError("Claude did not return the expected tool call")
