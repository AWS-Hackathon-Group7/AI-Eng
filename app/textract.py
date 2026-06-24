"""Async Textract text extraction over S3.

Flow for multi-page PDFs:
  1. Upload the document to S3 (Textract async reads from S3, not bytes).
  2. StartDocumentTextDetection -> JobId.
  3. Poll GetDocumentTextDetection until SUCCEEDED, paging through results.
  4. Stitch LINE blocks back into raw text.
"""

from __future__ import annotations

import time
import uuid

import boto3
from botocore.exceptions import ClientError

from .config import Settings


class TextractError(RuntimeError):
    """Raised when a Textract job fails or times out."""


class TextractService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._s3 = boto3.client("s3", region_name=settings.aws_region)
        self._textract = boto3.client("textract", region_name=settings.aws_region)

    def extract_text(self, data: bytes, filename: str, content_type: str) -> str:
        """Upload `data` to S3, run async detection, return the raw text.

        Used by the standalone upload endpoint — we own the object, so we
        delete it afterwards.
        """
        key = self._upload(data, filename, content_type)
        try:
            return self._detect_text(key)
        finally:
            # Best-effort cleanup so the bucket doesn't accumulate uploads.
            self._delete(key)

    def extract_text_from_s3(self, s3_key: str) -> str:
        """Run async detection on an object that already lives in the bucket.

        Used by the §3.5 ai-doc-analysis contract, where Backend has already
        uploaded the file and owns its lifecycle — we neither upload nor delete.
        """
        return self._detect_text(s3_key)

    def _detect_text(self, key: str) -> str:
        job_id = self._start_job(key)
        blocks = self._wait_for_blocks(job_id)
        return _blocks_to_text(blocks)

    # --- internals -------------------------------------------------------

    def _upload(self, data: bytes, filename: str, content_type: str) -> str:
        key = f"{self._settings.s3_prefix}{uuid.uuid4().hex}-{filename}"
        self._s3.put_object(
            Bucket=self._settings.textract_bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )
        return key

    def _delete(self, key: str) -> None:
        try:
            self._s3.delete_object(Bucket=self._settings.textract_bucket, Key=key)
        except ClientError:
            pass

    def _start_job(self, key: str) -> str:
        resp = self._textract.start_document_text_detection(
            DocumentLocation={
                "S3Object": {
                    "Bucket": self._settings.textract_bucket,
                    "Name": key,
                }
            }
        )
        return resp["JobId"]

    def _wait_for_blocks(self, job_id: str) -> list[dict]:
        deadline = time.monotonic() + self._settings.poll_timeout_seconds
        while True:
            resp = self._textract.get_document_text_detection(JobId=job_id)
            status = resp["JobStatus"]
            if status == "SUCCEEDED":
                return self._collect_pages(job_id, resp)
            if status == "FAILED":
                raise TextractError(
                    resp.get("StatusMessage", "Textract job failed")
                )
            if time.monotonic() > deadline:
                raise TextractError("Textract job timed out")
            time.sleep(self._settings.poll_interval_seconds)

    def _collect_pages(self, job_id: str, first: dict) -> list[dict]:
        blocks = list(first.get("Blocks", []))
        next_token = first.get("NextToken")
        while next_token:
            resp = self._textract.get_document_text_detection(
                JobId=job_id, NextToken=next_token
            )
            blocks.extend(resp.get("Blocks", []))
            next_token = resp.get("NextToken")
        return blocks


def _blocks_to_text(blocks: list[dict]) -> str:
    """Join LINE blocks in document order into newline-separated text."""
    return "\n".join(
        b["Text"] for b in blocks if b.get("BlockType") == "LINE" and b.get("Text")
    )
