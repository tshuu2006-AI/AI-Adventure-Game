import time
import math
from typing import List
from engine.DataManager.MemoryManager import VectorMemory, ShortTermMemory
from engine.Agents.CloudAgents import QueryAgent
from world.Entity import Memory
from engine.Utils.logger import game_logger  # Thêm import logger


class MemoryProcessor:
    def __init__(self, db, vector_model_path, groq_api_key, pm):
        self.db = db
        self.long_term_memory = VectorMemory(model_path=vector_model_path)
        self.short_term_memory = ShortTermMemory(prompt_manager=pm)
        self.query_agent = QueryAgent(api_key=groq_api_key, pm=pm)
        game_logger.debug("[MemoryProcessor] Đã khởi tạo hệ thống xử lý Ký ức.")

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
            base_score = float(faiss_score)

            # 2. TIME DECAY (Hàm mũ suy giảm)
            time_multiplier = 1.0
            if current_turn is not None and memory.game_turn is not None:
                turns_ago = max(0, current_turn - memory.game_turn)
                time_multiplier = math.exp(-time_decay_rate * turns_ago)

            # 3. HỆ SỐ THƯỞNG NGỮ CẢNH (Context Bonus Multipliers)
            bonus_multiplier = 1.0

            if current_location and memory.location == current_location:
                bonus_multiplier += 0.20

            if current_npc and memory.npc == current_npc:
                bonus_multiplier += 0.30

                # 4. HỆ SỐ THƯỞNG TỪ KHÓA (Keyword Exact Match)
            if keywords:
                for kw in keywords:
                    if kw.strip() and kw.lower() in memory.text.lower():
                        bonus_multiplier += 0.15

                        # 5. TỔNG HỢP FINAL SCORE
            final_score = (base_score * time_multiplier) * bonus_multiplier
            reranked_results.append((memory, final_score))

        # Sắp xếp giảm dần theo final_score
        reranked_results.sort(key=lambda x: x[1], reverse=True)

        return [item[0] for item in reranked_results]

    async def get_hybrid_context(self, player_input: str, player_state, keywords=None, k_candidates: int = 10,
                                 k_memories: int = 3):
        """
        Đóng gói quá trình RAG nâng cao với Scaled Reranking.
        Kết hợp FAISS Score [0,1], Time Decay (hàm mũ) và Context Multipliers.
        """
        start_rag = time.perf_counter()

        # 1. TRÍCH XUẤT NGỮ CẢNH HIỆN TẠI
        past_context = self.short_term_memory.get_memory()
        current_location_name = player_state.currentLocation.name if player_state.currentLocation else "Vùng đất vô danh"
        current_npc_names = [npc.name for npc in player_state.currentNPCs] if player_state.currentNPCs else []

        if keywords is None:
            keywords = [word.strip(",.?!") for word in player_input.split() if len(word) > 3]

        context_str = f"Quá khứ gần: {past_context}\nHành động mới: {player_input}"

        try:
            # 2. TẠO TRUY VẤN TỐI ƯU
            search_query = await self.query_agent.generate_query(
                current_location=current_location_name,
                npc_names=current_npc_names,
                context=context_str
            )
            if not search_query:
                search_query = player_input

            game_logger.debug(f"[MemoryProcessor] Truy vấn RAG đã mở rộng: '{search_query}'")

            # 3. TRUY XUẤT BAN ĐẦU
            memory_ids, faiss_scores = self.long_term_memory.search(query=search_query, top_k=k_candidates)
            memories_raw = await self.db.get_memories_by_ids(memory_ids) if memory_ids else []

            # 4. THỰC HIỆN SCALED RERANKING
            reranked_memories = self._rerank_memories(
                memories=memories_raw,
                faiss_scores=faiss_scores,
                current_turn=player_state.currentTurn,
                current_location=current_location_name,
                current_npc=current_npc_names[0] if current_npc_names else None,
                keywords=keywords
            )

            final_memories = reranked_memories[:k_memories]

            # 5. TRUY XUẤT THỰC THỂ HIỆN TẠI
            locations = await self.db.get_location_by_names([current_location_name])
            npcs = await self.db.get_npc_by_names(current_npc_names)

            # 6. ĐÓNG GÓI RAG CONTEXT
            long_term_context = self.long_term_memory.get_rag_context(
                memory_ids=[m.id for m in final_memories],
                memories=final_memories,
                npc_rows=npcs,
                location_rows=locations
            )

            rag_context = f"[RECENT-Memory]\n{context_str}\n\n{long_term_context}"
            game_logger.debug(f"[Profile] RAG (với Rerank) hoàn tất trong: {time.perf_counter() - start_rag:.3f}s")

        except Exception as e:
            game_logger.error(f"[MemoryProcessor] Lỗi hệ thống RAG: {e}", exc_info=True)
            rag_context = "[Hệ thống RAG đang quá tải]"
            npcs = []

        return rag_context, npcs

    async def save_turn(self, player_input: str, story_response: str, atomic_memories: List[str],
                        current_location_name: str, encountered_npc_names: List[str]):
        """Lưu lại ký ức sau khi Turn kết thúc"""
        self.short_term_memory.add_memory(player_input=player_input, story_response=story_response,
                                          atomic_memories=atomic_memories)

        for atomic_memory in atomic_memories:
            if encountered_npc_names:
                for encountered_npc_name in encountered_npc_names:
                    # GẮN TAG TÊN NPC VÀO CHUỖI ĐỂ FAISS HIỂU
                    tagged_text = f"[Tương tác với {encountered_npc_name}] {atomic_memory}"

                    new_memory = Memory(location=current_location_name, npc=encountered_npc_name,
                                        text=tagged_text, game_turn=self.long_term_memory.game_turn)

                    memory_id = await self.db.add_memory_to_db(new_memory)
                    self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)
            else:
                new_memory = Memory(location=current_location_name, npc=None,
                                    text=atomic_memory, game_turn=self.long_term_memory.game_turn)

                memory_id = await self.db.add_memory_to_db(new_memory)
                self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)

        game_logger.debug(f"[MemoryProcessor] Đã lưu {len(atomic_memories)} ký ức nguyên tử vào CSDL và VectorDB.")
        self.long_term_memory.update_game_turn()