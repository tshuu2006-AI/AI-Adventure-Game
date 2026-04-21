import faiss
import numpy as np
import os
from typing import List, Optional
import pickle
from sentence_transformers import SentenceTransformer
from engine.Agents.CloudAgents import SummarizeAgent
from engine.PromptManager import PromptManager

class VectorMemory:
    """
    Hệ thống quản lý Ký ức (Vector Database) sử dụng FAISS và SentenceTransformers.
    Phục vụ cho tính năng RAG (Retrieval-Augmented Generation) của Game Engine.
    """

    def __init__(self, model_path: str, db_dir = './data/'):
        # Tải mô hình nhúng (embedding model) từ Local
        self.encoder = SentenceTransformer(model_path)
        self.dimension = self.encoder.get_sentence_embedding_dimension()
        self.num_memory = 0


        # Đường dẫn lưu trữ vật lý
        self.index_path = os.path.join(db_dir, 'vector_index.bin')
        self.meta_path = os.path.join(db_dir, 'vector_meta.pkl')

        # Khởi tạo không gian FAISS có hỗ trợ lưu trữ ID tùy chỉnh (IDMap)
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))
        self.metadata = {}

        # KHÔI PHỤC DỮ LIỆU TỪ Ổ CỨNG LÊN (Nếu có)
        self._load_db()

    def reset_vector_db(self):
        """Xóa trắng FAISS index, metadata và reset bộ đếm, đưa bộ nhớ về trạng thái ban đầu."""
        # 1. Khởi tạo lại Index mới với cùng số chiều (dimension) ban đầu
        self.index = faiss.IndexIDMap(faiss.IndexFlatL2(self.dimension))

        # 2. Xóa sạch metadata và reset bộ đếm ID
        self.metadata = {}
        self.num_memory = 0  # Quan trọng: để ID bắt đầu lại từ 0

        # 3. Xóa các file vật lý trên ổ cứng để tránh nạp lại dữ liệu cũ khi khởi động lại
        if os.path.exists(self.index_path):
            os.remove(self.index_path)
        if os.path.exists(self.meta_path):
            os.remove(self.meta_path)

        print("[VectorDB] Đã tẩy trắng toàn bộ Ký ức RAG và file vật lý!")



    def get_rag_context(self, memory_ids, memories, npc_rows, location_rows) -> str:
        # Chuẩn hóa RAG context thành 3 khối để prompt dễ đọc và dễ kiểm tra log.
        memory_block = "\n".join(
            [f"- [memory:{item.id}] ({item.location}) {item.text}" for item in memories]
        ) if memories else "- Không có ký ức liên quan."

        npc_block = "\n".join(
            [
                f"- [npc:{item.id}] {item.name} | personality: {item.personality} | status: {item.status} | location: {item.location}"
                for item in npc_rows]
        ) if npc_rows else "- Không có NPC liên quan."

        location_block = "\n".join(
            [f"- [location:{item.id}] {item.name} | state: {item.state} | desc: {item.description}"
             for item in location_rows]
        ) if location_rows else "- Không có Location liên quan."

        rag_context = (
                "[MEMORY RETRIEVAL]\n" + memory_block +
                "\n\n[NPC RETRIEVAL]\n" + npc_block +
                "\n\n[LOCATION RETRIEVAL]\n" + location_block
        )

        if memory_ids:
            print(f"[RAG] Top memory IDs: {memory_ids}")
        if npc_rows:
            print(f"[RAG] NPC IDs: {[item.id for item in npc_rows]}")
        if location_rows:
            print(f"[RAG] Location IDs: {[item.id for item in location_rows]}")

        return rag_context


    def _load_db(self):
        """Đọc vector và metadata từ ổ cứng khi bật game."""
        if os.path.exists(self.index_path) and os.path.exists(self.meta_path):
            self.index = faiss.read_index(self.index_path)
            with open(self.meta_path, 'rb') as f:
                self.metadata = pickle.load(f)
            print(f"[VectorDB] Khôi phục thành công {self.index.ntotal} ký ức.")


    def _save_db(self):
        """Lưu vector và metadata xuống ổ cứng."""
        faiss.write_index(self.index, self.index_path)
        with open(self.meta_path, 'wb') as f:
            pickle.dump(self.metadata, f)


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

        self._save_db()


    def search(self, query: str, top_k: int = 3) -> List[int]:
        """Tìm kiếm top_k ký ức có ngữ nghĩa tương đồng nhất với câu truy vấn."""
        # Bỏ qua nếu database chưa có ký ức nào
        if self.index.ntotal == 0:
            return []

        # Mã hóa câu hỏi của người chơi thành vector
        query_vector = self.encoder.encode([query]).astype('float32')

        # d: Khoảng cách (độ lệch), i: Danh sách ID trả về
        d, i = self.index.search(query_vector, top_k)

        # Lọc bỏ các ID lỗi (-1) và trả về mảng ID hợp lệ
        return [int(idx) for idx in i[0] if idx != -1]


class ShortTermMemory:

    def __init__(self, groq_api_key, prompt_manager : PromptManager, window_size=3):
        self.window_size = window_size
        self.context_window = []
        self.scene_summary = ""
        self.pm = prompt_manager
        self.summarizeAgent = SummarizeAgent(api_key=groq_api_key, pm=self.pm)


    def add_memory(self, player_input, ai_response):
        self.context_window.append(f"player: {player_input}\nGameMaster: {ai_response}")


    async def summarize(self):
        if len(self.context_window) > self.window_size:
            try:
                # 1. Gọi API TRƯỚC
                summarized_context = await self.summarizeAgent.summarize_chat(self.context_window)

                # 2. Thành công rồi mới XÓA và CẬP NHẬT
                self.scene_summary = summarized_context
                # Giữ lại câu cuối cùng để làm cầu nối mượt mà cho LLM
                self.context_window = [self.context_window[-1]]

                return summarized_context
            except Exception as e:
                print(f"[Cảnh báo] Lỗi khi tóm tắt trí nhớ: {e}")
                # Nếu lỗi, không xóa gì cả, để lượt sau thử tóm tắt lại
                return None
        return None


    def get_memory(self):
        context = []
        if self.scene_summary:
            context.append(f"[Tóm tắt diễn biến trước]: {self.scene_summary}")
        context.extend(self.context_window)
        return context
