import math
import re
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from app.core.config import settings

class SemanticCache:
    """
    High-Performance Semantic Vector Cache.
    Matches queries based on semantic cosine similarity (threshold >= 0.96).
    Uses a fast normalized token-embedding representation that can plug into
    Redis VSS, FAISS, or local vector store.
    """
    def __init__(self, threshold: float = settings.SEMANTIC_CACHE_SIMILARITY_THRESHOLD):
        self.threshold = threshold
        # In-memory storage: list of { "prompt": str, "vector": np.ndarray, "response": Dict[str, Any] }
        self.cache_entries: List[Dict[str, Any]] = []

    def _normalize_text(self, text: str) -> str:
        text = text.lower().strip()
        text = re.sub(r'\s+', ' ', text)
        return text

    def _compute_embedding(self, text: str) -> np.ndarray:
        """
        Calculates a fast, deterministic feature vector (hash-projection n-gram embedding).
        In production with Redis VSS, this can be swapped with sentence-transformers or text-embedding-3-small.
        """
        words = re.findall(r'\b\w+\b', self._normalize_text(text))
        dim = 256
        vec = np.zeros(dim, dtype=np.float32)

        if not words:
            return vec

        for idx, word in enumerate(words):
            h = hash(word) % dim
            # Give higher weight to rare/longer informative words
            weight = math.log(len(word) + 2)
            vec[h] += weight

        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec

    def _cosine_similarity(self, vec_a: np.ndarray, vec_b: np.ndarray) -> float:
        dot = np.dot(vec_a, vec_b)
        return float(dot)

    def lookup(self, prompt: str) -> Optional[Tuple[Dict[str, Any], float]]:
        if not settings.SEMANTIC_CACHE_ENABLED or not self.cache_entries:
            return None

        query_vec = self._compute_embedding(prompt)
        best_match = None
        best_score = -1.0

        for entry in self.cache_entries:
            score = self._cosine_similarity(query_vec, entry["vector"])
            if score > best_score:
                best_score = score
                best_match = entry

        if best_match and best_score >= self.threshold:
            return best_match["response"], best_score

        return None

    def store(self, prompt: str, response: Dict[str, Any]) -> None:
        if not settings.SEMANTIC_CACHE_ENABLED:
            return

        query_vec = self._compute_embedding(prompt)
        
        # Prevent unbounded memory growth
        if len(self.cache_entries) >= settings.CACHE_MAX_ENTRIES:
            self.cache_entries.pop(0)

        self.cache_entries.append({
            "prompt": prompt,
            "vector": query_vec,
            "response": response
        })

    def clear(self):
        self.cache_entries.clear()

semantic_cache = SemanticCache()

