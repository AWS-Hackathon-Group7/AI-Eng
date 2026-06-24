"""§3.5 ai-doc-analysis: Textract + Claude over a document already in S3.

INPUT   { "s3Key": "tkt_.../ghana_card.jpg", "expectedDocType": "Ghana Card" }
OUTPUT  { "documentType": "...", "fields": {...}, "isValid": bool, "issues": [] }

The output is consumed by §3.1 pre-vetting. `analyze_document` is a plain
function with no FastAPI/HTTP dependency so it drops straight into the Lambda
handler the Backend invokes.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .bedrock import BedrockClassifier
from .config import Settings
from .textract import TextractService


class DocAnalysisRequest(BaseModel):
    s3Key: str
    expectedDocType: str


class DocAnalysisResponse(BaseModel):
    documentType: str
    fields: dict[str, str] = Field(default_factory=dict)
    isValid: bool
    issues: list[str] = Field(default_factory=list)


def analyze_document(
    s3_key: str,
    expected_doc_type: str,
    settings: Settings,
) -> DocAnalysisResponse:
    text = TextractService(settings).extract_text_from_s3(s3_key)

    # No readable text means OCR found nothing — don't bother Claude.
    if not text.strip():
        return DocAnalysisResponse(
            documentType="unknown",
            fields={},
            isValid=False,
            issues=["No readable text found in the document"],
        )

    result = BedrockClassifier(settings).classify(text, expected_doc_type)
    return DocAnalysisResponse(**result)
