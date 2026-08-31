"""
vector_index.py Flat ChromaDB vector index with no per tenant partitioning.

All documents from all tenants live in a single ChromaDB collection.
RBAC filtering is done *after* retrieval in the pipeline layer, which means:
  * Similarity scores for restricted docs are computed and logged for every
    query regardless of the requester's access rights.
  * After revocation, the vector index still ranks the revoked document
    highly for relevant queries. There is no reindexing step.

This "flat index" design is the second naive vulnerability: it leaks
existence and relevance signals through raw similarity scores.

Public API
    index = VectorIndex(chroma_dir=".chroma", embedder=<SentenceTransformer>)
    index.add_documents(docs)           # list[dict] from corpus_loader
    results = index.query(embedding, top_k=5)
    # returns list of doc id similarity and text tuples
"""

from __future__ import annotations

import chromadb
from sentence_transformers import SentenceTransformer


class VectorIndex:
    """
    Thin wrapper around a ChromaDB persistent collection.

    Parameters
    chroma_dir : str
        Path to the ChromaDB persistence directory.
    embedder : SentenceTransformer
        The shared embedding model instance.  Documents and queries
        are embedded with this model so the cache and the index
        always operate in the same vector space.
    collection_name : str
        ChromaDB collection name (default: "naive_rag_mvp").
    """

    def __init__(
        self,
        chroma_dir: str,
        embedder: SentenceTransformer,
        collection_name: str = "naive_rag_mvp",
    ) -> None:
        self._embedder = embedder
        self._client = chromadb.PersistentClient(path=chroma_dir)
        # cosine distance means distance equals one minus similarity
        self._collection = self._client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    # Indexing

    def add_documents(self, docs: list[dict]) -> None:
        """
        Embed and upsert all documents into the collection.

        Uses upsert so repeated demo runs don't fail on duplicate IDs.
        All docs from all tenants go into the same collection (flat index).
        """
        if not docs:
            return

        texts = [d["text"] for d in docs]
        embeddings = (
            self._embedder.encode(texts, normalize_embeddings=True, show_progress_bar=True)
            .tolist()
        )
        self._collection.upsert(
            ids=[d["doc_id"] for d in docs],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {
                    "tenant_id": d["tenant_id"],
                    "restricted": str(d["restricted"]),   # ChromaDB metadata is str/int/float
                    "title": d.get("title", ""),
                }
                for d in docs
            ],
        )

    # Querying

    def query(
        self,
        embedding: list[float],
        top_k: int = 5,
    ) -> list[tuple[str, float, str]]:
        """
        Retrieve the *top_k* nearest documents for a precomputed embedding.

        Returns
        list of (doc_id, cosine_similarity, document_text)
            Ordered from most to least similar.
            cosine_similarity ranges from zero to one.
        """
        count = self._collection.count()
        if count == 0:
            return []

        n = min(top_k, count)
        results = self._collection.query(
            query_embeddings=[embedding],
            n_results=n,
            include=["documents", "distances", "metadatas"],
        )

        ids       = results["ids"][0]
        distances = results["distances"][0]   # cosine distance ranges from zero to two
        documents = results["documents"][0]

        # ChromaDB uses cosine distance so convert to similarity for readability.
        return [
            (doc_id, max(0.0, 1.0 - dist), text)
            for doc_id, dist, text in zip(ids, distances, documents)
        ]

    # Metadata

    def count(self) -> int:
        """Total number of documents in the index."""
        return self._collection.count()
