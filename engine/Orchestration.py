import time

from engine.DataManager.DatabaseManager import DatabaseManager, PlayerState, WorldState
from engine.Utils.PromptManager import PromptManager
from engine.ImageAPI import ImageAPI
from engine.DataManager.ImageManager import ImageManager
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Utils.AudioManager import AudioManager
from engine.Agents.LocalAgents import MusicClassifier

# Import các Subsystem đã được module hóa (Bao gồm cả Đạo diễn)
from engine.Subengine.ActionProcessor import ActionProcessor
from engine.Subengine.MemoryProcessor import MemoryProcessor
from engine.Subengine.StateProcessor import StateProcessor
from engine.Subengine.StoryDirector import StoryDirector


class GameOrchestrator:
    def __init__(self, db_path, vector_model_path, groq_api_key):
        game_logger.info("Đang khởi tạo hệ thống Eldoria Game Engine...")

        self.pm = PromptManager('./static/prompts.yaml')
        self.db = DatabaseManager(db_path=db_path)
        self.player_state = PlayerState()
        self.world_state = WorldState()
        self.image_api = ImageAPI()
        self.image_manager = ImageManager(api=self.image_api)
        self.audio_manager = AudioManager()
        self.music_classifier = MusicClassifier(pm = self.pm, model_name = "qwen2.5:1.5b")

        # Khởi tạo các Subsystem (Phân chia rành mạch)
        self.memory_sys = MemoryProcessor(self.db,
                                          vector_model_path=vector_model_path,
                                          groq_api_key=groq_api_key,
                                          pm=self.pm)

        self.action_sys = ActionProcessor(db=self.db,
                                        player_state=self.player_state,
                                        pm=self.pm)

        self.state_sys = StateProcessor(db=self.db,
                                        player_state=self.player_state,
                                        image_manager=self.image_manager,
                                        groq_api_key=groq_api_key,
                                        pm=self.pm)

        self.story_director = StoryDirector(groq_api_key=groq_api_key, pm=self.pm)
        self.last_choices = []

        game_logger.info("Hệ thống đã sẵn sàng!")

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
        async for chunk in self.story_director.narrate_turn(
                player_input, self.world_state, self.player_state, npcs_context, hybrid_context, system_directive
        ):
            if not first_token and chunk.strip():
                game_logger.debug(f"[Profile] Time to First Token (TTFT): {time.perf_counter() - start_story:.3f}s")
                first_token = True

            print(chunk, end="", flush=True)  # Giữ print để in cốt truyện ra màn hình
            story_response += chunk
        print()

        # 3. CHẠY TÁC VỤ NỀN (Local LLM bẻ Chunk + Cập nhật State, UI)
        atomic_memories, scene_emotion = await self.state_sys.process_background_tasks(player_input, story_response)
        encountered_npc_names = [npc.name for npc in self.player_state.currentNPCs]

        # Gọi nhạc nền:
        if hasattr(self, 'audio_manager'):
            self.audio_manager.play_music(scene_emotion)

        # 4. LƯU KÝ ỨC
        await self.memory_sys.save_turn(player_input=player_input,
                                        story_response=story_response,
                                        atomic_memories=atomic_memories,
                                        current_location_name=self.player_state.currentLocation.name,
                                        encountered_npc_names=encountered_npc_names)

        # 5. SINH MENU LỰA CHỌN (Qua StoryDirector)

        choices = await self.story_director.generate_player_choices(
            current_location_name=self.player_state.currentLocation.name,
            encountered_npc_name = encountered_npc_names,
            recent_story_text=story_response
        )
        self.last_choices = choices
        self._display_choices(choices)

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
        self.world_state.mission = reqs.get("world_mission", "Sống sót")
        self.world_state.dynamic_vocabulary = world_bible.get("dynamic_vocabulary", {})

        print(f"\n>> Chào mừng đến với {self.world_state.name}!")
        game_logger.debug(f"World State Loaded: {self.world_state.name} | {self.world_state.type}")

        # 4. Khởi tạo điểm xuất phát
        print("[Hệ thống] Đang tạo điểm xuất phát và vẽ bối cảnh...")
        game_logger.info("Khởi tạo Location đầu tiên...")

        starting_loc_obj = await self.story_director.create_starting_location(
            self.world_state.name, self.world_state.type, self.world_state.theme_and_tone
        )

        # Lưu vào State và Database
        self.player_state.currentLocation = starting_loc_obj
        await self.db.add_location_to_db(starting_loc_obj)

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

        story_response = ""
        async for chunk in self.story_director.initialize_story(starting_loc_obj):
            print(chunk, end="", flush=True)
            story_response += chunk

        print("\n\n" + "=" * 50)

        # Lưu Ký ức cho Turn 0
        game_logger.info("Lưu ký ức Prologue (Turn 0)...")
        await self.memory_sys.save_turn(
            player_input="[Bắt đầu trò chơi]",
            story_response=story_response,
            atomic_memories=[f"Nhân vật chính thức tỉnh tại {starting_loc_obj.name}."],
            current_location_name=starting_loc_obj.name,
            encountered_npc_names=[]
        )

        # 6. Tạo lựa chọn đầu tiên từ prologue
        choices = await self.story_director.generate_player_choices(
            current_location_name=self.player_state.currentLocation.name,
            encountered_npc_name=[],
            recent_story_text=story_response
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
