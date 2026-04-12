import asyncio

from UX_AIRPG.main import process_turn
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
        self.world_bible = None


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


    async def _initialize_location(self, world_bible: dict):
        """
        Phân tích World Bible để thiết kế địa điểm bắt đầu game.
        Trả về object Location.
        """
        print("[Engine] Đang kiến tạo khu vực khởi đầu...")

        # 1. Trích xuất dữ liệu từ World Bible một cách an toàn
        sys_req = world_bible.get("system_requirements", {})
        dyn_lore = world_bible.get("dynamic_lore", {})

        world_name = sys_req.get("world_name", "Vùng đất Vô danh")
        world_mission = sys_req.get("world_mission", "Sống sót")
        theme_and_tone = dyn_lore.get("theme_and_tone", "Bí ẩn")

        # world_type là mảng (list), cần nối thành chuỗi để nạp vào prompt
        world_type_list = sys_req.get("world_type", ["Unknown"])
        world_type = ", ".join(world_type_list) if isinstance(world_type_list, list) else str(world_type_list)

        # 2. Lấy prompt Init từ YAML
        sys_init = self.pm.get_prompt('LocationAgent', 'systemInit')
        user_init = self.pm.get_prompt(
            'LocationAgent', 'userInit',
            world_name=world_name,
            world_type=world_type,
            theme_and_tone=theme_and_tone,
            world_mission=world_mission
        )

        # 3. Gọi Agent sinh địa điểm (Sử dụng hàm của CloudAgents)
        location_data = await self.locationAgent.generate_location(
            system_prompt=sys_init,
            user_prompt=user_init
        )

        if not location_data:
            raise ValueError("[Lỗi] LocationAgent không thể sinh ra địa điểm đầu tiên!")

        # 4. Trích xuất thông tin
        loc_name = location_data.get('location_name', 'Điểm khởi đầu')
        desc = location_data.get('description', 'Một nơi hoang vắng.')
        atmosphere = location_data.get('atmosphere', 'Yên tĩnh')
        paths = location_data.get('connected_paths', [])

        # 5. Cập nhật Game State & Tạo Object
        # Giả định bạn đã có class Location trong world.Entity
        start_location = Location(
            id = f"location_{self.db.num_locations}",
            name=loc_name,
            description=desc,
            state=atmosphere,
        )

        # 6. Lưu vào Database (để sau này RAG hoặc Router tìm kiếm)
        self.db.add_location_to_db(start_location)

        self.player_state.currentLocation = start_location

        return


    async def _create_new_world(self, player_idea: str):
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
            print(f"[Engine] Đã lưu Thông tin Thế Giới tại: {bible_path}")

        # BƯỚC 4: Cập nhật vào WorldState của Game Engine
        # (Để các Agent khác như Storyteller, NPC Creator lấy ra dùng sau này)
        self.world_state.name = world_bible["system_requirements"].get('world_name', 'Vùng đất Vô danh')
        self.world_state.type = world_bible["system_requirements"].get('world_type', 'Normal')
        self.world_state.theme_and_tone = world_bible["system_requirements"].get('theme_and_tone', 'Normal')
        self.world_state.core_conflict = world_bible["system_requirements"].get('core_conflict', 'None')
        self.world_state.mission = world_bible["system_requirements"].get('world_mission', 'Sinh tồn')
        self.world_state.dynamic_lore = world_bible['dynamic_lore']
        self.world_state.dynamic_vocabulary = world_bible['dynamic_vocabulary']
        return


    async def _process_game_turn(self, player_input: str):
        """
        Hàm xử lý 1 lượt chơi hoàn chỉnh.
        Trả về: (Cốt truyện sinh ra, Danh sách lựa chọn dạng JSON)
        """
        print(f"\n[Bạn]: {player_input}")

        past_context = None
        # BƯỚC 2: GENERATE STORY - Kể diễn biến tiếp theo
        print("\n[đang suy nghĩ...]")

        sys_story = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme = self.world_state.theme_and_tone,
            world_conflict = self.world_state.core_conflict,
            world_vocabulary = self.world_state.dynamic_vocabulary,

            current_location = self.player_state.currentLocation.name,
            npc_name = None,
            npc_personality = None,
            rag_context = None,
            system_directive = "The player just acted. Describe the consequences and the reaction of the NPC/environment."
        )

        user_story = self.pm.get_prompt('StoryAgent', 'user', user_input=player_input)

        story_response = ""
        # Chạy stream để in chữ ra màn hình từ từ cho mượt
        async for chunk in self.storyAgent.generate_stream(sys_story, user_story):
            print(chunk, end="", flush=True)
            story_response += chunk
        print("\n")  # Xuống dòng khi kể xong
        #
        # # BƯỚC 3: SUMMARIZE & SAVE - Nén và lưu ký ức
        # sum_sys = self.pm.get_prompt('SummarizeAgent', 'system')
        # sum_user = self.pm.get_prompt(
        #     'SummarizeAgent', 'user',
        #     current_location=current_location,
        #     npc_name=current_npc,
        #     user_input=player_input,
        #     storyteller_response=story_response
        # )
        # compressed_memory = await self.summarizeAgent.summarize_chat(sum_sys, sum_user)
        #
        # if compressed_memory:
        #     # Lưu ý: Cần đảm bảo hàm _save_memory_pipeline nhận đúng kiểu dữ liệu
        #     self._save_memory_pipeline(npc=current_npc, location=current_location, story=compressed_memory)
        #
        # # BƯỚC 4: GENERATE CHOICES - Đề xuất 3-4 hành động tiếp theo
        # sys_choice = self.pm.get_prompt('ChoiceAgent', 'system')
        # user_choice = self.pm.get_prompt(
        #     'ChoiceAgent', 'user',
        #     current_location=current_location,
        #     npc_name=current_npc,
        #     # Tận dụng luôn câu tóm tắt ở Bước 3 làm bối cảnh cho ChoiceAgent để tiết kiệm Token!
        #     recent_story_summary=compressed_memory if compressed_memory else story_response
        # )
        #
        # choices_data = await self.choiceAgent.generate_choices(sys_choice, user_choice)
        #
        # return story_response, choices_data



    async def run(self):
        player_idea = input()
        await self._create_new_world(player_idea = player_idea)
        player_input = input()
        await self._process_game_turn(player_input)

