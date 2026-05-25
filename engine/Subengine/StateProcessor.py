"""Module điều phối việc cập nhật thông tin, trạng thái của trò chơi trong csdl"""
import asyncio
import time
from world.Entity import Location, NPC, Item
from engine.Agents.LocalAgents import StateExtractor, MemoryExtractor
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Agents.CloudAgents import LocationAgent, NPCAgent
from static.config import STATE_EXTRACTOR_MODEL, MEMORY_EXTRACTOR_MODEL, LOCATION_AGENT_MODEL, NPC_AGENT_MODEL


class StateProcessor:
    """Lớp quản lý việc tạo sinh NPC, interface để cập nhật các thông tin trong cơ sở dữ liệu"""
    def __init__(self, db, player_state, image_manager, groq_api_key, gemini_api_key, pm):
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
        real_new_npcs = [
            name.strip() for name in npcs_arrived
            if name and str(name).strip() and name.strip().lower() not in current_npc_names
        ]

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

                    await self.db.add_npc_to_db(new_npc)
                    self.player_state.currentNPCs.append(new_npc)
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

    async def _update_inventory(self, items_added: list, items_removed: list):
        """Hàm chuyên xử lý logic túi đồ dưới dạng List[Item] và quản lý tài nguyên ảnh."""
        if items_added or items_removed:
            game_logger.info("[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")
            invalid_items = ["không", "không có", "none", "trống", "nothing", "không có gì", "null", "n/a"]

            # 1. Thêm Item mới vào Danh sách
            if isinstance(items_added, list):
                for item_name in items_added:
                    if not item_name or str(item_name).strip().lower() in invalid_items:
                        continue

                    item_name = str(item_name).strip()

                    # 🌟 KIỂM TRA: Nếu vật phẩm chưa có trong danh sách mảng Object
                    if not any(item.name.lower() == item_name.lower() for item in self.player_state.inventory):
                        # Gọi Kaggle vẽ ảnh
                        img_path = await self.image_manager.get_or_create_item_image(item_name)

                        # Khởi tạo Object Item chuẩn
                        new_item = Item(id=None, name=item_name,
                                        description=f"Vật phẩm '{item_name}' nhặt được trong hành trình.")
                        new_item.image_path = img_path

                        # 🌟 THÊM VÀO MẢNG (APPEND):
                        self.player_state.inventory.append(new_item)
                        game_logger.info(f" [+] Nhận được: {item_name}")

            # 2. Mất Item cũ khỏi Danh sách
            if isinstance(items_removed, list):
                for item_name in items_removed:
                    if not item_name or str(item_name).strip().lower() in invalid_items:
                        continue

                    item_name = str(item_name).strip()

                    # 🌟 TÌM OBJECT TRONG MẢNG:
                    target_item = next(
                        (item for item in self.player_state.inventory if item.name.lower() == item_name.lower()), None)

                    if target_item:
                        # 🌟 XÓA KHỎI MẢNG (REMOVE):
                        self.player_state.inventory.remove(target_item)

                        # Xóa file vật lý
                        if hasattr(target_item, 'image_path') and target_item.image_path:
                            self.image_manager.delete_image(target_item.image_path)
                        game_logger.info(f" [-] Bị mất: {item_name}")

            # In nhật ký balo ra màn hình điều khiển
            inventory_status = ", ".join(
                [item.name for item in self.player_state.inventory]) if self.player_state.inventory else "Trống rỗng"
            game_logger.info(f" [Balo hiện tại]: {inventory_status}")


    async def process_background_tasks(self, player_input, story_response):
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

        game_logger.debug(f"[Profile] Background Tasks (State Extraction): {time.perf_counter() - start_bg:.3f}s")

        if new_location_entered_name:
            await self._update_location(new_location_entered_name= new_location_entered_name,
                                    context=context)

        update_tasks = [
            self._update_inventory(items_added= items_added,
                                   items_removed=items_removed),
            self._update_npcs(npcs_arrived = npcs_arrived,
                              npcs_left = npcs_left,
                              context = context),
            self._update_affection_and_status(affection_changes=affection_changes)
        ]

        await asyncio.gather(*update_tasks)
        return atomic_memories, scene_emotion
