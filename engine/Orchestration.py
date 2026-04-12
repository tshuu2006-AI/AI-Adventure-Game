import asyncio
from engine.StateManager import StateManager, PlayerState, WorldState
from world.Entity import *
from engine.Memory import VectorMemory
from engine.CloudAgents import *
from engine.PromptManager import PromptManager
from engine.LocalAgents import IntentRouter, StateExtractor
import os


class GameOrchestrator:
    """
    Trái tim của Game Engine.
    Quản lý luồng dữ liệu giữa các trạng thái (State), ký ức (Memory), cơ sở dữ liệu (DB)
    và điều phối các Agent (AI) để tạo ra trải nghiệm chơi game liền mạch.
    """

    def __init__(self, db_path, vector_model_path, groq_api_key):
        print("Đang khởi tạo hệ thống...")

        # 1. Khởi tạo các component quản lý cơ sở hạ tầng
        self.db = StateManager(db_path=db_path)
        self.memory = VectorMemory(model_path=vector_model_path)
        self.player_state = PlayerState()
        self.world_state = WorldState()

        # 2. Khởi tạo các Cloud Agent (xử lý logic phức tạp, sáng tạo nội dung)
        self.worldGenerator = WorldGenerateAgent(api_key=groq_api_key)
        self.storyAgent = StoryAgent(api_key=groq_api_key)
        self.NPCAgent = NPCAgent(api_key=groq_api_key)
        self.locationAgent = LocationAgent(api_key=groq_api_key)
        self.summarizeAgent = SummarizeAgent(api_key=groq_api_key)

        # 3. Khởi tạo các Local Agent (xử lý tác vụ phân tích, trích xuất dữ liệu nhanh)
        self.pm = PromptManager('static/prompts.yaml')
        self.router = IntentRouter(model_name="qwen2.5:3b")
        self.extractor = StateExtractor(model_name="qwen2.5:3b")

        # Long-term-memory
        self.context_to_summarize = []
        self.context_to_summarize_length = 5

        #Short-term-memory
        self.contextWindow = []
        self.window_size = 3

        print("Hệ thống sẵn sàng!")


    def _save_memory_pipeline(self, npc: NPC = None, location: Location = None, story=None):
        """
        Pipeline đồng bộ lưu ký ức vào cả SQL (để truy vấn cấu trúc)
        và Vector DB (để tìm kiếm ngữ nghĩa/RAG).
        """

        self.db.add_npc_to_db(NPC, location)
        self.db.add_location_to_db(location)

        # Lưu vào SQLite để tạo ID định danh duy nhất
        memory_id, timestamp = self.db.add_memory_to_db(npc, location, story)

        # Ánh xạ ID chuẩn vào FAISS VectorDB
        self.memory.add_memory_to_vector(memory_id, story)
        print(f"[System] Đã ghi nhớ vào ID {memory_id}: {story}")

    async def _initialize_location(self):
        """
        Phân tích World Bible để sinh ra địa điểm khởi đầu của trò chơi.
        Cập nhật Trạng thái người chơi và lưu địa điểm vào CSDL.
        """
        print("[Engine] Đang kiến tạo khu vực khởi đầu...")

        # 1. Trích xuất bối cảnh từ World Bible
        dyn_lore = self.world_state.dynamic_lore

        # Chuẩn hóa mảng world_type thành chuỗi để đưa vào prompt
        world_type_list = self.world_state.type
        world_type = ", ".join(world_type_list) if isinstance(world_type_list, list) else str(world_type_list)

        # 2. Nạp dữ liệu bối cảnh vào Prompt
        sys_init = self.pm.get_prompt('LocationAgent', 'systemInit')
        user_init = self.pm.get_prompt(
            'LocationAgent', 'userInit',
            world_name=self.world_state.name,
            world_type=world_type,
            theme_and_tone=self.world_state.theme_and_tone,
            world_mission=self.world_state.mission
        )

        # 3. Yêu cầu LLM thiết kế không gian
        location_data = await self.locationAgent.generate_location(
            system_prompt=sys_init,
            user_prompt=user_init
        )

        if not location_data:
            raise ValueError("[Lỗi] LocationAgent không thể sinh ra địa điểm đầu tiên!")

        # 4. Trích xuất thuộc tính cấu thành Location
        loc_name = location_data.get('location_name', 'Điểm khởi đầu')
        desc = location_data.get('description', 'Một nơi hoang vắng.')
        atmosphere = location_data.get('atmosphere', 'Yên tĩnh')

        # 5. Khởi tạo Object Location
        start_location = Location(
            id=f"location_{self.db.num_locations}",
            name=loc_name,
            description=desc,
            state=atmosphere,
        )

        # 6. Ghi nhận địa điểm vào CSDL và cập nhật vị trí người chơi
        self.db.add_location_to_db(start_location)

        self.player_state.currentLocation = start_location

        return

    async def _create_new_world(self, player_idea: str):
        """
        Khởi tạo toàn bộ bối cảnh thế giới (World Bible) từ một ý tưởng ngắn.
        Lưu trạng thái vào WorldState và sao lưu ra file JSON vật lý.
        """
        print("[Engine] Đang kích hoạt World Architect...")

        # 1. Chuẩn bị prompt
        system_prompt = self.pm.get_prompt('WorldGenerateAgent', 'system')
        user_prompt = self.pm.get_prompt('WorldGenerateAgent', 'user', user_input=player_idea)

        # 2. Gọi WorldGenerateAgent tạo JSON cấu trúc thế giới
        world_bible = await self.worldGenerator.generate_bible(
            system_prompt=system_prompt,
            user_prompt=user_prompt
        )

        # 3. Sao lưu cấu trúc thế giới ra thư mục data
        os.makedirs('./data', exist_ok=True)
        bible_path = './data/world_bible.json'
        with open(bible_path, 'w', encoding='utf-8') as f:
            json.dump(world_bible, f, ensure_ascii=False, indent=4)
            print(f"[Engine] Đã lưu Thông tin Thế Giới tại: {bible_path}")

        # 4. Cập nhật các thông số cốt lõ i vào WorldState
        self.world_state.name = world_bible["system_requirements"].get('world_name', 'Vùng đất Vô danh')
        self.world_state.type = world_bible["system_requirements"].get('world_type', 'Normal')
        self.world_state.theme_and_tone = world_bible["system_requirements"].get('theme_and_tone', 'Normal')
        self.world_state.core_conflict = world_bible["system_requirements"].get('core_conflict', 'None')
        self.world_state.mission = world_bible["system_requirements"].get('world_mission', 'Sinh tồn')
        self.world_state.dynamic_lore = world_bible['dynamic_lore']
        self.world_state.dynamic_vocabulary = world_bible['dynamic_vocabulary']

        return

    async def _initialize_story(self):
        """
        Sinh ra đoạn văn Mở đầu game (Prologue) dựa trên bối cảnh và địa điểm xuất phát.
        """
        print("[Game Master đang chuẩn bị chương mở đầu...]")

        # 1. Chuyển đổi từ vựng đặc trưng thành chuỗi để nạp vào hệ thống kể chuyện
        dyn_vocab = self.world_state.dynamic_vocabulary
        vocab_str = ", ".join([f"{k}: {v}" for k, v in dyn_vocab.items()]) if dyn_vocab else "Không có"

        # 2. Chuẩn bị bối cảnh Prologue
        sys_init = self.pm.get_prompt('StoryAgent', 'systemInit')

        user_init = self.pm.get_prompt(
            'StoryAgent', 'userInit',
            world_name=self.world_state.name,
            world_theme=self.world_state.theme_and_tone,
            world_conflict=self.world_state.core_conflict,
            world_mission=self.world_state.mission,
            world_vocabulary=vocab_str,
            location_name=self.player_state.currentLocation.name,
            location_atmosphere=self.player_state.currentLocation.state,
            location_description=self.player_state.currentLocation.description
        )

        prologue_text = ""

        # 3. Stream phản hồi từ StoryAgent để tạo hiệu ứng điện ảnh
        print(f"\n{'=' * 60}")
        print(f"📖 CHƯƠNG MỞ ĐẦU: {self.player_state.currentLocation.name.upper()}")
        print(f"{'=' * 60}\n")

        async for chunk in self.storyAgent.generate_stream(system_prompt=sys_init, user_prompt=user_init):
            print(chunk, end="", flush=True)
            prologue_text += chunk
        print("\n\n" + "-" * 60)

        # 4. Tính năng Tóm tắt và Lưu Ký ức (Tạm thời vô hiệu hóa)
        # # print("[System] Đang đồng bộ hóa ký ức khởi nguyên...")
        # sum_sys = self.pm.get_prompt('SummarizeAgent', 'system')
        # sum_user = self.pm.get_prompt(
        #     'SummarizeAgent', 'user',
        #     current_location=start_location_obj.name,
        #     npc_name="Không có",
        #     user_input="[Người chơi vừa bước vào thế giới này]",
        #     storyteller_response=prologue_text
        # )
        #
        # compressed_memory = await self.summarizeAgent.summarize_chat(sum_sys, sum_user)
        # if compressed_memory:
        #     self._save_memory_pipeline(npc=None, location=start_location_obj, story=compressed_memory)
        #
        # return prologue_text

    async def _summarize_context(self):
        """
        Quản lý Trí nhớ Ngắn hạn (N-Window Context).
        Nếu mảng contextWindow vượt quá giới hạn (window_size), tự động lấy các lượt thoại
        cũ nhất đem nén thành 'scene_summary' để tiết kiệm Token mà không làm đứt gãy cốt truyện.
        """
        # Nếu số lượng câu thoại vẫn an toàn trong giới hạn thì bỏ qua
        if len(self.contextWindow) <= self.window_size:
            return

        print("[System] Trí nhớ ngắn hạn đạt đỉnh, đang tiến hành nén ngữ cảnh (Context Compression)...")

        # Tính số lượng tin nhắn bị dôi dư (VD: có 7 tin, giới hạn 5 -> cần nén 2 tin cũ nhất)
        overflow_count = len(self.contextWindow) - self.window_size

        # Trích xuất các đoạn thoại cũ nhất ra để nén
        old_messages = self.contextWindow[:overflow_count]
        text_to_compress = "\n".join(old_messages)

        # Khởi tạo biến lưu tóm tắt cảnh nếu chưa có
        if not hasattr(self, 'scene_summary'):
            self.scene_summary = ""

        # Tạo Prompt hệ thống để nén (Do đây là tác vụ nội bộ, không cần đưa vào file YAML cho phức tạp)
        sys_compress = "Bạn là hệ thống nén ngữ cảnh của Game Engine. Hãy đọc đoạn hội thoại sau và tóm tắt thành đúng 1-2 câu súc tích nhất, tập trung vào sự kiện cốt lõi đã xảy ra. TRẢ LỜI BẰNG TIẾNG VIỆT."
        user_compress = f"Hội thoại cần nén:\n{text_to_compress}"

        try:
            # Gọi LLM để tóm tắt
            compressed_text = await self.summarizeAgent.summarize_chat(sys_compress, user_compress)

            # Cập nhật và nối tiếp vào bản tóm tắt cảnh hiện tại
            if self.scene_summary:
                self.scene_summary += " " + compressed_text
            else:
                self.scene_summary = compressed_text

        except Exception as e:
            print(f"[System Lỗi nén] Không thể nén ngữ cảnh: {e}")

        # CUỐI CÙNG: Cắt bỏ các tin nhắn cũ đã được nén khỏi mảng, giữ mảng ở đúng kích thước window_size
        self.contextWindow = self.contextWindow[overflow_count:]


    async def _process_game_turn(self, player_input: str):
        """
        Xử lý vòng lặp chính của một lượt tương tác.
        Đẩy hành động người chơi cho StoryAgent để tạo ra phản ứng của thế giới.
        """
        print(f"\n[Bạn]: {player_input}")

        past_context = None

        # Kể diễn biến tiếp theo
        print("\n[đang suy nghĩ...]")

        sys_story = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme=self.world_state.theme_and_tone,
            world_conflict=self.world_state.core_conflict,
            world_vocabulary=self.world_state.dynamic_vocabulary,

            current_location=self.player_state.currentLocation.name,
            npc_name=None,
            npc_personality=None,
            rag_context=None,
            system_directive="The player just acted. Describe the consequences and the reaction of the NPC/environment."
        )

        user_story = self.pm.get_prompt('StoryAgent', 'user', user_input=player_input)

        story_response = ""

        # Stream nội dung trả về để hiển thị tuần tự
        async for chunk in self.storyAgent.generate_stream(sys_story, user_story):
            print(chunk, end="", flush=True)
            story_response += chunk
        print("\n")

        # Tính năng Tóm tắt, Lưu Ký ức & Đề xuất Lựa chọn (Tạm thời vô hiệu hóa)
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
        #     self._save_memory_pipeline(npc=current_npc, location=current_location, story=compressed_memory)
        #
        # # BƯỚC 4: GENERATE CHOICES - Đề xuất 3-4 hành động tiếp theo
        # sys_choice = self.pm.get_prompt('ChoiceAgent', 'system')
        # user_choice = self.pm.get_prompt(
        #     'ChoiceAgent', 'user',
        #     current_location=current_location,
        #     npc_name=current_npc,
        #     recent_story_summary=compressed_memory if compressed_memory else story_response
        # )
        #
        # choices_data = await self.choiceAgent.generate_choices(sys_choice, user_choice)
        #
        # return story_response, choices_data

    async def run(self):
        """Khởi động luồng điều khiển CLI để kiểm thử trò chơi."""
        self.db.reset_database()
        self.db.create_tables()
        print("Hãy nhập ý tưởng thế giới mà bạn muốn xây dựng: ")
        player_idea = input()
        await self._create_new_world(player_idea=player_idea)
        await self._initialize_location()
        await self._initialize_story()

        print("Hãy tạo một lựa chọn")
        player_input = input()
        await self._process_game_turn(player_input)