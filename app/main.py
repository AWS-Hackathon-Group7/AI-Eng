"""FastAPI app exposing a PDF/image -> text endpoint backed by Textract."""

from __future__ import annotations

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from .config import Settings, get_settings
from .doc_analysis import DocAnalysisRequest, DocAnalysisResponse, analyze_document
from .prevetting import PrevetRequest, PrevetResponse, prevet
from .smart_alert import SmartAlertRequest, SmartAlertResponse, smart_alert
from .textract import TextractError, TextractService

app = FastAPI(title="QueueSmart Document Reader")

# Textract async detection accepts PDFs and single images.
ALLOWED_TYPES = {
    "application/pdf",
    "image/png",
    "image/jpeg",
    "image/tiff",
}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB — Textract's hard limit for S3 objects via API.


class ExtractResponse(BaseModel):
    filename: str
    text: str
    char_count: int


def get_textract(settings: Settings = Depends(get_settings)) -> TextractService:
    return TextractService(settings)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/extract", response_model=ExtractResponse)
async def extract(
    file: UploadFile = File(...),
    textract: TextractService = Depends(get_textract),
) -> ExtractResponse:
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported type {file.content_type!r}. "
            f"Allowed: {sorted(ALLOWED_TYPES)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit")

    try:
        text = textract.extract_text(
            data, file.filename or "document", file.content_type
        )
    except TextractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ExtractResponse(
        filename=file.filename or "document",
        text=text,
        char_count=len(text),
    )


@app.post("/doc-analysis", response_model=DocAnalysisResponse)
def doc_analysis(
    req: DocAnalysisRequest,
    settings: Settings = Depends(get_settings),
) -> DocAnalysisResponse:
    """§3.5 contract: Textract + Claude over a document already in S3."""
    try:
        return analyze_document(req.s3Key, req.expectedDocType, settings)
    except TextractError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/prevetting", response_model=PrevetResponse)
def prevetting(
    req: PrevetRequest,
    settings: Settings = Depends(get_settings),
) -> PrevetResponse:
    """§3.1 contract: grounded conversational document pre-vetting."""
    return prevet(req, settings)


@app.post("/smart-alert", response_model=SmartAlertResponse)
def smart_alert_endpoint(
    req: SmartAlertRequest,
    settings: Settings = Depends(get_settings),
) -> SmartAlertResponse:
    """§3.2 contract: live-traffic "leave now" alert."""
    return smart_alert(req, settings)
