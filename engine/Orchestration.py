from sympy.codegen.ast import continue_

from engine.DataManager.StateManager import StateManager, PlayerState, WorldState
from world.Entity import *
from engine.DataManager.MemoryManager import VectorMemory, ShortTermMemory
from engine.Agents.CloudAgents import *
from engine.PromptManager import PromptManager
from engine.Agents.LocalAgents import IntentRouter, StateExtractor

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
        self.pm = PromptManager('static/prompts.yaml')

        self.db = StateManager(db_path=db_path)
        self.long_term_memory = VectorMemory(model_path=vector_model_path)
        self.short_term_memory = ShortTermMemory(groq_api_key, self.pm)
        self.player_state = PlayerState()
        self.world_state = WorldState()

        # 2. Khởi tạo các Cloud Agent (xử lý logic phức tạp, sáng tạo nội dung)
        self.worldGenerator = WorldGenerateAgent(api_key=groq_api_key)
        self.storyAgent = StoryAgent(api_key=groq_api_key)
        self.NPCAgent = NPCAgent(api_key=groq_api_key)
        self.locationAgent = LocationAgent(api_key=groq_api_key)
        self.choiceAgent = ChoiceAgent(api_key=groq_api_key) # Khởi tạo ChoiceAgent

        self.queryAgent = QueryAgent(api_key=groq_api_key) # Mới thêm

        # 3. Khởi tạo các Local Agent (xử lý tác vụ phân tích, trích xuất dữ liệu nhanh)
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
        self.long_term_memory.add_memory_to_vector(story)
        print("[System] Đã ghi nhớ thông tin mới")


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

        # 4. Cập nhật các thông số cốt lõi vào WorldState
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
        async for chunk in self.storyAgent.generate_stream(system_prompt=sys_init, user_prompt=user_init):
            print(chunk, end="", flush=True)
            prologue_text += chunk

        self.short_term_memory.add_memory('Wake up', prologue_text)

        return prologue_text


    async def _summarize_memory(self):
        short_term_memory = await self.short_term_memory.summarize()

        if short_term_memory is None:
            return

        self.long_term_memory.add_memory_to_vector(short_term_memory)


    async def _process_game_turn(self, player_input: str):
        """
        Xử lý vòng lặp chính của một lượt tương tác.
        Đẩy hành động người chơi cho StoryAgent để tạo ra phản ứng của thế giới.
        """
        print(f"\n[Bạn]: {player_input}")

        past_context = self.short_term_memory.get_memory()


        # Tạm thời hardcode, sau này sẽ lấy từ state
        current_npc_name = "Không rõ"

        # 1. Thu thập trí nhớ dài hạn (RAG) thông qua hàm Helper
        rag_context_str = await self._get_rag_context(player_input, current_npc_name)

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
            rag_context=rag_context_str, # Nhét kết quả từ hàm Helper vào đây
            valid_paths_from_sql = None,
            system_directive="The player just acted. Describe the consequences and the reaction of the NPC/environment."
        )

        user_story = self.pm.get_prompt('StoryAgent', 'user', user_input=player_input)

        story_response = ""

        # Stream nội dung trả về để hiển thị tuần tự
        async for chunk in self.storyAgent.generate_stream(sys_story, user_story):
            print(chunk, end="", flush=True)
            story_response += chunk
        print("\n")

        # Lưu vào short-term memory câu vừa tương tác xong
        self.short_term_memory.add_memory(player_input, story_response)

        # Bơm dữ liệu từ trí nhớ ngắn hạn sang trí nhớ dài hạn (FAISS)
        await self._summarize_memory()

        # Cập nhật inventory
        await self._update_inventory(player_input, story_response)

        # Tạo lựa chọn
        choices = await self._generate_choices(story_response)
    
        self._display_choices(choices)

        return story_response



    async def run(self):
        """Khởi động luồng điều khiển CLI để kiểm thử trò chơi."""
        self.db.reset_database()
        self.db.create_tables()
        print("Hãy nhập ý tưởng thế giới mà bạn muốn xây dựng: ")
        player_idea = input()
        await self._create_new_world(player_idea=player_idea)
        await self._initialize_location()

        prologue_text = await self._initialize_story()
        print("\n")
        choices = await self._generate_choices(prologue_text)
        self._display_choices(choices)

        player_input = ""
        # while player_input.lower() != "exit":
        while True:
            player_input = input("\n[Lựa chọn của bạn]: ")

            if player_input.lower() == 'exit':
                break
            story_response = await self._process_game_turn(player_input)
            print()


    async def _generate_choices(self, story_context: str):
        """
        Sinh ra danh sách các lựa chọn hành động cho người chơi.
        story_context: Có thể là story_response vừa tạo hoặc tóm tắt gần nhất.
        """
        print("[Engine] Đang tính toán các lựa chọn tiếp theo...")

        # 1. Lấy thông tin NPC hiện tại (nếu có) từ PlayerState hoặc Memory
        # Tạm thời để None nếu hệ thống chưa lưu NPC active trong scene
        current_npc_name = "Không có"
        
        # 2. Nạp dữ liệu vào Prompt từ prompts.yaml
        sys_prompt = self.pm.get_prompt('ChoiceAgent', 'system')
        user_prompt = self.pm.get_prompt(
            'ChoiceAgent', 'user',
            current_location=self.player_state.currentLocation.name,
            npc_name=current_npc_name,
            recent_story_summary=story_context
        )

        # 3. Gọi Agent để lấy JSON lựa chọn
        choices_data = await self.choiceAgent.generate_choices(sys_prompt, user_prompt)
        
        return choices_data.get('choices', [])

    async def _update_inventory(self, player_input: str, story_response: str):
        """
        Hàm con (Helper) chuyên chịu trách nhiệm đọc hội thoại và cập nhật túi đồ.
        """
        recent_interaction = f"Hành động của người chơi: {player_input}\nPhản hồi của thế giới: {story_response}"
        
        sys_extractor = self.pm.get_prompt('StateExtractor', 'system')
        user_extractor = self.pm.get_prompt('StateExtractor', 'user', conversation_history=recent_interaction)

        # Chạy LocalAgent
        state_changes = await self.extractor.extract_state(sys_extractor, user_extractor)

        items_added = state_changes.get("items_added", [])
        items_removed = state_changes.get("items_removed", [])

        if items_added or items_removed:
            print("\n[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")
            
            if isinstance(items_added, list):
                for item in items_added:
                    if item and item not in self.player_state.inventory:
                        self.player_state.inventory.append(item)
                        print(f" [+] Nhận được: {item}")
            
            if isinstance(items_removed, list):
                for item in items_removed:
                    if item and item in self.player_state.inventory:
                        self.player_state.inventory.remove(item)
                        print(f" [-] Bị mất: {item}")
            
            inventory_status = ", ".join(self.player_state.inventory) if self.player_state.inventory else "Trống rỗng"
            print(f" [Balo hiện tại]: {inventory_status}")

    def _display_choices(self, choices):
        """Hàm con phụ trách in menu lựa chọn ra màn hình."""
        if choices:
            print("-" * 30)
            print("BẠN SẼ LÀM GÌ TIẾP THEO?")
            for choice in choices:
                print(f" {choice['id']}. {choice['action_text']} ({choice['style']})")
            print("-" * 30)



    async def _get_rag_context(self, player_input: str, current_npc_name: str) -> str:
        """
        Hàm con chịu trách nhiệm tổng hợp ngữ cảnh và truy vấn FAISS VectorDB.
        Trả về chuỗi văn bản chứa các sự kiện trong quá khứ.
        """
        past_context = self.short_term_memory.get_memory()
        context_str = "\n".join(past_context) + f"\nplayer: {player_input}"

        print("\n[Hệ thống đang rà soát ký ức...]")

        # 1. Gọi QueryAgent đẻ ra từ khóa tìm kiếm
        sys_query = self.pm.get_prompt('QueryAgent', 'system')
        user_query = self.pm.get_prompt('QueryAgent', 'user',
                                        current_location=self.player_state.currentLocation.name,
                                        npc_name=current_npc_name,
                                        context_window=context_str)

        search_query = await self.queryAgent.generate_query(sys_query, user_query)
        print(f"   [Debug Query]: '{search_query}'")

        # 2. Chọc vào FAISS VectorDB
        rag_context_str = "Không có sự kiện quá khứ nào đáng chú ý."

        if search_query:
            memory_ids = self.long_term_memory.search(search_query, top_k=2)

            if isinstance(memory_ids, list) and len(memory_ids) > 0:
                retrieved_memories = [
                    self.long_term_memory.metadata[idx]
                    for idx in memory_ids
                    if idx in self.long_term_memory.metadata
                ]
                if retrieved_memories:
                    rag_context_str = "\n".join(retrieved_memories)

                    # BẬT X-RAY ĐỂ DEBUG DỮ LIỆU TÌM ĐƯỢC:
                    print(f"   [Debug VectorDB]: {rag_context_str}")

        return rag_context_str