import faiss
import numpy as np
import os
from sentence_transformers import SentenceTransformer


class VectorMemory:
    """
    Hệ thống quản lý Ký ức (Vector Database) sử dụng FAISS và SentenceTransformers.
    Phục vụ cho tính năng RAG (Retrieval-Augmented Generation) của Game Engine.
    """

    def __init__(self, model_path: str):
        # Tải mô hình nhúng (embedding model) từ Local
        self.encoder = SentenceTransformer(model_path)
        self.dimension = 384

        # Khởi tạo không gian FAISS có hỗ trợ lưu trữ ID tùy chỉnh (IDMap)
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        self.metadata = {}


    def add_memory_to_vector(self, memory_id: int, text: str):
        """Mã hóa văn bản thành vector và lưu trữ vào FAISS kèm theo ID từ SQL."""
        # Chuyển đổi văn bản thành vector NumPy chuẩn float32
        vector = self.encoder.encode([text]).astype('float32')

        # Lưu vector vào FAISS và ánh xạ với memory_id
        self.index.add_with_ids(vector, np.array([memory_id]).astype('int64'))
        self.metadata[memory_id] = text


    def search(self, query: str, top_k: int = 2):
        """Tìm kiếm top_k ký ức có ngữ nghĩa tương đồng nhất với câu truy vấn."""
        # Bỏ qua nếu database chưa có ký ức nào
        if self.index.ntotal == 0:
            return ""

        # Mã hóa câu hỏi của người chơi thành vector
        query_vector = self.encoder.encode([query]).astype('float32')

        # D: Khoảng cách (độ lệch), I: Danh sách ID trả về
        D, I = self.index.search(query_vector, top_k)

        # Lọc bỏ các ID lỗi (-1) và trả về mảng ID hợp lệ
        return [int(idx) for idx in I[0] if idx != -1]


    def reset_vector_db(self):
        """Xóa trắng FAISS index và metadata, đưa bộ nhớ về trạng thái ban đầu."""
        # Khởi tạo lại Index mới với cùng cấu trúc như hàm __init__
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        self.metadata = {}

        # Xóa file index vật lý nếu có tồn tại trên ổ cứng
        if hasattr(self, 'index_path') and os.path.exists(self.index_path):
            os.remove(self.index_path)

        print("[VectorDB] Đã tẩy trắng Ký ức RAG!")