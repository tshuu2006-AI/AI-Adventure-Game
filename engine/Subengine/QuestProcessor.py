from engine.DataManager.PlayerState import PlayerState
from engine.Utils.logger import game_logger
from engine.Agents.LocalAgents import QuestAgent


class QuestProcessor:
    """
    Hệ thống điều phối Nhiệm vụ (Quests) và Đa luồng Cốt truyện (Context Stacking).
    Phiên bản kiến trúc Unified Quest Log (Một danh sách nhiệm vụ duy nhất).
    """

    def __init__(self, player_state: PlayerState, pm, gemini_api_key: str):
        self.player_state = player_state
        self.quest_agent = QuestAgent(pm=pm, gemini_api_key=gemini_api_key)

    async def switch_quest(self, target_quest, recent_story, current_choices, force=False):
        # 1. KIỂM TRA ĐIỀU KIỆN
        if not force:
            if target_quest.status in ['failed', 'completed'] or not self.player_state.is_safe_zone:
                return "Không thể nhận nhiệm vụ này lúc này. Hãy chắc chắn bạn đang ở khu vực an toàn."

        if target_quest.status == 'available' or force:
            src_quest = self.player_state.active_quest

            # ==========================================
            # 2. LƯU SNAPSHOT TRƯỚC KHI RỜI ĐI
            # ==========================================
            if src_quest:
                src_quest.snapshot = {
                    "location": self.player_state.currentLocation,
                    "npcs": self.player_state.currentNPCs.copy() if self.player_state.currentNPCs else [],
                    "last_story": recent_story,
                    "last_choices": current_choices
                }

                # Chỉ thay đổi trạng thái nếu nó đang làm dở, KHÔNG remove khỏi mảng
                if src_quest.status == 'in_progress':
                    src_quest.status = 'available'

            # ==========================================
            # 3. SINH LỜI DẪN CHUYỂN CẢNH
            # ==========================================
            transitive_text = await self.quest_agent.generate_transition_narrative(
                source_quest=src_quest,
                target_quest=target_quest,
                recent_story=recent_story
            )

            # ==========================================
            # 4. CHUYỂN ĐỔI SANG QUEST MỚI
            # ==========================================
            target_quest.status = 'in_progress'
            self.player_state.active_quest = target_quest
            self.player_state.update_quest_items()

            # 5. KHÔI PHỤC SNAPSHOT CỦA QUEST ĐÍCH
            if hasattr(target_quest, "snapshot") and target_quest.snapshot:
                snap = target_quest.snapshot
                self.player_state.currentLocation = snap.get("location")
                self.player_state.currentNPCs = snap.get("npcs", [])

            return transitive_text

        return "Nhiệm vụ này không khả dụng."

    # ==========================================
    # NHÓM 3: NGHIỆM THU TIẾN ĐỘ NGẦM
    # ==========================================
    async def evaluate_turn(self, player_input: str, story_response: str) -> bool:
        # Bỏ qua nếu không có quest, hoặc đang ở mạch chính
        if not self.player_state.active_quest or self.player_state.active_quest == getattr(self.player_state,
                                                                                           "main_quest", None):
            return False

        current_quest = self.player_state.active_quest

        # Gọi Agent chấm điểm
        evaluation = await self.quest_agent.evaluate_quest_status(
            quest_title=current_quest.name,
            objectives=getattr(current_quest, "objective", []),
            player_input=player_input,
            story_response=story_response
        )

        status = evaluation.get("status", "in_progress")

        if status in ["completed", "failed"]:
            game_logger.info(f"[QuestSystem] Kết thúc Quest: {current_quest.name} - Trạng thái: {status}")

            # 1. Chỉ cập nhật trạng thái (Nhiệm vụ vẫn nằm trong player_state.quests)
            current_quest.status = status

            # 2. TỰ ĐỘNG PHỤC HỒI MẠCH CHÍNH (Ép chuyển về main_quest)
            game_logger.info("[QuestSystem] Tự động phục hồi mạch truyện chính.")

            await self.switch_quest(
                target_quest=self.player_state.main_quest,
                recent_story=story_response,
                current_choices=[],
                force=True
            )

            return True

        return False

    async def initialize_main_quest(self, world_state, starting_npcs: list):
        """
        Tổng hợp thông tin, gọi Agent sinh Nhiệm vụ chính và lưu vào trạng thái người chơi.
        """
        # 1. Trích xuất danh sách Key NPCs thành chuỗi
        key_npcs_str = "\n".join([f"name: {npc.name} - description: {npc.description} -  personality: {npc.personality}" for npc in starting_npcs])
        if not key_npcs_str:
            key_npcs_str = "Chưa có thông tin về các thế lực trong thế giới này."

        # 2. Gọi Agent sinh cốt truyện chiến dịch
        quest_data = await self.quest_agent.initialize_main_quest(
            world_name=world_state.name,
            world_theme=world_state.theme_and_tone,
            world_conflict=world_state.core_conflict,
            world_mission=world_state.world_mission,
            key_npcs=key_npcs_str
        )

        # 3. Trích xuất dữ liệu an toàn
        title = quest_data.get("title", f"Hành trình tại {world_state.name}")
        description = quest_data.get("description", "Vận mệnh của bạn chưa được định đoạt.")
        objectives = quest_data.get("objectives", ["Sống sót"])
        give_by = quest_data.get("give_by", "Vận mệnh")

        # 4. Tạo Object Quest
        from world.Entity import Quest
        main_quest = Quest(
            id=0,
            name=title,
            description=description,
            objective=objectives,
            give_by=give_by,
            rewards=[]
        )
        main_quest.status = 'in_progress'

        # 5. Lưu vào PlayerState
        self.player_state.main_quest = main_quest
        self.player_state.active_quest = main_quest
        if main_quest not in self.player_state.quests:
            self.player_state.quests.append(main_quest)

        game_logger.info(f"[QuestSystem] Đã thiết lập Hành trình chính: '{main_quest.name}'")
        return main_quest

