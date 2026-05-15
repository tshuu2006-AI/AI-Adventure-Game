# Tệp: engine/Subsystems/MemoryProcessor.py
import time
from typing import List
from engine.DataManager.MemoryManager import VectorMemory, ShortTermMemory
from engine.Agents.CloudAgents import QueryAgent
from world.Entity import Memory


class MemoryProcessor:
    def __init__(self, db, vector_model_path, groq_api_key, pm):
        self.db = db
        self.long_term_memory = VectorMemory(model_path=vector_model_path)
        self.short_term_memory = ShortTermMemory(prompt_manager=pm)
        self.query_agent = QueryAgent(api_key=groq_api_key, pm=pm)

    def _rerank_memories(
            self,
            memories: List[Memory],
            faiss_scores: List[float],
            current_turn: int = None,
            current_location: str = None,
            current_npc: str = None,
            keywords: List[str] = None,
            time_decay_rate: float = 0.05
    ) -> List[Memory]:
        """
        Thuật toán Reranking scale theo hệ số [0, 1] của FAISS.
        Sử dụng Multipliers (Hệ số nhân) và Exponential Decay (Suy giảm mũ).
        """
        if not memories:
            return []

        reranked_results = []

        for memory, faiss_score in zip(memories, faiss_scores):

            # 1. ĐIỂM NỀN TẢNG (Từ 0 đến 1)
            # Giả định faiss_score là Cosine Similarity [0, 1] (Càng gần 1 càng giống)
            base_score = float(faiss_score)

            # 2. TIME DECAY (Hàm mũ suy giảm)
            # Dùng math.exp để điểm giảm dần về 0 một cách mượt mà, không bị âm.
            time_multiplier = 1.0
            if current_turn is not None and memory.game_turn is not None:
                turns_ago = max(0, current_turn - memory.game_turn)
                # Ví dụ: turns_ago = 10, rate = 0.05 => multiplier = e^(-0.5) ≈ 0.60 (Giữ lại 60% giá trị)
                time_multiplier = math.exp(-time_decay_rate * turns_ago)

            # 3. HỆ SỐ THƯỞNG NGỮ CẢNH (Context Bonus Multipliers)
            # Khởi tạo hệ số thưởng gốc là 100% (1.0)
            bonus_multiplier = 1.0

            if current_location and memory.location == current_location:
                bonus_multiplier += 0.20  # Tăng 20% giá trị gốc nếu trùng địa điểm

            if current_npc and memory.npc == current_npc:
                bonus_multiplier += 0.30  # Tăng 30% giá trị gốc nếu trùng NPC

            # 4. HỆ SỐ THƯỞNG TỪ KHÓA (Keyword Exact Match)
            if keywords:
                for kw in keywords:
                    if kw.strip() and kw.lower() in memory.text.lower():
                        bonus_multiplier += 0.15  # Tăng 40% cho MỖI từ khóa khớp chính xác

            # ---------------------------------------------------
            # 5. TỔNG HỢP FINAL SCORE
            # final_score = (Điểm gốc * Tỉ lệ giữ lại do thời gian) * Hệ số thưởng
            # ---------------------------------------------------
            final_score = (base_score * time_multiplier) * bonus_multiplier

            reranked_results.append((memory, final_score))

        # Sắp xếp giảm dần theo final_score
        reranked_results.sort(key=lambda x: x[1], reverse=True)

        return [item[0] for item in reranked_results]


    async def get_hybrid_context(self, player_input: str, player_state, keywords=None, k_candidates: int = 10, k_memories: int  = 3):
        """
        Đóng gói quá trình RAG nâng cao với Scaled Reranking.
        Kết hợp FAISS Score [0,1], Time Decay (hàm mũ) và Context Multipliers.
        """
        start_rag = time.perf_counter()

        # 1. TRÍCH XUẤT NGỮ CẢNH HIỆN TẠI
        past_context = self.short_term_memory.get_memory()
        current_location_name = player_state.currentLocation.name if player_state.currentLocation else "Vùng đất vô danh"
        current_npc_names = [npc.name for npc in player_state.currentNPCs] if player_state.currentNPCs else []

        # Tự động trích xuất keyword nếu không được truyền vào
        if keywords is None:
            keywords = [word.strip(",.?!") for word in player_input.split() if len(word) > 3]

        context_str = f"Quá khứ gần: {past_context}\nHành động mới: {player_input}"

        try:
            # 2. TẠO TRUY VẤN TỐI ƯU (QUERY EXPANSION)
            search_query = await self.query_agent.generate_query(
                current_location=current_location_name,
                npc_names=current_npc_names,
                context=context_str
            )
            if not search_query:
                search_query = player_input

            # 3. TRUY XUẤT BAN ĐẦU (Kéo rộng hơn top_k để có không gian Rerank)
            # Lấy top_k * 2 để tránh việc các ký ức quan trọng bị loại sớm do điểm FAISS thấp hơn một chút
            memory_ids, faiss_scores = self.long_term_memory.search(query=search_query, top_k=k_candidates)
            memories_raw = self.db.get_memories_by_ids(memory_ids) if memory_ids else []

            # 4. THỰC HIỆN SCALED RERANKING
            # Hàm này sử dụng Multipliers thay vì hằng số cộng
            reranked_memories = self._rerank_memories(
                memories=memories_raw,
                faiss_scores=faiss_scores,
                current_turn=player_state.currentTurn,
                current_location=current_location_name,
                current_npc=current_npc_names[0] if current_npc_names else None,
                keywords=keywords
            )

            # Lấy đúng số lượng top_k sau khi đã sắp xếp lại điểm số
            final_memories = reranked_memories[:k_memories]

            # 5. TRUY XUẤT THỰC THỂ HIỆN TẠI (NPC & LOCATION)
            npcs = []
            locations = []

            loc_data = self.db.get_location_by_names(current_location_name)
            if loc_data: locations.append(loc_data)

            if current_npc_names:
                for name in current_npc_names:
                    npc_data = self.db.get_npc_by_name(name)
                    if npc_data: npcs.append(npc_data)

            # 6. ĐÓNG GÓI RAG CONTEXT
            long_term_context = self.long_term_memory.get_rag_context(
                memory_ids=[m.id for m in final_memories],
                memories=final_memories,
                npc_rows=npcs,
                location_rows=locations
            )

            # Nối Trí nhớ ngắn hạn (context_str) lên đầu tiên để LLM dễ đọc nhất
            rag_context = f"[RECENT-Memory]\n{context_str}\n\n{long_term_context}"

        except Exception as e:
            print(f"[CẢNH BÁO RAG] Lỗi hệ thống: {e}")
            rag_context = "[Hệ thống RAG đang quá tải]"
            npcs = []

        print(f"[Profile] RAG (với Rerank) hoàn tất trong: {time.perf_counter() - start_rag:.3f}s")
        return rag_context, npcs


    def save_turn(self, player_input: str, story_response:str, atomic_memories: List[str], current_location_name: str , encountered_npc_name: str):
        """Lưu lại ký ức sau khi Turn kết thúc"""
        self.short_term_memory.add_memory(player_input = player_input, story_response = story_response, atomic_memories = atomic_memories)

        for atomic_memory in atomic_memories:
            new_memory = Memory(location=current_location_name, npc=encountered_npc_name,
                                text=atomic_memory, game_turn = self.long_term_memory.game_turn)

            memory_id = self.db.add_memory_to_db(new_memory)
            self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)

        self.long_term_memory.update_game_turn()


