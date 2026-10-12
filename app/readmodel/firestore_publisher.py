"""Versioned writes to the Firestore read model.

A document is only written if the incoming `version` is greater than the stored one, inside a
Firestore transaction. Publishing is therefore idempotent and safe against out-of-order delivery:
a late, older publish never overwrites a newer document.
"""

import os
from typing import Any, Protocol

from google.cloud import firestore
from google.cloud.firestore import AsyncClient, AsyncDocumentReference, AsyncTransaction

from app.config import Settings


class Publisher(Protocol):
    async def publish(
        self, aggregate_type: str, aggregate_id: str, payload: dict[str, Any]
    ) -> bool:
        """Write the document. Returns False when skipped because a newer version is stored."""
        ...


def document_path(aggregate_type: str, aggregate_id: str, payload: dict[str, Any]) -> str:
    if aggregate_type == "tournament":
        return f"tournaments/{aggregate_id}"
    if aggregate_type == "match":
        return f"tournaments/{payload['tournamentId']}/matches/{aggregate_id}"
    raise ValueError(f"Unknown aggregate type: {aggregate_type}")


@firestore.async_transactional
async def _write_if_newer(
    transaction: AsyncTransaction, ref: AsyncDocumentReference, payload: dict[str, Any]
) -> bool:
    snapshot = await ref.get(transaction=transaction)
    if snapshot.exists:
        stored = snapshot.to_dict() or {}
        if int(stored.get("version", 0)) >= int(payload["version"]):
            return False
    transaction.set(ref, {**payload, "updatedAt": firestore.SERVER_TIMESTAMP})
    return True


class FirestorePublisher:
    def __init__(self, client: AsyncClient) -> None:
        self._client = client

    async def publish(
        self, aggregate_type: str, aggregate_id: str, payload: dict[str, Any]
    ) -> bool:
        ref = self._client.document(document_path(aggregate_type, aggregate_id, payload))
        written: bool = await _write_if_newer(self._client.transaction(), ref, payload)
        return written

    def close(self) -> None:
        self._client.close()  # type: ignore[no-untyped-call]  # unannotated in the library


def create_firestore_client(settings: Settings) -> AsyncClient:
    if settings.firestore_emulator_host:
        # The Google client reads the emulator address from the process environment only.
        os.environ["FIRESTORE_EMULATOR_HOST"] = settings.firestore_emulator_host
    return AsyncClient(project=settings.gcp_project_id)
