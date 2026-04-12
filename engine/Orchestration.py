import asyncio
from engine.StateManager import  StateManager, PlayerState, WorldState
from world.Entity import *
from engine.Memory import VectorMemory
from engine.CloudAgents import *
from engine.PromptManager import PromptManager
from engine.LocalAgents import IntentRouter, StateExtractor
import os



class GameOrchestrator:
    def __init__(self, db_path, vector_model_path, groq_api_key):
        # 1. Khởi tạo các component
        print("Đang khởi tạo hệ thống...")
        self.db = StateManager(db_path=db_path)
        self.memory = VectorMemory(model_path=vector_model_path)
        self.player_state = PlayerState()
        self.world_state = WorldState()

        #2. Khởi tạo các CloudAgents
        self.worldGenerator = WorldGenerateAgent(api_key = groq_api_key)
        self.storyAgent = StoryAgent(api_key = groq_api_key)
        self.NPCAgent = NPCAgent(api_key = groq_api_key)
        self.locationAgent = LocationAgent(api_key = groq_api_key)
        self.summarizeAgent = SummarizeAgent(api_key = groq_api_key)

        #3. Khởi tạo các LocalAgents
        self.pm = PromptManager('static/prompts.yaml')  # Khởi tạo quản lý Prompt
        self.router = IntentRouter(model_name="qwen2.5:3b")  # Gọi Ollama
        self.extractor = StateExtractor(model_name="qwen2.5:3b")  # Gọi Ollama

        self.contextWindow = []
        self.window_size = 5


        print("Hệ thống sẵn sàng!")

    def _save_memory_pipeline(self, npc: NPC = None, location: Location= None, story = None):
        """
        Pipeline đồng bộ lưu ký ức vào cả SQL và Vector DB
        """


        self.db.add_npc_to_db(NPC, location)
        self.db.add_location_to_db(location)

        # Bước 1: Lưu vào SQLite để lấy ID chuẩn
        memory_id, timestamp = self.db.add_memory_to_db(npc, location, story)

        # Bước 2: Dùng chính ID đó lưu vào FAISS để map 1-1
        self.memory.add_memory_to_vector(memory_id, story)
        print(f"[System] Đã ghi nhớ vào ID {memory_id}: {story}")


    async def init_scene(self, location_name: str, atmosphere: str):
        """Khởi tạo một cảnh chơi mới với 1 NPC"""
        print(f"\n--- BƯỚC VÀO: {location_name} ---")
        # Sinh NPC bằng Groq
        npc_data = await self.storyAgent.generate_npc(location_context=location_name, atmosphere=atmosphere)

        if npc_data:
            npc_name = npc_data.get('name', 'Kẻ vô danh')
            print(f"[{npc_name}] xuất hiện! Nghề nghiệp: {npc_data.get('occupation')}")
            print(f"Mô tả: {npc_data.get('description')}")
            print(f"{npc_name}: {npc_data.get('initial_dialogue')}")

            # Lưu câu thoại đầu tiên vào ký ức
            self._save_memory_pipeline(
                npc_name=npc_name,
                location_name=location_name,
                text=f"{npc_name} xuất hiện và nói: {npc_data.get('initial_dialogue')}"
            )
            return npc_name
        return None

    async def player_interact(self, player_input: str, npc_name: str, location_name: str):
        """
        Luồng RAG hoàn chỉnh khi người chơi tương tác với NPC
        """
        print(f"\n[Bạn]: {player_input}")

        # Bước 1: RETRIEVAL - Tìm kiếm ký ức liên quan
        relevant_mem_ids = self.memory.search(player_input, top_k=3)
        past_context = ""
        if relevant_mem_ids:
            # Lấy text từ metadata của Vector DB (hoặc query ngược lại SQL bằng ID)
            memories = [self.memory.metadata[mid] for mid in relevant_mem_ids]
            past_context = "\n".join(memories)
            print(f"[System] Tìm thấy {len(memories)} ký ức liên quan.")

        # Bước 2: Xây dựng Prompt cho LLM
        prompt = f"""
        Bạn đang đóng vai NPC tên là {npc_name} tại {location_name}.

        KÝ ỨC CŨ LIÊN QUAN (Hãy dùng nếu cần thiết để giữ tính nhất quán):
        {past_context if past_context else "Không có ký ức nào liên quan."}

        Người chơi vừa nói: "{player_input}"
        Hãy trả lời người chơi một cách tự nhiên, đúng vai trò của bạn.
        """

        # Bước 3: GENERATION - Gọi LLM để sinh câu trả lời
        print(f"[{npc_name}]: ", end="", flush=True)
        npc_response = ""
        async for chunk in self.storyAgent.generate_stream(prompt):
            print(chunk, end="", flush=True)
            npc_response += chunk
        print()  # Xuống dòng khi sinh xong

        # Bước 4: UPDATE MEMORY - Lưu lại toàn bộ đoạn hội thoại vừa diễn ra
        interaction_text = f"Người chơi nói: '{player_input}'. {npc_name} trả lời: '{npc_response}'"
        self._save_memory_pipeline(npc_name, location_name, interaction_text)


    async def create_new_world(self, player_idea: str) -> dict:
        """
        Khởi tạo thế giới mới từ ý tưởng người chơi.
        Trả về dictionary chứa World Bible để app.py hiển thị.
        """
        print("[Engine] Đang kích hoạt World Architect...")

        # BƯỚC 1: Lấy prompt từ file YAML
        # (Giả sử self.pm là instance của PromptManager đã load file yaml)
        system_prompt = self.pm.get_prompt('WorldGenerateAgent', 'system')
        user_prompt = self.pm.get_prompt('WorldGenerateAgent', 'user', user_input=player_idea)

        # BƯỚC 2: Gọi Agent chuyên biệt để đúc ra "Kinh thánh thế giới"
        # Truyền đúng 2 chuỗi prompt vào hàm generate_bible (đã thiết lập JSON mode)
        world_bible = await self.worldGenerator.generate_bible(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # BƯỚC 3: Lưu World Bible ra file vật lý (Backup/Debug)
        # Đảm bảo thư mục data/ tồn tại
        os.makedirs('./data', exist_ok=True)
        bible_path = './data/world_bible.json'

        with open(bible_path, 'w', encoding='utf-8') as f:
            json.dump(world_bible, f, ensure_ascii=False, indent=4)
        print(f"[Engine] Đã lưu Kinh Thánh Thế Giới tại: {bible_path}")

        # BƯỚC 4: Cập nhật vào WorldState của Game Engine
        # (Để các Agent khác như Storyteller, NPC Creator lấy ra dùng sau này)
        self.world_state.name = world_bible.get('world_name', 'Vùng đất Vô danh')
        self.world_state.theme = world_bible.get('theme', 'Fantasy')
        self.world_state.tone = world_bible.get('tone_and_style', 'Trang trọng')
        self.world_state.core_conflict = world_bible.get('core_conflict', 'Sinh tồn')

        vocab = world_bible.get('vocabulary_mapping', {})
        self.world_state.currency = vocab.get('currency', 'Vàng')
        self.world_state.tech_magic = vocab.get('magic_or_tech', 'Phép thuật')

        # BƯỚC 5: Khởi tạo cảnh đầu tiên (Bắt buộc phải có để bắt đầu game)
        start_loc = world_bible.get('starting_location', 'Nơi hoang dã')
        start_atmos = world_bible.get('starting_atmosphere', 'Bí ẩn')

        # Đẩy người chơi vào map đầu tiên và sinh NPC khởi đầu
        await self.init_scene(start_loc, start_atmos)

        # Trả về toàn bộ dữ liệu để app.py có thể in ra thông báo cho người chơi
        return world_bible


