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
        Phiên bản RAG Lai Mới: Kết hợp Lịch sử Cá nhân (SQLite Link) và Lịch sử Môi trường (FAISS Reranked).
        Đảm bảo không trùng lặp và tiết kiệm chi phí gọi mô hình.
        """
        start_rag = time.perf_counter()

        # 1. TRÍCH XUẤT NGỮ CẢNH HIỆN TẠI
        past_context = self.short_term_memory.get_memory()
        current_location_name = player_state.currentLocation.name if player_state.currentLocation else "Vùng đất vô danh"
        current_npc_ids = [npc.id for npc in player_state.currentNPCs] if player_state.currentNPCs else []
        current_npc_names = [npc.name for npc in player_state.currentNPCs] if player_state.currentNPCs else []

        if keywords is None:
            keywords = [word.strip(",.?!") for word in player_input.split() if len(word) > 3]

        context_str = f"Quá khứ gần: {past_context}\nHành động mới: {player_input}"

        # Biến hứng dữ liệu NPC để trả về
        npcs = []
        try:
            # --- LUỒNG 1: LẤY LỊCH SỬ CÁ NHÂN (SQLITE) - ƯU TIÊN CAO ---
            npc_history_blocks = []
            # Tập hợp lưu trữ ID ký ức đã lấy từ SQLite để khử trùng lặp ở FAISS
            personal_memory_ids = set()

            if current_npc_names:
                # Lấy dữ liệu Profile của NPC (để Đạo diễn biết tính cách, máu me)
                npcs = await self.db.get_npc_by_names(current_npc_names)

                # Lặp qua từng NPC đang đứng trước mặt người chơi
                for npc_name in current_npc_names:
                    # Lấy 3 ký ức gần nhất liên quan TRỰC TIẾP đến NPC này (nhờ bảng NPC_Memory_Link)
                    recent_mems = await self.db.get_recent_memories_by_npc(npc_name, limit=3)

                    if recent_mems:
                        history_text_lines = []
                        for mem in recent_mems:
                            # mem: (id, text, game_turn)
                            history_text_lines.append(f"- Turn {mem['game_turn']}: {mem['text']}")
                            personal_memory_ids.add(mem['id'])  # Đưa ID vào danh sách cấm

                        npc_history_blocks.append(f"Lịch sử với {npc_name}:\n" + "\n".join(history_text_lines))

            # Đóng gói Lịch sử NPC
            npc_structured_context = "\n".join(
                npc_history_blocks) if npc_history_blocks else "Không có Lịch sử đặc biệt với NPC nào."

            # --- LUỒNG 2: LẤY KÝ ỨC MÔI TRƯỜNG (FAISS) - KÉM ƯU TIÊN ---
            # Chỉ sinh Query và gọi FAISS để tìm các sự kiện ngẫu nhiên, sự kiện ở map này trong quá khứ...
            search_query = await self.query_agent.generate_query(
                current_location=current_location_name,
                npc_names=current_npc_names,
                context=context_str
            )
            if not search_query:
                search_query = player_input

            game_logger.debug(f"[MemoryProcessor] Truy vấn FAISS: '{search_query}'")

            # Gọi FAISS lấy các Candidates
            memory_ids, faiss_scores = self.long_term_memory.search(query=search_query, top_k=k_candidates)

            # --- KHỬ TRÙNG LẶP (DEDUPLICATION) TRƯỚC KHI RERANK ---
            unique_memory_ids = []
            unique_faiss_scores = []
            for m_id, m_score in zip(memory_ids, faiss_scores):
                # Nếu ID này chưa nằm trong Lịch sử Cá nhân (personal_memory_ids), thì cho vào
                if m_id not in personal_memory_ids:
                    unique_memory_ids.append(m_id)
                    unique_faiss_scores.append(m_score)
                else:
                    game_logger.debug(f"[Deduplication] Bỏ qua ký ức #{m_id} từ FAISS vì đã có trong Lịch sử NPC.")

            # Kéo nội dung từ DB lên cho những ID còn sót lại
            memories_raw = await self.db.get_memories_by_ids(unique_memory_ids) if unique_memory_ids else []

            # Thực hiện Rerank (Hàm cũ của bạn, không thay đổi)
            reranked_memories = []
            if memories_raw:
                reranked_memories = self._rerank_memories(
                    memories=memories_raw,
                    faiss_scores=unique_faiss_scores,
                    current_turn=player_state.currentTurn,
                    current_location=current_location_name,
                    current_npc=current_npc_names[0] if current_npc_names else None,
                    keywords=keywords
                )

            final_memories = reranked_memories[:k_memories]

            # Gói các ký ức Môi trường thành chuỗi
            faiss_context_lines = [f"- (Turn {m.game_turn} tại {m.location}): {m.text}" for m in final_memories]
            faiss_structured_context = "\n".join(
                faiss_context_lines) if faiss_context_lines else "Không có sự kiện quá khứ nào liên quan."

            # --- LUỒNG 3: TRUY XUẤT ĐỊA ĐIỂM ---
            locations = await self.db.get_location_by_names([current_location_name])
            location_desc = locations[0].description if locations else ""

            # --- 4. GỘP TOÀN BỘ NGỮ CẢNH ---
            rag_context = (
                f"[BỐI CẢNH HIỆN TẠI]\n"
                f"- Địa điểm: {current_location_name} - {location_desc}\n"
                f"- Quá khứ gần: {past_context}\n"
                f"- Player đang làm: {player_input}\n\n"
                f"[LỊCH SỬ CÁ NHÂN VỚI NPC]\n"
                f"{npc_structured_context}\n\n"
                f"[CÁC KÝ ỨC MÔI TRƯỜNG KHÁC (TỪ FAISS)]\n"
                f"{faiss_structured_context}"
            )

            game_logger.debug(f"[Profile] RAG (Hybrid DB+FAISS) hoàn tất trong: {time.perf_counter() - start_rag:.3f}s")

        except Exception as e:
            game_logger.error(f"[MemoryProcessor] Lỗi hệ thống RAG Lai: {e}", exc_info=True)
            rag_context = "[Hệ thống RAG đang quá tải]"
            npcs = []

        return rag_context, npcs

    async def save_turn(self, player_input: str, story_response: str, episode_data: dict,
                        current_location_name: str, encountered_npc_names: List[str]):
        """Lưu lại ký ức sau khi Turn kết thúc dưới dạng Khối Tập Phim (Episode)"""

        # 1. GHÉP CHUỖI CÓ CẤU TRÚC TỪ DICT (JSON)
        if not episode_data or "action" not in episode_data:
            structured_text = f"Hành động: {player_input} | Kết quả: {story_response[:50]}..."
        else:
            structured_text = (
                f"[Ngữ cảnh]: {episode_data.get('context', '')} | "
                f"[Hành động]: {episode_data.get('action', '')} | "
                f"[Kết quả]: {episode_data.get('result', '')} | "
                f"[Cảm xúc]: {episode_data.get('emotion', '')}"
            )

        self.short_term_memory.add_memory(player_input=player_input, story_response=story_response,
                                          structured_memory=structured_text)

        # 2. LƯU VÀO SQLITE & FAISS (Chỉ lưu 1 khối duy nhất, không dùng vòng lặp)
        if encountered_npc_names:
            # Gắn tag tên tất cả NPC vào đầu để FAISS dễ nhận diện
            tagged_text = f"[Tương tác với {', '.join(encountered_npc_names)}] {structured_text}"
            new_memory = Memory(location=current_location_name, text=tagged_text,
                                game_turn=self.long_term_memory.game_turn)

            memory_id = await self.db.add_memory_to_db(new_memory)
            self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)

            # LINK KHỐI KÝ ỨC VỚI TỪNG NPC
            for npc_name in encountered_npc_names:
                await self.db.link_memory_to_npc(npc_name, memory_id)
        else:
            new_memory = Memory(location=current_location_name, text=structured_text,
                                game_turn=self.long_term_memory.game_turn)

            memory_id = await self.db.add_memory_to_db(new_memory)
            self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)

        game_logger.debug(f"[MemoryProcessor] Đã lưu 1 Episode Ký ức vào CSDL và VectorDB.")
        self.long_term_memory.update_game_turn()