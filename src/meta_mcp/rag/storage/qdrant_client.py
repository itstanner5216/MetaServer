# storage/qdrant_client.py
"""
High-level Qdrant client for chunk storage and retrieval.
"""

import logging
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.models import (
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    Range,
    UpdateStatus,
)

logger = logging.getLogger(__name__)


class QdrantStorageClient:
    """High-level Qdrant client for chunk storage and retrieval."""

    def __init__(
        self,
        url: str = "http://localhost:6333",
        api_key: str | None = None,
        collection: str = "chunks_gemini_v1",
        timeout: int = 30,
    ):
        if api_key:
            self.client = QdrantClient(url=url, api_key=api_key, timeout=timeout)
        else:
            self.client = QdrantClient(url=url, timeout=timeout)
        self.collection = collection

    def upsert_chunk(self, chunk_id: str, vector: list[float], payload: dict[str, Any]) -> bool:
        """
        Insert or update a chunk in Qdrant.

        Args:
            chunk_id: Unique identifier for the chunk
            vector: Embedding vector (768-dim for Gemini)
            payload: Metadata to store with the vector

        Returns:
            True if successful
        """
        result = self.client.upsert(
            collection_name=self.collection,
            points=[PointStruct(id=chunk_id, vector=vector, payload=payload)],
            wait=True,  # Wait for indexing
        )

        return result.status == UpdateStatus.COMPLETED

    def upsert_batch(self, points: list[dict[str, Any]], batch_size: int = 100) -> int:
        """
        Batch upsert chunks.

        Args:
            points: List of {"chunk_id": str, "vector": List[float], "payload": Dict}
            batch_size: Number of points per batch

        Returns:
            Number of points successfully upserted
        """
        total = 0

        for i in range(0, len(points), batch_size):
            batch = points[i : i + batch_size]

            point_structs = [
                PointStruct(id=p["chunk_id"], vector=p["vector"], payload=p["payload"])
                for p in batch
            ]

            result = self.client.upsert(
                collection_name=self.collection, points=point_structs, wait=True
            )

            if result.status == UpdateStatus.COMPLETED:
                total += len(batch)

        return total

    def search(
        self,
        vector: list[float],
        scope: str,
        top_k: int = 30,
        filters: dict[str, Any] | None = None,
        score_threshold: float | None = None,
    ) -> list[dict]:
        """
        Semantic search with scope filtering.

        Args:
            vector: Query embedding
            scope: Required scope filter
            top_k: Number of results to return
            filters: Additional filters (path, doc_id, etc.)
            score_threshold: Minimum similarity score

        Returns:
            List of matches with chunk_id, score, and payload
        """
        # Build filter conditions
        filter_conditions = [FieldCondition(key="scope", match=MatchValue(value=scope))]

        if filters:
            for key, value in filters.items():
                if isinstance(value, dict) and "range" in value:
                    # Range filter (e.g., for timestamps)
                    filter_conditions.append(FieldCondition(key=key, range=Range(**value["range"])))
                else:
                    filter_conditions.append(FieldCondition(key=key, match=MatchValue(value=value)))

        # Execute search
        results = self.client.search(
            collection_name=self.collection,
            query_vector=vector,
            query_filter=Filter(must=filter_conditions),
            limit=top_k,
            with_payload=True,
            score_threshold=score_threshold,
        )

        return [{"chunk_id": hit.id, "score": hit.score, "payload": hit.payload} for hit in results]

    def get_chunk(self, chunk_id: str) -> dict | None:
        """Get a single chunk by ID."""
        results = self.client.retrieve(
            collection_name=self.collection, ids=[chunk_id], with_payload=True, with_vectors=False
        )

        if results:
            return {"chunk_id": results[0].id, "payload": results[0].payload}
        return None

    def get_chunks(self, chunk_ids: list[str]) -> list[dict]:
        """Get multiple chunks by ID."""
        results = self.client.retrieve(
            collection_name=self.collection, ids=chunk_ids, with_payload=True, with_vectors=False
        )

        return [{"chunk_id": point.id, "payload": point.payload} for point in results]

    def delete_chunk(self, chunk_id: str) -> bool:
        """Delete a chunk by ID."""
        self.client.delete(collection_name=self.collection, points_selector=[chunk_id])
        return True

    def delete_chunks_by_doc(self, doc_id: str) -> int:
        """Delete all chunks for a document."""
        # Get count first
        count = self.count_points({"doc_id": doc_id})

        if count > 0:
            self.client.delete(
                collection_name=self.collection,
                points_selector=Filter(
                    must=[FieldCondition(key="doc_id", match=MatchValue(value=doc_id))]
                ),
            )

        return count

    def count_points(self, filters: dict[str, Any] | None = None) -> int:
        """Count points matching filters."""
        if filters:
            filter_conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filters.items()
            ]
            result = self.client.count(
                collection_name=self.collection, count_filter=Filter(must=filter_conditions)
            )
        else:
            result = self.client.count(collection_name=self.collection)

        return result.count

    def take_snapshot(self) -> str:
        """
        Create a snapshot of the collection.

        Returns:
            Snapshot filename
        """
        snapshot_info = self.client.create_snapshot(collection_name=self.collection)
        logger.info(f"Created snapshot: {snapshot_info.name}")
        return snapshot_info.name

    def list_snapshots(self) -> list[dict]:
        """List all available snapshots."""
        snapshots = self.client.list_snapshots(collection_name=self.collection)
        return [
            {"name": s.name, "creation_time": s.creation_time, "size": s.size} for s in snapshots
        ]

    def restore_snapshot(self, snapshot_name: str, snapshot_location: str = None) -> bool:
        """
        Restore collection from a snapshot.

        Args:
            snapshot_name: Name of the snapshot
            snapshot_location: Path to snapshot file (if not in default location)

        Returns:
            True if successful
        """
        try:
            if snapshot_location:
                # Restore from file path
                self.client.recover_snapshot(
                    collection_name=self.collection, location=snapshot_location
                )
            else:
                # Restore from Qdrant's snapshot storage
                self.client.recover_snapshot(
                    collection_name=self.collection,
                    location=f"file:///qdrant/snapshots/{self.collection}/{snapshot_name}",
                )
            logger.info(f"Restored snapshot: {snapshot_name}")
            return True
        except Exception as e:
            logger.error(f"Snapshot restore failed: {e}")
            return False

    def get_collection_info(self) -> dict:
        """Get collection statistics and configuration."""
        info = self.client.get_collection(self.collection)

        return {
            "name": self.collection,
            "points_count": info.points_count,
            "vectors_count": info.vectors_count,
            "indexed_vectors_count": info.indexed_vectors_count,
            "status": str(info.status),
            "optimizer_status": str(info.optimizer_status),
            "payload_schema": list(info.payload_schema.keys()) if info.payload_schema else [],
        }

    def health_check(self) -> tuple[bool, str]:
        """Check if Qdrant is healthy."""
        try:
            info = self.get_collection_info()
            if info["status"] == "green":
                return True, f"Healthy: {info['points_count']} points"
            return False, f"Status: {info['status']}"
        except Exception as e:
            return False, f"Connection error: {e}"
