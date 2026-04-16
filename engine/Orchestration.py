from engine.DataManager.StateManager import DatabaseManager, PlayerState, WorldState
from engine.DataManager.MemoryManager import VectorMemory, ShortTermMemory
from engine.Agents.CloudAgents import *
from engine.PromptManager import PromptManager
from engine.Agents.LocalAgents import IntentRouter, StateExtractor
from engine.ImageAPI import ImageAPI
from engine.DataManager.ImageManager import ImageManager

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

        self.db = DatabaseManager(db_path=db_path)
        self.long_term_memory = VectorMemory(model_path=vector_model_path)
        self.short_term_memory = ShortTermMemory(groq_api_key, self.pm)
        self.player_state = PlayerState()
        self.world_state = WorldState()

        # 2. Khởi tạo các Cloud Agent (xử lý logic phức tạp, sáng tạo nội dung)
        self.worldGenerator = WorldGenerateAgent(api_key=groq_api_key, pm=self.pm)
        self.storyAgent = StoryAgent(api_key=groq_api_key, pm=self.pm)
        self.NPCAgent = NPCAgent(api_key=groq_api_key, pm=self.pm)
        self.locationAgent = LocationAgent(api_key=groq_api_key, pm=self.pm)
        self.choiceAgent = ChoiceAgent(api_key=groq_api_key, pm=self.pm) # Khởi tạo ChoiceAgent

        self.queryAgent = QueryAgent(api_key=groq_api_key, pm=self.pm) # Mới thêm

        self.image_api = ImageAPI(base_url="https://unspelt-nonbrutally-eleanore.ngrok-free.dev") # Cập nhật link ngrok
        self.image_manager = ImageManager(api=self.image_api)

        # 3. Khởi tạo các Local Agent (xử lý tác vụ phân tích, trích xuất dữ liệu nhanh)
        self.router = IntentRouter(model_name="qwen2.5:1.5b")
        self.extractor = StateExtractor(model_name="qwen2.5:1.5b")

        print("Hệ thống sẵn sàng!")


    def _retrieve_relevant_memories(self, query: str, top_k: int = 3):
        """
        Nhận truy vấn -> tìm top_k Memory ID từ VectorDB -> truy xuất ngược SQL,
        đồng thời mở rộng context từ các bảng NPCs/Locations.
        """
        memory_ids = self.long_term_memory.search(query=query, top_k=top_k)
        memories = self.db.get_memories_by_ids(memory_ids)

        # Dùng thực thể xuất hiện trong memory để truy ngược thêm dữ liệu quan hệ.
        memory_npc_names = [item.npc for item in memories]
        memory_location_names = [item.location for item in memories]

        npcs_from_memory = self.db.get_npc_by_names(memory_npc_names, limit=3)
        locations_from_memory = self.db.get_location_by_names(memory_location_names, limit=3)

        # Mở rộng theo truy vấn hiện tại để bắt thêm thực thể chưa xuất hiện trong top memory.
        entity_hits = self.db.search_entities_by_query(query=query, limit_per_table=2)

        # Gộp kết quả và khử trùng lặp theo ID để giữ context gọn, ổn định.
        all_npcs = npcs_from_memory + entity_hits.get('npcs', [])
        npc_map = {item.id: item for item in all_npcs}
        npcs = list(npc_map.values())

        all_locations = locations_from_memory + entity_hits.get('locations', [])
        location_map = {item.id: item for item in all_locations}
        locations = list(location_map.values())

        rag_context = self.long_term_memory.get_rag_context(memory_ids, memories, npcs, locations)

        return memory_ids, memories, npcs, locations, rag_context


    async def _initialize_location(self):
        """
        Phân tích World Bible để sinh ra địa điểm khởi đầu của trò chơi.
        Cập nhật Trạng thái người chơi và lưu địa điểm vào CSDL.
        """
        print("[Engine] Đang kiến tạo khu vực khởi đầu...")
        # Chuẩn hóa mảng world_type thành chuỗi để đưa vào prompt
        world_type_list = self.world_state.type
        world_type = ", ".join(world_type_list) if isinstance(world_type_list, list) else str(world_type_list)

        # 2. Nạp dữ liệu bối cảnh vào Prompt
        initial_location = await self.locationAgent.initialize_location(world_name = self.world_state.name,
                                                               world_type = world_type,
                                                               theme = self.world_state.theme_and_tone)

        if not initial_location:
            raise ValueError("[Lỗi] LocationAgent không thể sinh ra địa điểm đầu tiên!")

        # Tạo ảnh và thêm đường dẫn ảnh vào
        img_path = await self.image_manager.get_or_create_location_image(
            location_name=initial_location.name,
            description=initial_location.description,
            atmosphere=initial_location.state
        )
        initial_location.image_path = img_path

        # 6. Ghi nhận địa điểm vào CSDL và cập nhật vị trí người chơi
        self.db.add_location_to_db(initial_location)

        self.player_state.currentLocation = initial_location

        return


    async def _create_new_world(self, player_idea: str):
        """
        Khởi tạo toàn bộ bối cảnh thế giới (World Bible) từ một ý tưởng ngắn.
        Lưu trạng thái vào WorldState và sao lưu ra file JSON vật lý.
        """
        print("[Engine] Đang kích hoạt World Architect...")

        # 1. Gọi WorldGenerateAgent tạo JSON cấu trúc thế giới
        world_bible = await self.worldGenerator.generate_bible(player_idea=player_idea)

        # 2. Sao lưu cấu trúc thế giới ra thư mục data
        os.makedirs('./data', exist_ok=True)
        bible_path = './data/world_bible.json'
        with open(bible_path, 'w', encoding='utf-8') as f:
            json.dump(world_bible, f, ensure_ascii=False, indent=4)
            print(f"[Engine] Đã lưu Thông tin Thế Giới tại: {bible_path}")

        # 3. Cập nhật các thông số cốt lõi vào WorldState
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

        # 1. Chuyển đổi từ vựng đặc trưng thành chuỗi
        dyn_vocab = self.world_state.dynamic_vocabulary
        vocab_str = ", ".join([f"{k}: {v}" for k, v in dyn_vocab.items()]) if dyn_vocab else "Không có"

        prologue_text = ""

        # 2. Giao việc thẳng cho StoryAgent, Tổng quản chỉ việc in kết quả ra màn hình
        story_stream = self.storyAgent.initialize_story(
            name=self.world_state.name,
            theme=self.world_state.theme_and_tone,
            core_conflict=self.world_state.core_conflict,
            mission=self.world_state.mission,
            vocab=vocab_str,
            location_name=self.player_state.currentLocation.name,
            location_state=self.player_state.currentLocation.state,
            location_description=self.player_state.currentLocation.description
        )

        # Hứng từng chữ AI gõ ra
        async for chunk in story_stream:
            print(chunk, end="", flush=True)
            prologue_text += chunk

        # 3. Lưu vào trí nhớ ngắn hạn
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

        # Kể diễn biến tiếp theo
        print("\n[đang suy nghĩ...]")

        search_query = await self.get_rag_query(player_input, current_npc_name='Không có')
        memory_ids, memories, npcs, locations, rag_context = self._retrieve_relevant_memories(search_query, top_k=3)

        sys_story = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme=self.world_state.theme_and_tone,
            world_conflict=self.world_state.core_conflict,
            world_vocabulary=self.world_state.dynamic_vocabulary,
            current_location=self.player_state.currentLocation.name,
            npc_name=[npc.name for npc in npcs],
            npc_personality=None,
            rag_context=rag_context,
            valid_paths_from_sql = None,
            system_directive="The player just acted. Describe the consequences and the reaction of the NPC/environment."
        )
        recent_history = "\n".join(self.short_term_memory.get_memory())
        full_user_input = f"[Lịch sử hội thoại gần đây]:\n{recent_history}\n\n[Hành động mới của người chơi]: {player_input}"
        user_story = self.pm.get_prompt('StoryAgent', 'user', user_input=full_user_input)

        story_response = ""

        # Stream nội dung trả về để hiển thị tuần tự
        async for chunk in self.storyAgent.generate_stream(sys_story, user_story):
            print(chunk, end="", flush=True)
            story_response += chunk
        print("\n")

        # Thực hiện trích xuất thông tin 1 lần
        recent_interaction = f"Hành động của người chơi: {player_input}\nPhản hồi của thế giới: {story_response}"
        sys_extractor = self.pm.get_prompt('StateExtractor', 'system')
        user_extractor = self.pm.get_prompt('StateExtractor', 'user', conversation_history=recent_interaction)

        # Lưu vào short-term memory câu vừa tương tác xong
        self.short_term_memory.add_memory(player_input, story_response)

        # Bơm dữ liệu từ trí nhớ ngắn hạn sang trí nhớ dài hạn (FAISS)
        await self._summarize_memory()

        # Chạy LocalAgent
        state_changes = await self.extractor.extract_state(sys_extractor, user_extractor)
        await self._update_inventory(
            items_added=state_changes.get("items_added", []),
            items_removed=state_changes.get("items_removed", [])
        )

        # Update Địa điểm
        new_loc_data = state_changes.get("new_location_entered")
        if new_loc_data:
            new_location = Location(id = None,
                                    name = new_loc_data['name'],
                                    description = new_loc_data['description'],
                                    state = new_loc_data['atmosphere'])
            await self._update_location(location = new_location)

        # Update NPC
        new_npc_data = state_changes.get('new_npc_encountered')
        if new_npc_data:
            new_npc = NPC(id = None,
                          name = new_npc_data['name'],
                          description=new_npc_data['description'],
                          personality=new_npc_data['personality'],
                          affectionate=0,
                          location = new_npc_data['location'],
                          status = new_npc_data['status'],)
            await self._update_npc(new_npc)

        # Lưu lại sự kiện vừa xảy ra vào SQL + VectorDB để dùng cho các lượt sau
        encountered_npc = state_changes.get("new_npc_encountered")
        npc_name_to_save = encountered_npc.get('name') if encountered_npc else None

        new_memory = Memory(
            location=self.player_state.currentLocation.name,
            npc=npc_name_to_save,
            text=f"Player: {player_input}\nStory: {story_response}"
        )

        memory_id = self.db.add_memory_to_db(new_memory)
        self.long_term_memory.add_memory_to_vector(new_memory.text, memory_id=memory_id)

        # Tạo lựa chọn
        choices = await self._generate_choices(story_response)
    
        self._display_choices(choices)

        return story_response, choices



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
            story_response, choices = await self._process_game_turn(player_input)
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


    async def _update_inventory(self, items_added: list, items_removed: list):
        """Hàm chuyên xử lý logic túi đồ và tạo/xóa ảnh vật phẩm."""
        if items_added or items_removed:
            print("\n[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")

            # 1. Thêm Item mới -> Vẽ ảnh
            if isinstance(items_added, list):
                for item in items_added:
                    # Kiểm tra item chưa có trong keys của Dictionary
                    if item and item not in self.player_state.inventory:
                        # Gọi Kaggle vẽ ảnh
                        img_path = await self.image_manager.get_or_create_item_image(item)

                        # Lưu vào Dict
                        self.player_state.inventory[item] = img_path
                        print(f" [+] Nhận được: {item}")

            # 2. Mất Item cũ -> Xóa ảnh và gỡ khỏi Dict
            if isinstance(items_removed, list):
                for item in items_removed:
                    if item and item in self.player_state.inventory:
                        # Lấy đường dẫn ảnh bằng pop() (vừa lấy vừa xóa khỏi Dict)
                        img_path = self.player_state.inventory.pop(item)

                        # Xóa file vật lý
                        if img_path:
                            self.image_manager.delete_image(img_path)
                        print(f" [-] Bị mất: {item}")

            # Lấy danh sách chìa khóa (Tên items) để in ra console
            inventory_status = ", ".join(self.player_state.inventory.keys()) if self.player_state.inventory else "Trống rỗng"
            print(f" [Balo hiện tại]: {inventory_status}")


    async def _update_location(self, location:Location = None):
        """Hàm chuyên xử lý logic và hình ảnh khi sang Địa điểm mới."""
        if location:
            print(f">> Phát hiện khu vực: {location.name}. State: {location.state}. Đang vẽ ảnh nền...")
            img_path = await self.image_manager.get_or_create_location_image(
                location_name=location.name,
                description=location.description,
                atmosphere=location.state
            )
            if img_path:
                # Gắn ảnh vào thuộc tính của vị trí hiện tại
                self.player_state.currentLocation.image_path = img_path
                print(f"[UI] Đã tải xong ảnh nền: {img_path}")

    async def _update_npc(self, npc: NPC = None):
        """Hàm chuyên xử lý logic và hình ảnh khi gặp NPC mới."""
        if npc:
            print(f">> Phát hiện nhân vật: {npc.name}. Đang vẽ ảnh nhân vật...")
            img_path = await self.image_manager.get_or_create_npc_image(
                npc_name=npc.name,
                description=npc.description
            )
            if img_path:
                # Lưu đường dẫn ảnh NPC vào PlayerState để truyền qua Unity
                self.player_state.current_npc_image = img_path
                print(f"[UI] Đã tải xong ảnh nhân vật: {img_path}")

    def _display_choices(self, choices):
        """Hàm con phụ trách in menu lựa chọn ra màn hình."""
        if choices:
            print("-" * 30)
            print("BẠN SẼ LÀM GÌ TIẾP THEO?")
            for choice in choices:
                print(f" {choice['id']}. {choice['action_text']} ({choice['style']})")
            print("-" * 30)



    async def get_rag_query(self, player_input: str, current_npc_name) -> str:
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
        return search_query

