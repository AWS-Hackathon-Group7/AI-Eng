"""Document classification via Bedrock Claude.

Given the raw text Textract pulled from a document and the document type we
expect, ask Claude to identify the document, pull key fields, and judge whether
it matches and looks complete. We force a tool call so the model returns
structured JSON instead of prose we'd have to parse.
"""

from __future__ import annotations

import boto3

from .config import Settings

_TOOL_NAME = "record_document_analysis"

_TOOL_SPEC = {
    "toolSpec": {
        "name": _TOOL_NAME,
        "description": "Record the structured analysis of a scanned document.",
        "inputSchema": {
            "json": {
                "type": "object",
                "properties": {
                    "documentType": {
                        "type": "string",
                        "description": "The actual document type identified from the text.",
                    },
                    "fields": {
                        "type": "object",
                        "description": "Key fields read from the document (e.g. name, idNumber).",
                        "additionalProperties": {"type": "string"},
                    },
                    "isValid": {
                        "type": "boolean",
                        "description": "True if the document matches expectedDocType and looks complete.",
                    },
                    "issues": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Problems found (wrong type, missing fields, illegible, expired).",
                    },
                },
                "required": ["documentType", "fields", "isValid", "issues"],
            }
        },
    }
}

_SYSTEM = (
    "You verify uploaded identity and application documents for a government "
    "service queue. You are given OCR text extracted from one document and the "
    "document type the customer was asked to provide. Identify the real document "
    "type, extract the important fields, and decide whether it matches the "
    "expected type and looks complete and legible. Be strict but fair: if the "
    "OCR text clearly is a different document, mark isValid false and say so in "
    "issues. Always call the tool."
)


class BedrockClassifier:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = boto3.client(
            "bedrock-runtime", region_name=settings.bedrock_region
        )

    def classify(self, text: str, expected_doc_type: str) -> dict:
        prompt = (
            f"Expected document type: {expected_doc_type}\n\n"
            f"OCR text from the uploaded document:\n---\n{text}\n---"
        )
        resp = self._client.converse(
            modelId=self._settings.bedrock_model_id,
            system=[{"text": _SYSTEM}],
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            toolConfig={
                "tools": [_TOOL_SPEC],
                "toolChoice": {"tool": {"name": _TOOL_NAME}},
            },
            inferenceConfig={"maxTokens": 1024, "temperature": 0},
        )
        return _extract_tool_input(resp)


def _extract_tool_input(resp: dict) -> dict:
    for block in resp["output"]["message"]["content"]:
        if "toolUse" in block and block["toolUse"]["name"] == _TOOL_NAME:
            return block["toolUse"]["input"]
    raise RuntimeError("Claude did not return the expected tool call")
