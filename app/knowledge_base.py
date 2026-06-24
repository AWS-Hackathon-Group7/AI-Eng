"""Retrieval against the Bedrock Knowledge Base (§4).

Pulls the relevant per-service document checklist so pre-vetting is grounded in
the authored rules rather than the model's memory.
"""

from __future__ import annotations

import boto3

from .config import Settings


class KnowledgeBase:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._client = boto3.client(
            "bedrock-agent-runtime", region_name=settings.bedrock_region
        )

    def retrieve_checklist(self, service_name: str, queue_id: str) -> str:
        """Return concatenated checklist passages relevant to the service.

        Empty string if nothing relevant is indexed yet — callers should fall
        back to the requiredDocuments passed in the request.
        """
        query = f"{service_name} ({queue_id}) required documents and validity rules"
        resp = self._client.retrieve(
            knowledgeBaseId=self._settings.knowledge_base_id,
            retrievalQuery={"text": query},
            retrievalConfiguration={
                "vectorSearchConfiguration": {
                    "numberOfResults": self._settings.kb_num_results
                }
            },
        )
        passages = [
            r["content"]["text"].strip()
            for r in resp.get("retrievalResults", [])
            if r.get("content", {}).get("text")
        ]
        return "\n\n---\n\n".join(passages)
