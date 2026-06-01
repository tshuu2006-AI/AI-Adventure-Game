"""Module điều phối việc cập nhật thông tin, trạng thái của trò chơi trong csdl"""
import asyncio
import time
from world.Entity import Location, NPC, Item, Quest
from engine.Agents.LocalAgents import StateExtractor, MemoryExtractor, ItemAgent, QuestAgent
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
        self.item_agent = ItemAgent(model_name="gemini-3.1-flash-lite", pm=pm, gemini_api_key=gemini_api_key)
        self.quest_agent = QuestAgent(model_name="gemini-3.1-flash-lite", pm=pm, gemini_api_key=gemini_api_key)

        self.location_agent = LocationAgent(api_key = groq_api_key,
                                            pm = pm,
                                            model_name = LOCATION_AGENT_MODEL)

        self.npc_agent = NPCAgent(api_key = groq_api_key,
                                  pm = pm,
                                  model_name = NPC_AGENT_MODEL)

        if not hasattr(self.player_state, "active_quests"):
            self.player_state.active_quests = []
        if not hasattr(self.player_state, "available_quests"):
            self.player_state.available_quests = []
        if not hasattr(self.player_state, "completed_quests"):
            self.player_state.completed_quests = []
        if not hasattr(self.player_state, "quest_notifications"):
            self.player_state.quest_notifications = []
        if not hasattr(self.player_state, "quest_branch_active"):
            self.player_state.quest_branch_active = False
        if not hasattr(self.player_state, "current_quest_branch_id"):
            self.player_state.current_quest_branch_id = None
        if not hasattr(self.player_state, "quest_branch_checkpoint"):
            self.player_state.quest_branch_checkpoint = None
        if not hasattr(self.player_state, "quest_branch_title"):
            self.player_state.quest_branch_title = None
        if not hasattr(self.player_state, "quest_branch_story_snapshot"):
            self.player_state.quest_branch_story_snapshot = ""

        self.max_available_quests = 4
        self.max_active_quests = 1


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
                        # Gọi ItemAgent để phân loại vật phẩm
                        item_context = f"Location: {self.player_state.currentLocation.name if self.player_state.currentLocation else ''}"
                        item_spec = await self.item_agent.classify_item(item_name, item_context)

                        # Gọi Kaggle vẽ ảnh
                        img_path = await self.image_manager.get_or_create_item_image(item_name)

                        # Khởi tạo object item theo loại
                        new_item = self.item_agent.build_item_object(item_spec, fallback_name=item_name)
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

    def _push_quest_notification(self, message: str):
        if not message:
            return

        if not hasattr(self.player_state, "quest_notifications"):
            self.player_state.quest_notifications = []

        self.player_state.quest_notifications.append(message)
        self.player_state.quest_notifications = self.player_state.quest_notifications[-10:]
        game_logger.info(f"[Quest Notice] {message}")

    def _serialize_location(self, location: Location):
        if not location:
            return None
        return {
            "id": getattr(location, "id", None),
            "name": getattr(location, "name", None),
            "description": getattr(location, "description", ""),
            "atmosphere": getattr(location, "atmosphere", ""),
            "image_path": getattr(location, "image_path", None),
        }

    def _serialize_npc(self, npc: NPC):
        return {
            "id": getattr(npc, "id", None),
            "name": getattr(npc, "name", None),
            "personality": getattr(npc, "personality", ""),
            "description": getattr(npc, "description", ""),
            "affectionate": getattr(npc, "affectionate", 0),
            "location": getattr(npc, "location", ""),
            "status": getattr(npc, "status", "Bình thường"),
            "image_path": getattr(npc, "image_path", None),
        }

    def _capture_quest_checkpoint(self, quest_title: str = "") -> dict:
        return {
            "location": self._serialize_location(self.player_state.currentLocation),
            "npcs": [self._serialize_npc(npc) for npc in self.player_state.currentNPCs],
            "turn": self.player_state.currentTurn,
            "quest_title": quest_title,
        }

    def _restore_quest_checkpoint(self, checkpoint: dict):
        if not checkpoint:
            return

        location_payload = checkpoint.get("location")
        if location_payload:
            self.player_state.currentLocation = Location(
                id=location_payload.get("id"),
                name=location_payload.get("name", "Vùng đất vô danh"),
                description=location_payload.get("description", ""),
                atmosphere=location_payload.get("atmosphere", "bình thường"),
                image_path=location_payload.get("image_path"),
            )

        npc_payloads = checkpoint.get("npcs", [])
        restored_npcs = []
        for npc_payload in npc_payloads:
            restored_npcs.append(
                NPC(
                    id=npc_payload.get("id"),
                    name=npc_payload.get("name", "Vô danh"),
                    personality=npc_payload.get("personality", "Bí ẩn"),
                    description=npc_payload.get("description", "Không rõ"),
                    affectionate=npc_payload.get("affectionate", 0),
                    location=npc_payload.get("location", ""),
                    status=npc_payload.get("status", "Bình thường"),
                    image_path=npc_payload.get("image_path"),
                )
            )
        self.player_state.currentNPCs = restored_npcs

    async def start_quest_branch(self, quest_index: int) -> tuple[bool, str]:
        if self.player_state.quest_branch_active:
            return False, "Bạn đang ở trong một quest branch rồi."

        if quest_index < 0 or quest_index >= len(self.player_state.available_quests):
            return False, "Quest không hợp lệ."

        quest = self.player_state.available_quests.pop(quest_index)
        checkpoint = self._capture_quest_checkpoint(quest_title=quest.title)

        branch_id = await self.db.create_quest_branch(
            quest_title=quest.title,
            checkpoint=checkpoint,
            started_turn=self.player_state.currentTurn,
            origin_location=checkpoint.get("location", {}).get("name") if checkpoint.get("location") else None,
            quest_status="active",
        )

        quest.branch_id = branch_id
        quest.branch_state = "active"
        quest.status = "active"
        quest.branch_checkpoint = checkpoint
        quest.branch_start_turn = self.player_state.currentTurn
        quest.branch_origin_location = checkpoint.get("location", {}).get("name") if checkpoint.get("location") else None
        quest.branch_origin_npcs = [npc.get("name") for npc in checkpoint.get("npcs", [])]
        quest.branch_story_snapshot = self.player_state.quest_branch_story_snapshot

        self.player_state.active_quests = [quest]
        self.player_state.quest_branch_active = True
        self.player_state.current_quest_branch_id = branch_id
        self.player_state.quest_branch_checkpoint = checkpoint
        self.player_state.quest_branch_title = quest.title

        await self.db.add_quest_event(
            branch_id=branch_id,
            quest_title=quest.title,
            event_type="branch_start",
            description=f"Bắt đầu nhánh quest '{quest.title}'.",
            story_text=quest.branch_story_snapshot,
            location=checkpoint.get("location", {}).get("name") if checkpoint.get("location") else "",
            npc_names=quest.branch_origin_npcs,
            inventory=[item.name for item in self.player_state.inventory],
            turn_number=self.player_state.currentTurn,
        )

        transition_text = (
            f"Bạn tạm rời mạch chính để xử lý quest '{quest.title}'. "
            f"Điểm xuất phát hiện tại được lưu lại để quay về sau khi hoàn tất."
        )
        self._push_quest_notification(transition_text)
        return True, transition_text

    async def capture_main_menu_choices(self, choices: list):
        """Lưu lựa chọn hiện tại từ mạch chính trước khi vào quest"""
        self.player_state.preQuestMainChoices = choices
        game_logger.debug(f"[QuestSystem] Lưu {len(choices)} lựa chọn mạch chính để sử dụng sau quest")

    async def return_from_quest_branch(self, reason: str, reward_item_name: str = None, transition_override: str = None) -> tuple[bool, str]:
        if not self.player_state.quest_branch_active or not self.player_state.active_quests:
            return False, "Không có quest branch nào đang hoạt động."

        quest = self.player_state.active_quests[0]
        checkpoint = quest.branch_checkpoint or self.player_state.quest_branch_checkpoint or {}

        if reason == "completed":
            quest.branch_state = "rewarded" if quest.reward_claimed else "completed"
            quest.status = "completed"
            quest.turn_completed = self.player_state.currentTurn
            quest.branch_end_turn = self.player_state.currentTurn
            if quest not in self.player_state.completed_quests:
                self.player_state.completed_quests.append(quest)
        else:
            quest.branch_state = "paused"
            quest.status = "available"
            if quest not in self.player_state.available_quests:
                self.player_state.available_quests.insert(0, quest)

        self._restore_quest_checkpoint(checkpoint)

        if quest.branch_id is not None:
            await self.db.update_quest_branch(
                branch_id=quest.branch_id,
                quest_status=quest.branch_state,
                checkpoint=checkpoint,
                ended_turn=self.player_state.currentTurn,
                return_reason=reason,
                return_transition=transition_override,
            )

        await self.db.add_quest_event(
            branch_id=quest.branch_id or 0,
            quest_title=quest.title,
            event_type="branch_end",
            description=f"Kết thúc nhánh quest '{quest.title}' với lý do: {reason}.",
            story_text=transition_override or "",
            location=self.player_state.currentLocation.name if self.player_state.currentLocation else "",
            npc_names=[npc.name for npc in self.player_state.currentNPCs],
            inventory=[item.name for item in self.player_state.inventory],
            turn_number=self.player_state.currentTurn,
        )

        self.player_state.active_quests = []
        self.player_state.quest_branch_active = False
        self.player_state.current_quest_branch_id = None
        self.player_state.quest_branch_checkpoint = None
        self.player_state.quest_branch_title = None
        self.player_state.quest_branch_story_snapshot = ""

        if reason == "completed" and reward_item_name:
            return_transition = (
                transition_override
                or f"Sau khi hoàn tất quest '{quest.title}', bạn mang theo phần thưởng '{reward_item_name}' và quay lại mạch truyện chính từ vị trí đã lưu."
            )
        elif reason == "completed":
            return_transition = transition_override or f"Sau khi hoàn tất quest '{quest.title}', bạn quay lại mạch truyện chính từ vị trí đã lưu."
        else:
            return_transition = transition_override or f"Bạn gác quest '{quest.title}' lại và quay về mạch truyện chính từ điểm đã lưu."

        quest.return_transition = return_transition
        self._push_quest_notification(return_transition)
        return True, return_transition

    async def record_active_quest_event(self, player_input: str, story_response: str, episode_data: dict, scene_emotion: str):
        if not self.player_state.quest_branch_active or not self.player_state.active_quests:
            return

        quest = self.player_state.active_quests[0]
        if quest.branch_id is None:
            return

        summary = episode_data.get("result") if isinstance(episode_data, dict) else ""
        if not summary:
            summary = story_response[:400]

        await self.db.add_quest_event(
            branch_id=quest.branch_id,
            quest_title=quest.title,
            event_type="turn",
            description=f"Quest turn: {summary}",
            story_text=story_response,
            location=self.player_state.currentLocation.name if self.player_state.currentLocation else "",
            npc_names=[npc.name for npc in self.player_state.currentNPCs],
            inventory=[item.name for item in self.player_state.inventory],
            turn_number=self.player_state.currentTurn,
        )

    async def _maybe_create_side_quest(self, story_response: str):
        current_location = self.player_state.currentLocation.name if self.player_state.currentLocation else "Chưa xác định"
        current_npcs = ", ".join([npc.name for npc in self.player_state.currentNPCs]) if self.player_state.currentNPCs else "Không có ai"
        inventory = ", ".join([item.name for item in self.player_state.inventory]) if self.player_state.inventory else "Trống rỗng"

        if self.player_state.quest_branch_active:
            return

        if len(self.player_state.available_quests) >= self.max_available_quests:
            return

        quest_data = await self.quest_agent.generate_side_quest(
            story_response=story_response,
            current_location=current_location,
            current_npcs=current_npcs,
            inventory=inventory
        )

        if not quest_data:
            return

        quest = Quest(
            id=None,
            title=quest_data.get("title", "Nhiệm vụ phụ"),
            description=quest_data.get("description", ""),
            objectives=quest_data.get("objectives", []),
            status="available",
            reward_type=quest_data.get("reward", {}).get("item_type", "ConsumableItem"),
            reward_data=quest_data.get("reward", {}),
            linked_npc_names=quest_data.get("linked_npc_names", []),
            linked_location=quest_data.get("linked_location"),
            completion_hint=quest_data.get("completion_hint", ""),
            turn_created=self.player_state.currentTurn,
            branch_state="available",
        )

        self.player_state.available_quests.append(quest)
        game_logger.info(f"[Quest] Nhiệm vụ phụ mới: {quest.title}")
        objectives_text = ", ".join(quest.objectives) if quest.objectives else "Chưa có mục tiêu rõ ràng"
        self._push_quest_notification(f"Nhiệm vụ mới sẵn sàng: {quest.title}. Mục tiêu: {objectives_text}.")

    async def _evaluate_active_quests(self, story_response: str):
        if not self.player_state.active_quests:
            return

        current_location = self.player_state.currentLocation.name if self.player_state.currentLocation else "Chưa xác định"
        current_npcs = ", ".join([npc.name for npc in self.player_state.currentNPCs]) if self.player_state.currentNPCs else "Không có ai"
        inventory = ", ".join([item.name for item in self.player_state.inventory]) if self.player_state.inventory else "Trống rỗng"

        for quest in list(self.player_state.active_quests):
            quest_payload = {
                "title": quest.title,
                "description": quest.description,
                "objectives": quest.objectives,
                "linked_npc_names": quest.linked_npc_names,
                "linked_location": quest.linked_location,
                "difficulty": quest.reward_data.get("difficulty", "easy"),
            }

            evaluation = await self.quest_agent.evaluate_quest(
                quest_data=quest_payload,
                story_response=story_response,
                current_location=current_location,
                current_npcs=current_npcs,
                inventory=inventory,
            )

            if evaluation.get("progress_notes"):
                quest.progress_notes.append(evaluation["progress_notes"])

            if evaluation.get("is_completed") and not quest.reward_claimed:
                reward = evaluation.get("reward") or quest.reward_data
                reward_item = None
                if reward:
                    reward["quest_id"] = quest.id or quest.title
                    reward_item = self.item_agent.build_item_object(reward, fallback_name=reward.get("name", quest.title))
                    img_path = await self.image_manager.get_or_create_item_image(reward_item.name)
                    reward_item.image_path = img_path
                    self.player_state.inventory.append(reward_item)
                    self._push_quest_notification(
                        f"Hoàn thành nhiệm vụ '{quest.title}'. Nhận thưởng: {reward_item.name} ({reward_item.item_type})."
                    )
                else:
                    self._push_quest_notification(f"Hoàn thành nhiệm vụ '{quest.title}'.")

                quest.status = "completed"
                quest.reward_claimed = True
                quest.turn_completed = self.player_state.currentTurn
                game_logger.info(f"[Quest] Hoàn thành nhiệm vụ phụ: {quest.title}")
                await self.return_from_quest_branch(
                    reason="completed",
                    reward_item_name=reward_item.name if reward_item else None,
                    transition_override=(
                        f"Sau khi giải quyết xong quest '{quest.title}', bạn bình tĩnh quay lại điểm đã lưu trong mạch truyện chính."
                    ),
                )


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
            current_loc_name = self.player_state.currentLocation.name if self.player_state.currentLocation else ""
            
            if new_location_entered_name.strip().lower() != current_loc_name.strip().lower():
                await self._update_location(new_location_entered_name=new_location_entered_name, context=context)
            else:
                game_logger.debug(f"[State] Đã ở {current_loc_name}, không cần phân tích tạo lại.")

        update_tasks = [
            self._update_inventory(items_added= items_added,
                                   items_removed=items_removed),
            self._update_npcs(npcs_arrived = npcs_arrived,
                              npcs_left = npcs_left,
                              context = context),
            self._update_affection_and_status(affection_changes=affection_changes)
        ]

        await asyncio.gather(*update_tasks)
        await self.record_active_quest_event(player_input, story_response, atomic_memories, scene_emotion)
        await self._evaluate_active_quests(story_response)
        await self._maybe_create_side_quest(story_response)
        return atomic_memories, scene_emotion
