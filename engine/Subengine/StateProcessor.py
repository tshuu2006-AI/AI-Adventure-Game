import asyncio
import time
from world.Entity import Location, NPC
from engine.Agents.LocalAgents import StateExtractor, MemoryExtractor
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Agents.CloudAgents import LocationAgent, NPCAgent


class StateProcessor:
    def __init__(self, db, player_state, image_manager, groq_api_key, pm):
        self.db = db
        self.player_state = player_state
        self.image_manager = image_manager
        self.state_extractor = StateExtractor(pm = pm, model_name="qwen2.5:1.5b")
        self.memory_extractor = MemoryExtractor(pm = pm, model_name="qwen2.5:1.5b")

        self.location_agent = LocationAgent(api_key = groq_api_key,
                                            pm = pm,
                                            model_name = "qwen/qwen3-32b")

        self.npc_agent = NPCAgent(api_key = groq_api_key,
                                  pm = pm,
                                  model_name = "qwen/qwen3-32b")

    async def _generate_and_save_new_npc(self, context: str, npc_name: str) -> NPC:
        game_logger.info(f"[Cloud] Đang thiết kế chỉ số và cốt truyện nền cho: {npc_name}...")

        # Gọi LLM sinh thuộc tính nhân vật
        npc_json = await self.npc_agent.generate_npc(context=context, npc_name=npc_name)

        npc_obj = NPC(
            id=None,
            name=npc_json.get('name', npc_name),
            personality=npc_json.get('personality', 'Bí ẩn'),
            description=npc_json.get('description', 'Một bóng người vừa mới xuất hiện.'),
            affectionate=npc_json.get('affectionate', 0),
            location=self.player_state.currentLocation.name,
            status=npc_json.get('status', 'Bình thường')
        )

        # Vẽ ảnh bằng Stable Diffusion (Chạy bất đồng bộ)
        img_path = await self.image_manager.get_or_create_npc_image(
            npc_name=npc_obj.name,
            description=npc_obj.description
        )
        if img_path:
            npc_obj.image_path = img_path

        # Lưu vào DB trước khi trả về
        await self.db.add_npc_to_db(npc_obj)
        return npc_obj


    async def _update_location(self, new_location_entered_name: str, context: str) -> Location:
        """
        Xử lý logic khi người chơi bước vào một khu vực mới.
        Cập nhật PlayerState, lưu Database và vẽ ảnh nền.
        Trả về đối tượng Location để sử dụng ở các bước tiếp theo.
        """
        # 1. Khởi tạo đối tượng Location từ dữ liệu JSON của LLM
        new_loc_data = await self.location_agent.generate_location(current_location=self.player_state.currentLocation.name,
                                                             target_location= new_location_entered_name,
                                                             context = context)


        new_location = Location(
            id=None,
            name=new_loc_data.get('name', 'Vùng đất vô danh'),
            description=new_loc_data.get('description', ''),
            atmosphere=new_loc_data.get('atmosphere', 'Bình thường')
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
            for name in left_names_set:
                game_logger.info(f" [-] NPC đã rời khỏi phân cảnh: {name}")

        # 2. XỬ LÝ CÁC NPC MỚI XUẤT HIỆN (npcs_arrived)
        if npcs_arrived:
            new_npc_names = []
            current_npc_lowercased = {npc.name.lower() for npc in self.player_state.currentNPCs}

            # Lọc trùng lặp so với trạng thái hiện tại
            for npc_name in npcs_arrived:
                if not npc_name or str(npc_name).strip() == "":
                    continue
                name_clean = npc_name.strip()
                if name_clean.lower() in current_npc_lowercased:
                    continue
                game_logger.info(f" [+] Phát hiện nhân vật xuất hiện: {name_clean}")
                new_npc_names.append(name_clean)

            if new_npc_names:
                # Bước 2.1: Truy vấn CSDL hàng loạt (Batch Query)
                db_npcs = await self.db.get_npc_by_names(new_npc_names, limit=len(new_npc_names))
                self.player_state.currentNPCs.extend(db_npcs)

                # Giải quyết Bug 1 & 2: Ép kiểu lower cho set để tìm kiếm O(1) chính xác
                db_npc_names_lower = {npc.name.lower() for npc in db_npcs}

                # Lọc ra danh sách những cái tên thực sự chưa có trong CSDL
                missing_names = [name for name in new_npc_names if name.lower() not in db_npc_names_lower]



                if missing_names:
                    tasks = [self._generate_and_save_new_npc(context, name) for name in missing_names]
                    generated_npcs = await asyncio.gather(*tasks)  # Kích nổ song song!
                    self.player_state.currentNPCs.extend(generated_npcs)

        # 3. ĐỒNG BỘ ẢNH HIỂN THỊ LÊN GIAO DIỆN (UI)
        if self.player_state.currentNPCs:
            self.player_state.current_npc_image = self.player_state.currentNPCs[-1].image_path
        else:
            self.player_state.current_npc_image = None



    async def _update_inventory(self, items_added: list, items_removed: list):
        """Hàm chuyên xử lý logic túi đồ và tạo/xóa ảnh vật phẩm."""
        if items_added or items_removed:
            game_logger.info("[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")

            # 1. Thêm Item mới -> Vẽ ảnh
            if isinstance(items_added, list):
                for item in items_added:
                    # Kiểm tra item chưa có trong keys của Dictionary
                    if item and item not in self.player_state.inventory:
                        # Gọi Kaggle vẽ ảnh
                        img_path = await self.image_manager.get_or_create_item_image(item)

                        # Lưu vào Dict
                        self.player_state.inventory[item] = img_path
                        game_logger.info(f" [+] Nhận được: {item}")

            # 2. Mất Item cũ -> Xóa ảnh và gỡ khỏi Dict
            if isinstance(items_removed, list):
                for item in items_removed:
                    if item and item in self.player_state.inventory:
                        # Lấy đường dẫn ảnh bằng pop() (vừa lấy vừa xóa khỏi Dict)
                        img_path = self.player_state.inventory.pop(item)

                        # Xóa file vật lý
                        if img_path:
                            self.image_manager.delete_image(img_path)
                        game_logger.info(f" [-] Bị mất: {item}")

            # Lấy danh sách chìa khóa (Tên items) để in ra console
            inventory_status = ", ".join(
                self.player_state.inventory.keys()) if self.player_state.inventory else "Trống rỗng"
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

        atomic_memories_data = results[1] if not isinstance(results[1], Exception) else {}
        if isinstance(results[1], Exception):
            game_logger.error(f"[MemoryExtractor Lỗi] {results[1]}")

        # Chuẩn hóa dữ liệu phòng trường hợp Dict rỗng
        if not isinstance(state_changes, dict): state_changes = {}
        if not isinstance(atomic_memories_data, dict): atomic_memories_data = {}

        atomic_memories = atomic_memories_data.get("atomic_memories", [])
        items_added = state_changes.get("items_added", [])
        items_removed = state_changes.get("items_removed", [])
        npcs_arrived = state_changes.get("npcs_arrived", [])
        npcs_left = state_changes.get("npcs_left", [])
        new_location_entered_name = state_changes.get("new_location_entered",  )

        game_logger.debug(f"[Profile] Background Tasks (State Extraction): {time.perf_counter() - start_bg:.3f}s")

        if new_location_entered_name:
            await self._update_location(new_location_entered_name= new_location_entered_name,
                                    context=context)

        update_tasks = [
            self._update_inventory(items_added= items_added,
                                   items_removed=items_removed),
            self._update_npcs(npcs_arrived = npcs_arrived,
                              npcs_left = npcs_left,
                              context = context)
        ]

        await asyncio.gather(*update_tasks)
        return atomic_memories
