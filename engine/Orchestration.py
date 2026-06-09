import time
from typing import List
from world.Entity import NPC, Quest, Location, ConsumableItem, BaseItem, WeaponItem
import os
from engine.DataManager.DatabaseManager import DatabaseManager
from engine.DataManager.PlayerState import PlayerState
from engine.DataManager.WorldState import WorldState
from engine.Utils.PromptManager import PromptManager
from engine.ImageAPI import ImageAPI
from engine.DataManager.ImageManager import ImageManager
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Utils.AudioManager import AudioManager
from engine.Agents.CloudAgents import BaseCloudAgent
from engine.Agents.LocalAgents import MusicClassifier

# Import các Subsystem đã được module hóa (Bao gồm cả Đạo diễn)
from engine.Subengine.ActionProcessor import ActionProcessor
from engine.Subengine.MemoryProcessor import MemoryProcessor
from engine.Subengine.SaveManager import SaveManager
from engine.Subengine.StateProcessor import StateProcessor
from engine.Subengine.QuestProcessor import QuestProcessor
from engine.Subengine.StoryDirector import StoryDirector
from engine.Subengine.ItemProcessor import ItemProcessor


class GameOrchestrator:
    def __init__(self, db_path, db_folder, vector_model_path, provider, groq_api_key, local_api_key):
        game_logger.info("Đang khởi tạo hệ thống Eldoria Game Engine...")

        self.pm = PromptManager('./static/prompts.yaml')
        self.db = DatabaseManager(db_path=db_path, db_folder = db_folder)
        self.player_state = PlayerState()
        self.world_state = WorldState()
        self.image_api = ImageAPI()
        self.image_manager = ImageManager(api=self.image_api, base_folder=db_folder)
        self.audio_manager = AudioManager()
        self.music_classifier = MusicClassifier(pm = self.pm, provider=provider, api_key=local_api_key)
        self.current_emotion = "bình thường"
        self.is_processing_bg = False

        # Khởi tạo các Subsystem (Phân chia rành mạch)
        self.memory_sys = MemoryProcessor(self.db,
                                          vector_model_path=vector_model_path,
                                          groq_api_key=groq_api_key,
                                          pm=self.pm)

        self.action_sys = ActionProcessor(db=self.db,
                                        player_state=self.player_state,
                                        pm=self.pm,
                                        provider = provider,
                                        local_api_key = local_api_key)

        self.state_sys = StateProcessor(db=self.db,
                                        player_state=self.player_state,
                                        image_manager=self.image_manager,
                                        groq_api_key=groq_api_key,
                                        provider = provider,
                                        local_api_key=local_api_key,
                                        pm=self.pm)

        self.item_sys = ItemProcessor(player_state=self.player_state,
                                      provider = provider,
                                      local_api_key= local_api_key,
                                      pm = self.pm)

        self.quest_sys = QuestProcessor(player_state=self.player_state,
                                        provider = provider,
                                        local_api_key=local_api_key,
                                        pm=self.pm)

        self.story_director = StoryDirector(groq_api_key=groq_api_key, pm=self.pm)
        self.save_manager = SaveManager(self)
        self.last_choices = []

        game_logger.info("Hệ thống đã sẵn sàng!")

    async def setup_new_game_api(self, player_idea: str) -> str:
        """Hàm chuyên dụng để khởi tạo New Game từ API"""
        self.player_state.clear()

        await self.db.connect()
        await self.db.reset_database()
        await self.db.create_tables()
        self.image_manager.clear_image_folders()

        world_bible_dir = os.path.join(self.db.db_folder, "world_bible.json")
        world_bible = await self.story_director.create_world_bible(player_idea, path=world_bible_dir)

        # Thiết lập World State
        world_data = world_bible.get("system_requirements", {})
        self.world_state.load_state(data = world_data)

        # Tạo bối cảnh và NPC
        starting_loc = await self.story_director.create_starting_location(
            world_state = self.world_state
        )
        self.player_state.set_location(starting_loc)

        starting_npcs = await self.story_director.initialize_key_npcs(
            world_state = self.world_state
        )

        npc_objects = []
        for npc_data in starting_npcs:
            if isinstance(npc_data, dict):
                npc_obj = NPC(
                    id=None,
                    name=npc_data.get("name", "Vô danh"),
                    personality=npc_data.get("personality", "Bí ẩn"),
                    description=npc_data.get("description", "Không rõ"),
                    affectionate=npc_data.get("affectionate", 0),
                    location=starting_loc.name,
                    status=npc_data.get("status", "Bình thường")
                )
            else:
                npc_obj = npc_data
                npc_obj.location = starting_loc.name 
                npc_obj.id = None
            
            npc_objects.append(npc_obj)
            self.player_state.add_npc(npc_obj)

        main_quest = await self.quest_sys.initialize_main_quest(world_state= self.world_state,
                                                                starting_npcs=starting_npcs)
        self.player_state.set_main_quest(main_quest=main_quest)

        # Sinh truyện mở màn
        story_response = ""
        async for chunk in self.story_director.initialize_story(starting_loc, world_bible_dir=world_bible_dir):
            story_response += chunk

        return story_response

    def get_encountered_npc_names(self) -> list:
        """Hàm bọc (Wrapper) để lấy danh sách tên NPC hiện tại"""
        return [n.name for n in self.player_state.get_current_npcs()]


    async def generate_turn_narrative_api(self, action: str) -> str:
        """Hàm bọc xử lý toàn bộ logic sinh cốt truyện (RAG + AI) cho API"""
        directive = await self.action_sys.get_system_directive(action)
        hybrid_ctx, npcs_ctx = await self.memory_sys.get_hybrid_context(action, self.player_state)

        story_response = ""
        async for chunk in self.story_director.narrate_turn(
                action, self.world_state, self.player_state, npcs_ctx, hybrid_ctx, directive):
            story_response += chunk

        return story_response


    async def _process_game_turn(self, player_input: str):
        """
        Luồng xử lí game sau mỗi lượt chọn của người chơi
        """
        # Vẫn dùng print để tương tác giao diện người dùng
        print(f"\n[Bạn]: {player_input}\n[đang suy nghĩ...]")
        game_logger.info(f"[Turn Start] Player Input: '{player_input}'")

        system_directive = await self.action_sys.get_system_directive(player_input)
        start_turn_time = time.perf_counter()

        hybrid_context, npcs_context = await self.memory_sys.get_hybrid_context(
            player_input, self.player_state
        )

        # 2. ĐẠO DIỄN KỂ CHUYỆN (Streaming qua StoryDirector)
        story_response = ""
        first_token = False
        start_story = time.perf_counter()

        # Trực tiếp gọi hàm narrate_turn của StoryDirector
        async for chunk in self.story_director.narrate_turn(player_input=player_input,
                                                            world_state=self.world_state,
                                                            player_state=self.player_state,
                                                            npcs_context=npcs_context,
                                                            hybrid_rag_context=hybrid_context,
                                                            system_directive=system_directive):
            if not first_token and chunk.strip():
                game_logger.debug(f"[Profile] Time to First Token (TTFT): {time.perf_counter() - start_story:.3f}s")
                first_token = True

            print(chunk, end="", flush=True)  # Giữ print để in cốt truyện ra màn hình
            story_response += chunk
        print()

        # 3. CHẠY TÁC VỤ NỀN (Local LLM bẻ Chunk + Cập nhật State, UI)
        episode_data, scene_emotion = await self.state_sys.process_background_tasks(player_input, story_response)
        await self.quest_sys.evaluate_turn(player_input, story_response)

        encountered_npc_names = [npc.name for npc in self.player_state.currentNPCs]

        # Gọi nhạc nền:
        if hasattr(self, 'audio_manager'):
            self.audio_manager.play_music(scene_emotion)

        # 4. LƯU KÝ ỨC
        await self.memory_sys.save_turn(player_input=player_input,
                                        story_response=story_response,
                                        episode_data=episode_data,
                                        current_location_name=self.player_state.currentLocation.name,
                                        encountered_npc_names=encountered_npc_names)

        # 5. SINH MENU LỰA CHỌN (Qua StoryDirector)

        choices = await self.story_director.generate_player_choices(
            current_location_name=self.player_state.currentLocation.name,
            encountered_npc_name = encountered_npc_names,
            recent_story_text=story_response,
            active_quest=self.player_state.active_quest,
            quest_items = self.player_state.quest_items
        )
        self.last_choices = choices
        self._display_choices(choices)

        token_report = BaseCloudAgent.get_and_reset_token_usage()
        if token_report:
            game_logger.info(token_report)

        game_logger.debug(f"[Profile] Tổng thời gian Turn: {time.perf_counter() - start_turn_time:.3f}s")
        return story_response, choices

    def _display_choices(self, choices):
        # Giữ nguyên print cho Menu
        if choices:
            print("-" * 30)
            print("BẠN SẼ LÀM GÌ TIẾP THEO?")
            for choice in choices:
                print(f" {choice['id']}. {choice['action_text']} ({choice['style']})")
            print("-" * 30)

    async def run(self):
        """Vòng lặp khởi tạo và chạy Game chính"""
        print("\n" + "=" * 50)
        print("⚔️ CHÀO MỪNG ĐẾN VỚI ELDORIA AI ADVENTURE ⚔️".center(50))
        print("=" * 50)

        # 1. Dọn dẹp Database và Ảnh từ lần chơi trước
        game_logger.info("Bắt đầu khởi tạo phiên chơi mới - Dọn dẹp dữ liệu...")
        await self.db.connect()
        await self.db.reset_database()
        await self.db.create_tables()
        self.image_manager.clear_image_folders()

        # 2. Nhận ý tưởng từ người chơi
        player_idea = input("\nNhập ý tưởng thế giới của bạn (VD: Thế giới Cyberpunk bị rồng thống trị): ")
        print("\n[Hệ thống] Đang kiến tạo thế giới... (Vui lòng chờ)")
        game_logger.info(f"Người chơi chọn ý tưởng: '{player_idea}'")

        # 3. Tạo Kinh thánh Thế giới (World Bible)
        world_bible = await self.story_director.create_world_bible(player_idea)
        reqs = world_bible.get("system_requirements", {})

        # Cập nhật World State
        self.world_state.name = reqs.get("world_name", "Vùng đất vô danh")
        self.world_state.type = reqs.get("world_type", "Fantasy")
        self.world_state.theme_and_tone = reqs.get("theme_and_tone", "Tối tăm")
        self.world_state.core_conflict = reqs.get("core_conflict", "Sinh tồn")
        self.world_state.world_mission = reqs.get("world_mission", "Sống sót")
        self.world_state.dynamic_vocabulary = world_bible.get("dynamic_vocabulary", {})

        print(f"\n>> Chào mừng đến với {self.world_state.name}!")
        game_logger.debug(f"World State Loaded: {self.world_state.name} | {self.world_state.type}")

        # 4. Khởi tạo điểm xuất phát
        print("[Hệ thống] Đang tạo điểm xuất phát và vẽ bối cảnh...")
        game_logger.info("Khởi tạo Location đầu tiên...")

        starting_loc_obj = await self.story_director.create_starting_location(world_state=self.world_state)

        starting_npcs = await self.story_director.initialize_key_npcs(world_state=self.world_state)

        # Lưu vào State và Database
        self.player_state.currentLocation = starting_loc_obj
        await self.db.add_location_to_db(starting_loc_obj)

        npc_objs = []
        for starting_npc in starting_npcs:
            print(starting_npc)
            npc_obj = NPC(
                    id=None,
                    name=starting_npc.get("name", "Vô danh"),
                    personality=starting_npc.get("personality", "Bí ẩn"),
                    description=starting_npc.get("description", "Không rõ"),
                    affectionate=starting_npc.get("affectionate", 0),
                    location=starting_npc.get("location", "Không biết"),
                    status=starting_npc.get("status", "Bình thường")
            )
            await self.db.add_npc_to_db(npc_obj)
            npc_objs.append(npc_obj)

        print("[Hệ thống] Đang kiến tạo Vận mệnh và Chiến dịch chính...")
        await self.quest_sys.initialize_main_quest(
            world_state=self.world_state,
            starting_npcs=npc_objs
        )

        # Tải ảnh nền cho điểm xuất phát
        await self.image_manager.get_or_create_location_image(
            starting_loc_obj.name, starting_loc_obj.description, starting_loc_obj.atmosphere
        )

        # Tạo nhạc cho turn 0
        print(f"[Hệ thống] Đang phân tích nhạc nền cho không khí: '{starting_loc_obj.atmosphere}'...")
        turn0_emotion = await self.music_classifier.classify_emotion(starting_loc_obj.atmosphere)
        self.audio_manager.play_music(turn0_emotion)

        # 5. Kể đoạn mở đầu (Prologue)
        print("\n" + "=" * 50)
        print("PROLOGUE".center(50))
        print("=" * 50 + "\n")
        world_bible_dir = os.path.join(self.db.db_folder, "world_bible.json")
        story_response = ""
        async for chunk in self.story_director.initialize_story(starting_loc_obj, world_bible_dir= world_bible_dir):
            print(chunk, end="", flush=True)
            story_response += chunk

        print("\n\n" + "=" * 50)

        # Lưu Ký ức cho Turn 0
        game_logger.info("Lưu ký ức Prologue (Turn 0)...")
        await self.memory_sys.save_turn(
            player_input="[Bắt đầu trò chơi]",
            story_response=story_response,
            episode_data={},
            current_location_name=starting_loc_obj.name,
            encountered_npc_names=[]
        )

        # 6. Tạo lựa chọn đầu tiên từ prologue
        choices = await self.story_director.generate_player_choices(
            current_location_name=self.player_state.currentLocation.name,
            encountered_npc_name=[],
            recent_story_text=story_response,
            active_quest = self.player_state.active_quest,
            quest_items = self.player_state.quest_items
        )
        self.last_choices = choices
        self._display_choices(choices)

        # 7. Mở vòng lặp Game Loop
        game_logger.info("=== BẮT ĐẦU VÒNG LẶP GAME CHÍNH (GAME LOOP) ===")
        while True:
            player_input = input("\nBạn muốn làm gì? (Gõ 'exit' để thoát, 'on' để bật nhạc, 'off' để tắt nhạc: ")

            if player_input.lower() in ['exit', 'quit', 'thoát']:
                print("\n[Hệ thống] Đang lưu và đóng Database. Hẹn gặp lại!")
                game_logger.info("Người chơi thoát game an toàn. Đang đóng CSDL...")

                if self.db.conn:
                    # Phải await việc đóng connection trong aiosqlite
                    await self.db.conn.close()
                break

            # Tắt bật nhạc
            if player_input.lower().strip() in ['off', 'tắt nhạc', 'mute']:
                print("[Hệ thống] 🔇 Đã TẮT nhạc nền.")
                if hasattr(self, 'audio_manager'):
                    self.audio_manager.toggle_music(False)
                continue

            if player_input.lower().strip() in ['on', 'bật nhạc', 'unmute']:
                print("[Hệ thống] 🔊 Đã BẬT nhạc nền.")
                if hasattr(self, 'audio_manager'):
                    self.audio_manager.toggle_music(True)
                continue

            if player_input.lower().strip() in ["i", "inv", "inventory", "túi đồ", "balo", "tui do"]:
                await self._open_inventory_menu()
                continue  # Bỏ qua turn để không gửi chữ 'i' lên cho AI xử lý

                # Mở sổ tay nhiệm vụ
            if player_input.lower().strip() in ['q', 'quest', 'nhiệm vụ', 'quests', 'nhiem vu']:
                # Lấy story_response của turn trước đó (nếu có) để làm bối cảnh chuyển Quest
                last_story = locals().get('story_response', 'Bạn đang đứng quan sát xung quanh.')
                await self._open_quest_menu(story_response=last_story)
                continue  # Bỏ qua turn để không gửi chữ 'q' lên cho AI xử lý

            resolved_input = player_input
            if self.last_choices and player_input.strip().isdigit():
                choice_id = int(player_input.strip())
                matched = next((c for c in self.last_choices if c.get("id") == choice_id), None)
                if matched and matched.get("action_text"):
                    resolved_input = matched["action_text"]

            try:
                await self._process_game_turn(resolved_input)
            except Exception as e:
                game_logger.error(f"[Game Loop] Lỗi nghiêm trọng ở Turn hiện tại: {e}", exc_info=True)

    async def _open_inventory_menu(self):
        """
        Hiển thị giao diện túi đồ và thông tin chi tiết vật phẩm.
        """
        print("\n" + "=" * 15 + " TÚI ĐỒ " + "=" * 15)
        inv = self.player_state.inventory_manager

        # In ra các ngăn chứa
        print(f"🗡️ [Vũ khí]: {', '.join([w.name for w in inv.weapon_item_inventory]) or 'Trống'}")
        if inv.equipped_weapon:
            print(f"   -> Đang trang bị: {inv.equipped_weapon.name}")

        print(f"🧪 [Tiêu hao]: {', '.join([c.name for c in inv.consumable_item_inventory]) or 'Trống'}")
        print(f"📜 [Nhiệm vụ]: {', '.join([q.name for q in inv.quest_item_inventory]) or 'Trống'}")
        print(f"📦 [Khác]: {', '.join([m.name for m in inv.interactive_item_inventory]) or 'Trống'}")
        print("=" * 38)

        # Cho phép người chơi xem chi tiết đồ
        cmd = input("Nhập tên vật phẩm để xem chi tiết (hoặc 'Enter' để đóng): ").strip()
        if cmd:
            item = self.player_state.get_item_by_name(cmd)
            if item:
                print(f"\n[{item.name}] - Phân loại: {item.item_type.upper()}")
                print(f"📝 Mô tả: {item.description}")
                if item.item_type == 'weapon':
                    print(f"⚔️ Sát thương cơ bản: {getattr(item, 'base_damage', 0)}")
                    if getattr(item, 'status_effect', None):
                        print(f"🔥 Hiệu ứng đính kèm: {item.status_effect}")
                elif item.item_type == 'consumable':
                    print(f"💚 Hiệu ứng phục hồi: {getattr(item, 'effect', 0)} HP")
            else:
                print("[Hệ thống] Không tìm thấy vật phẩm này trong túi!")

    async def _open_quest_menu(self, story_response: str):
        """
        Hiển thị sổ tay nhiệm vụ và cho phép chuyển đổi mục tiêu.
        """
        print("\n" + "=" * 12 + " NHẬT KÝ NHIỆM VỤ " + "=" * 12)
        quests = self.player_state.quests

        if not quests:
            print("Bạn chưa có nhiệm vụ nào.")
            print("=" * 42)
            return

        # Hiển thị danh sách nhiệm vụ với Icon biểu cảm
        for idx, q in enumerate(quests):
            icon = "🔄" if q.status == 'in_progress' else "✅" if q.status == 'completed' else "❌" if q.status == 'failed' else "📜"
            print(f"[{idx}] {icon} {q.name} - Trạng thái: {q.status.upper()}")
            print(f"    Mục tiêu: {q.objectives}")

            if q == self.player_state.active_quest:
                print("    -> [ĐANG THEO DÕI]")
        print("=" * 42)

        # Cho phép chuyển đổi Quest
        cmd = input("\nNhập số ID nhiệm vụ để chuyển đổi (hoặc 'Enter' để đóng): ").strip()
        if cmd.isdigit():
            idx = int(cmd)
            if 0 <= idx < len(quests):
                target = quests[idx]

                # Chặn việc chuyển lại đúng quest đang làm
                if target == self.player_state.active_quest:
                    print("\n[Hệ thống] Bạn đang làm nhiệm vụ này rồi!")
                    return

                print("\n[Hệ thống] Đang lưu trữ ký ức và chuyển đổi không gian/thời gian...")
                transition_msg = await self.quest_sys.switch_quest(target, story_response, self.last_choices)
                print(f"\n[Đạo diễn]: 🔄 {transition_msg}\n")
            else:
                print("\n[Hệ thống] ID nhiệm vụ không hợp lệ!")


    async def switch_quest(self, target_quest: Quest, recent_story: str, current_choices: list[str]):
        transition_msg = await self.quest_sys.switch_quest(
            target_quest=target_quest,
            recent_story=recent_story,
            current_choices=current_choices
        )
        return transition_msg


    async def add_location_to_db(self, location: Location):
        await self.db.add_location_to_db(location_obj = location)

    async def add_npc_to_db(self, npc: NPC):
        await self.db.add_npc_to_db(npc_obj = npc)

    async def quest_evaluate_turn(self, player_input: str, story_response: str):
        await self.quest_sys.evaluate_turn(player_input=player_input, story_response=story_response)

    async def state_process_background_tasks(self, player_input: str, story_response:str):
        return await self.state_sys.process_background_tasks(player_input=player_input,
                                                      story_response=story_response)

    async def memory_save_turn(self, player_input: str,
                                story_response:str,
                                episode_data,
                                current_location_name: str,
                                encountered_npc_names: str):
        await self.memory_sys.save_turn(player_input=player_input,
            story_response=story_response,
            episode_data=episode_data,
            current_location_name=current_location_name,
            encountered_npc_names=encountered_npc_names
        )

    async def use(self, item_list: List[BaseItem], action_details:str):
        return await self.item_sys.use(item_list=item_list, action_details=action_details)

    def use_consumables(self, consumable_item: ConsumableItem):
        self.player_state.use_consumables(consumable_item)

    def equip_weapon(self, weapon: WeaponItem):
        self.player_state.equip_weapon(weapon=weapon)

    async def craft(self, item_list: List[BaseItem], action_details: str):
        return await self.item_sys.craft(item_list = item_list,
                                         action_details = action_details,
                                         image_manager = self.image_manager)

    async def save_game(self, slot_name:str):
        await self.save_manager.save_game(slot_name=slot_name)

    async def load_game(self, slot_name:str):
        return await self.save_manager.load_game(slot_name=slot_name)

    #====================================================
    #=                    GETTER                        =
    #====================================================
    def get_player_item(self, item_name: str):
        return self.player_state.get_item(item_name)

    def get_all_items(self):
        return self.player_state.get_all_items()

    def get_current_location_name(self):
        return self.player_state.get_current_location_name()

    def get_item_by_name(self, item_name:str):
        return self.player_state.get_item_by_name(item_name=item_name)

    def get_current_npcs(self):
        return self.player_state.get_current_npcs()

    def get_current_location(self):
        return self.player_state.get_current_location()

    def get_current_hp(self):
        return self.player_state.get_current_hp()

    def get_max_hp(self):
        return self.player_state.get_max_hp()

    def get_equipped_weapon(self):
        return self.player_state.get_equipped_weapon()

    def get_active_quest(self):
        return self.player_state.get_active_quest()

    def get_all_quests(self):
        return self.player_state.get_all_quests()

    async def get_all_npcs(self):
        return await self.db.npc_manager.get_all()

    async def get_all_locations(self):
        return await self.db.location_manager.get_all()

