import faiss
import numpy as np
import os
from typing import List, Optional
from sentence_transformers import SentenceTransformer
from engine.Agents.CloudAgents import SummarizeAgent
from engine.PromptManager import PromptManager

class VectorMemory:
    """
    Hệ thống quản lý Ký ức (Vector Database) sử dụng FAISS và SentenceTransformers.
    Phục vụ cho tính năng RAG (Retrieval-Augmented Generation) của Game Engine.
    """

    def __init__(self, model_path: str):
        # Tải mô hình nhúng (embedding model) từ Local
        self.encoder = SentenceTransformer(model_path)
        self.dimension = 384
        self.num_memory = 0

        # Khởi tạo không gian FAISS có hỗ trợ lưu trữ ID tùy chỉnh (IDMap)
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        self.metadata = {}


    def add_memory_to_vector(self, text: str, memory_id: Optional[int] = None):
        """Mã hóa văn bản thành vector và lưu trữ vào FAISS với ID ổn định."""
        # Chuyển đổi văn bản thành vector NumPy chuẩn float32
        vector = self.encoder.encode([text]).astype('float32')

        # Nếu caller truyền ID từ SQL, dùng trực tiếp để đồng bộ hai hệ.
        # Nếu không, fallback sang bộ đếm nội bộ để tương thích mã cũ.
        vector_id = int(memory_id) if memory_id is not None else int(self.num_memory)

        # Đảm bảo ID đã tồn tại sẽ được cập nhật bằng vector mới.
        self.index.remove_ids(np.array([vector_id]).astype('int64'))

        # Lưu vector vào FAISS và ánh xạ với memory_id
        self.index.add_with_ids(vector, np.array([vector_id]).astype('int64'))
        self.metadata[vector_id] = text

        if memory_id is None:
            self.num_memory += 1


    def search(self, query: str, top_k: int = 3) -> List[int]:
        """Tìm kiếm top_k ký ức có ngữ nghĩa tương đồng nhất với câu truy vấn."""
        # Bỏ qua nếu database chưa có ký ức nào
        if self.index.ntotal == 0:
            return []

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



class ShortTermMemory:

    def __init__(self, groq_api_key, prompt_manager : PromptManager, window_size=3):
        self.window_size = window_size
        self.context_window = []
        self.scene_summary = ""
        self.pm = prompt_manager
        self.summarizeAgent = SummarizeAgent(api_key=groq_api_key)


    def add_memory(self, player_input, ai_response):
        self.context_window.append(f"player: {player_input}\nGameMaster: {ai_response}")


    def summarize(self):
        if len(self.context_window) > self.window_size:
            sys_prompt = self.pm.get_prompt('SummarizeAgent', 'system')
            user_prompt = self.pm.get_prompt('SummarizeAgent', 'user',
                                            context_window = self.context_window)

            summarized_context = self.summarizeAgent.summarize_chat(sys_prompt, user_prompt)
            return summarized_context

        else:
            return None


    def get_memory(self):
        return self.context_window
