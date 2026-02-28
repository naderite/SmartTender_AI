from typing import Any

import chromadb


class SemanticStore:
    def __init__(self, persist_dir: str):
        self.client = chromadb.PersistentClient(path=persist_dir)
        self.collection = self.client.get_or_create_collection(
            name="cv_profiles",
            metadata={"hnsw:space": "cosine"},
        )

    def upsert_cv(self, cv_id: int, document: str, metadata: dict[str, Any]) -> None:
        self.collection.upsert(
            ids=[str(cv_id)],
            documents=[document],
            metadatas=[metadata],
        )

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def search(self, query_text: str, limit: int) -> dict[str, Any]:
        if self.count() == 0:
            return {"ids": [[]], "distances": [[]], "metadatas": [[]], "documents": [[]]}
        return self.collection.query(
            query_texts=[query_text],
            n_results=max(1, min(limit, self.count())),
            include=["documents", "distances", "metadatas"],
        )
