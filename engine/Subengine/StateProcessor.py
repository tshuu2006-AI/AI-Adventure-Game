"""Module điều phối việc cập nhật thông tin, trạng thái của trò chơi trong csdl"""
import asyncio
import time
from world.Entity import Location, NPC
from engine.Agents.LocalAgents import StateExtractor, MemoryExtractor, ItemAgent
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Agents.CloudAgents import LocationAgent, NPCAgent
from static.config import STATE_EXTRACTOR_MODEL, MEMORY_EXTRACTOR_MODEL, LOCATION_AGENT_MODEL, NPC_AGENT_MODEL, ITEM_AGENT_MODEL
from engine.DataManager.DatabaseManager import DatabaseManager
from engine.Utils.PromptManager import PromptManager
from engine.DataManager.PlayerState import PlayerState

class StateProcessor:
    """Lớp quản lý việc tạo sinh NPC, interface để cập nhật các thông tin trong cơ sở dữ liệu"""
    def __init__(self, db: DatabaseManager,
                 player_state: PlayerState,
                 image_manager,
                 groq_api_key: str,
                 gemini_api_key: str,
                 pm: PromptManager):
        self.db = db
        self.player_state = player_state
        self.image_manager = image_manager
        self.state_extractor = StateExtractor(model_name = STATE_EXTRACTOR_MODEL, pm = pm, gemini_api_key=gemini_api_key)
        self.memory_extractor = MemoryExtractor(model_name = MEMORY_EXTRACTOR_MODEL, pm = pm, gemini_api_key=gemini_api_key)

        self.location_agent = LocationAgent(api_key = groq_api_key,
                                            pm = pm,
                                            model_name = LOCATION_AGENT_MODEL)

        self.npc_agent = NPCAgent(api_key = groq_api_key,
                                  pm = pm,
                                  model_name = NPC_AGENT_MODEL)

        self.item_agent = ItemAgent(model_name = ITEM_AGENT_MODEL, pm = pm, gemini_api_key=gemini_api_key)


    async def _update_location(self, new_location_entered_name: str, context: str) -> Location:
        """
        Xử lý logic khi người chơi bước vào một khu vực mới.
        Cập nhật PlayerState, lưu Database và vẽ ảnh nền.
        Trả về đối tượng Location để sử dụng ở các bước tiếp theo.
        """
        # 1. Khởi tạo đối tượng Location từ dữ liệu JSON của LLM
        new_location = await self.location_agent.generate_location(
            current_location=self.player_state.currentLocation.name,
            target_location=new_location_entered_name,
            context=context
        )

        game_logger.info(f">> [Hệ Thống] Phát hiện khu vực mới: {new_location.name}. Đang tải ảnh nền...")

        # 2. Gọi ImageManager tải/vẽ ảnh nền (Chạy bất đồng bộ)
        img_path = await self.image_manager.get_or_create_location_image(
            location_name=new_location.name,
            description=new_location.description,
            atmosphere=new_location.atmosphere
        )

        # 3. Cập nhật PlayerState
        if img_path:
            new_location.image_path = img_path
            game_logger.debug(f"[UI] Đã tải xong ảnh nền: {img_path}")

        self.player_state.currentLocation = new_location

        # 4. Ghi nhận địa điểm mới vào CSDL để dùng cho FAISS Entity-Centric sau này
        await self.db.add_location_to_db(new_location)

        return new_location

    async def _update_npcs(self, npcs_arrived: list, npcs_left: list, context: str):
        """
        Quản lý danh sách các NPC đang tương tác trong PlayerState dựa trên dữ liệu chuỗi tinh gọn.
        - Loại bỏ các NPC đã rời đi hoặc đã chết.
        - Khôi phục từ DB hoặc tạo mới profile cho các NPC vừa xuất hiện bằng xử lý song song.
        """
        # 1. XỬ LÝ CÁC NPC RỜI ĐI (npcs_left)
        if npcs_left:
            # Lowercase toàn bộ danh sách rời đi để tăng tốc độ so sánh
            left_names_set = {name.strip().lower() for name in npcs_left if name and str(name).strip()}

            self.player_state.currentNPCs = [
                npc for npc in self.player_state.currentNPCs
                if npc.name.lower() not in left_names_set
            ]
            # Ghi log bằng mảng gốc để giữ nguyên viết hoa/thường cho đẹp
            for name in npcs_left:
                if name.strip().lower() in left_names_set:
                    game_logger.info(f" [-] NPC đã rời khỏi phân cảnh: {name}")

        # Dùng Set để tra cứu tốc độ cao O(1) thay vì List O(N)
        current_npc_names = {npc.name.lower() for npc in self.player_state.currentNPCs}

        # Chỉ lấy những cái tên hợp lệ (không rỗng) và chưa có trong cảnh
        real_new_npcs = []
        for name in npcs_arrived:
            name_lower = name.strip().lower()
            if not name_lower: continue
            
            # Kiểm tra xem tên ngắn có nằm trong tên dài, hoặc ngược lại không
            is_exist = any(name_lower in curr_name or curr_name in name_lower for curr_name in current_npc_names)
            
            if not is_exist:
                real_new_npcs.append(name.strip())

        if not real_new_npcs:
            return

        # 2. KIỂM TRA DATABASE 1 LẦN DUY NHẤT CHO TOÀN BỘ NPC MỚI (Khắc phục N+1 Query)
        existing_npcs = await self.db.get_npc_by_names(real_new_npcs, limit=len(real_new_npcs))

        # Tạo mapping để dễ truy xuất
        existing_npcs_map = {npc.name.lower(): npc for npc in existing_npcs}
        completely_new_names = []

        # 3. Phân loại: Ai đã có trong Database, ai hoàn toàn mới?
        for npc_name in real_new_npcs:
            npc_lower = npc_name.lower()
            if npc_lower in existing_npcs_map:
                game_logger.debug(f"[State] Đưa NPC cũ '{npc_name}' vào cảnh.")
                self.player_state.currentNPCs.append(existing_npcs_map[npc_lower])
            else:
                completely_new_names.append(npc_name)

        # 4. GỌI API MỘT LẦN DUY NHẤT CHO TOÀN BỘ NPC MỚI
        if completely_new_names:
            game_logger.info(f"[Cloud] Đang tạo hàng loạt NPC mới: {completely_new_names}...")

            results = await self.npc_agent.generate_npcs(completely_new_names, context)

            loc_name = self.player_state.currentLocation.name if self.player_state.currentLocation else "Unknown"

            # 5. Lưu vào Database (Bảo vệ an toàn dữ liệu trả về)
            if isinstance(results, list):
                for npc_dict in results:
                    # Khởi tạo an toàn bằng Keyword Arguments
                    new_npc = NPC(
                        id=None,
                        name=npc_dict.get("name", "Vô danh"),
                        personality=npc_dict.get("personality", "Bí ẩn"),
                        description=npc_dict.get("description", "Không rõ"),
                        affectionate=npc_dict.get("affectionate", 0),
                        location=loc_name,
                        status=npc_dict.get("status", "Bình thường")
                    )

                    img_path = await self.image_manager.get_or_create_npc_image(
                        npc_name=new_npc.name,
                        description=new_npc.description
                    )
                    if img_path:
                        new_npc.image_path = img_path

                    res = await self.db.add_npc_to_db(new_npc)
                    if res: self.player_state.currentNPCs.append(new_npc)
            else:
                game_logger.error(f"[Cloud Lỗi] Định dạng trả về bulk_npcs không hợp lệ: {results}")



    async def _update_affection_and_status(self, affection_changes: list):
        if not affection_changes:
            return

        for change in affection_changes:
            npc_name = change.get("npc_name", "").strip()
            delta = change.get("delta", 0)
            new_status = change.get("new_status")

            if not npc_name or (delta == 0 and not new_status):
                continue

            await self.db.update_npc_state(npc_name, affection_change=delta, new_status=new_status)

            # Đồng bộ lại object đang sống trong PlayerState
            for npc in self.player_state.currentNPCs:
                if npc.name.lower() == npc_name.lower():
                    if delta != 0:
                        npc.affectionate = max(-100, min(100, int(npc.affectionate) + delta))
                    if new_status:
                        npc.status = new_status
                    break

    async def _update_player_state(self, items_added: list,
                                   items_removed: list,
                                   story_response: str,
                                   context: str,
                                   is_safe_zone: bool):
        """Hàm chuyên xử lý logic túi đồ và tự động lưu Checkpoint (Snapshot) khi an toàn."""

        # ==========================================
        # 1. CẬP NHẬT TÚI ĐỒ (ĐÃ VÁ LỖI BUG LOGIC)
        # ==========================================
        if items_added or items_removed:
            game_logger.info("[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")
            invalid_items = ["không", "không có", "none", "trống", "nothing", "không có gì", "null", "n/a"]

            # Thêm Item mới
            if isinstance(items_added, list):
                for item_data in items_added:
                    if isinstance(item_data, dict):
                        item_name = str(item_data.get("name", "")).strip()
                        item_type = str(item_data.get("type", "miscellaneous")).strip()
                    else:
                        item_name = str(item_data).strip()
                        item_type = "miscellaneous"

                    if not item_name or str(item_name).strip().lower() in invalid_items:
                        continue

                    # [ĐÃ SỬA]: Bỏ lệnh check tồn tại để cho phép nhặt nhiều đồ giống nhau (VD: 3 Bình máu)
                    img_path = await self.image_manager.get_or_create_item_image(item_name)

                    new_item = await self.item_agent.generate_item(
                        context=context,
                        item_name=item_name,
                        item_type=item_type,
                        quest=getattr(self.player_state, "active_quest", [None])[0] if getattr(self.player_state,
                                                                                                "active_quests",
                                                                                                []) else None
                    )
                    new_item.image_path = img_path

                    self.player_state.add_item(new_item)
                    game_logger.info(f" [+] Nhận được: {item_name}")

            # Mất Item cũ
            if isinstance(items_removed, list):
                for item_name in items_removed:
                    if not item_name or str(item_name).strip().lower() in invalid_items:
                        continue

                    target_item = self.player_state.get_item_by_name(item_name.strip())

                    if target_item:
                        self.player_state.remove_item(target_item)
                        # [ĐÃ SỬA]: Bỏ lệnh xóa file vật lý (delete_image) để tái sử dụng ảnh cache sau này
                        game_logger.info(f" [-] Bị mất: {target_item.name}")

            inventory_status = self.player_state.get_all_item_names()
            game_logger.info(f" [Balo hiện tại]: {inventory_status}")

        # ==========================================
        # 2. LƯU SNAPSHOT VÀO QUEST HIỆN TẠI (SAFE ZONE)
        # ==========================================
        self.player_state.is_safe_zone = is_safe_zone
        if is_safe_zone:
            # Tách Story Response từ biến context (do context truyền vào đang chứa cả player_input và story_response)

            # 2.1. Nếu đang ở trong một Nhiệm vụ phụ (Quest nhánh)
            if hasattr(self.player_state, "active_quest") and self.player_state.active_quest:
                current_quest = self.player_state.active_quest
                current_quest.snapshot = {
                    "location": self.player_state.currentLocation,
                    "npcs": self.player_state.currentNPCs.copy() if self.player_state.currentNPCs else [],
                    "last_story": story_response
                }

                game_logger.debug(f"[Checkpoint] Đã lưu Snapshot an toàn trực tiếp vào Quest: '{current_quest.name}'.")


    async def process_background_tasks(self, player_input: str, story_response: str):
        """Chạy song song trích xuất State"""
        start_bg = time.perf_counter()

        context = (f"Player Action: {player_input}\n"
                   f"Story Response: {story_response}")

        extract_task = [
        self.state_extractor.extract_state(player_input=player_input,
                                   story_response=story_response,
                                   player_state=self.player_state),
        self.memory_extractor.extract_memory(player_input = player_input,
                                             story_response = story_response)
        ]

        results = await asyncio.gather(*extract_task, return_exceptions=True)

        # Bóc tách kết quả an toàn
        state_changes = results[0] if not isinstance(results[0], Exception) else {}
        if isinstance(results[0], Exception):
            game_logger.error(f"[StateExtractor Lỗi] {results[0]}")

        atomic_memories = results[1] if not isinstance(results[1], Exception) else {}
        if isinstance(results[1], Exception):
            game_logger.error(f"[MemoryExtractor Lỗi] {results[1]}")

        # Chuẩn hóa dữ liệu phòng trường hợp Dict rỗng
        if not isinstance(state_changes, dict): state_changes = {}
        if not isinstance(atomic_memories, dict): atomic_memories = {}

        items_added = state_changes.get("items_added", [])
        items_removed = state_changes.get("items_removed", [])
        npcs_arrived = state_changes.get("npcs_arrived", [])
        npcs_left = state_changes.get("npcs_left", [])
        new_location_entered_name = state_changes.get("new_location_entered", "")
        scene_emotion = state_changes.get("scene_emotion", "bình thường")
        affection_changes = state_changes.get("affection_changes", [])
        is_safe_zone = state_changes.get("is_safe_zone", True)

        game_logger.debug(f"[Profile] Background Tasks (State Extraction): {time.perf_counter() - start_bg:.3f}s")

        if new_location_entered_name:
            current_loc_name = self.player_state.currentLocation.name if self.player_state.currentLocation else ""
            
            if new_location_entered_name.strip().lower() != current_loc_name.strip().lower():
                await self._update_location(new_location_entered_name=new_location_entered_name, context=context)
            else:
                game_logger.debug(f"[State] Đã ở {current_loc_name}, không cần phân tích tạo lại.")

        update_tasks = [
            self._update_player_state(items_added= items_added,
                                    items_removed=items_removed,
                                    context = context,
                                    story_response=story_response,
                                    is_safe_zone=is_safe_zone),
            self._update_npcs(npcs_arrived = npcs_arrived,
                              npcs_left = npcs_left,
                              context = context),
            self._update_affection_and_status(affection_changes=affection_changes)
        ]

        await asyncio.gather(*update_tasks)
        return atomic_memories, scene_emotion
