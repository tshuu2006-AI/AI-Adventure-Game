import faiss
import numpy as np
from sentence_transformers import SentenceTransformer

class VectorMemory:
    def __init__(self, model_path: str):
        # Tải model từ đường dẫn cục bộ như Hữu muốn
        self.encoder = SentenceTransformer(model_path)
        self.dimension = 384
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        self.metadata = {}


    def add_memory_to_vector(self, memory_id: int, text: str):
        vector = self.encoder.encode([text]).astype('float32')
        self.index.add_with_ids(vector, np.array([memory_id]).astype('int64'))
        self.metadata[memory_id] = text


    def search(self, query: str, top_k: int = 2):
        if self.index.ntotal == 0:
            return ""

        query_vector = self.encoder.encode([query]).astype('float32')
        D, I = self.index.search(query_vector, top_k)

        return [int(idx) for idx in I[0] if idx != -1]