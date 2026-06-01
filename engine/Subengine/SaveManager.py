import shutil
import json
import os
from engine.Utils.logger import game_logger
from world.Entity import Item, ConsumableItem, WeaponItem, QuestItem, Quest

class SaveManager():
    def serialize_runtime_state(self, orchestrator) -> dict:
        def serialize_item(item: Item) -> dict:
            return {
                "name": item.name,
                "description": getattr(item, "description", ""),
                "item_type": getattr(item, "item_type", "generic"),
                "effect": getattr(item, "effect", {}),
                "quest_id": getattr(item, "quest_id", None),
            }

        def serialize_quest(quest: Quest) -> dict:
            return {
                "title": quest.title,
                "description": quest.description,
                "objectives": quest.objectives,
                "status": quest.status,
                "lifecycle_state": quest.lifecycle_state(),
                "reward_type": quest.reward_type,
                "reward_data": quest.reward_data,
                "linked_npc_names": quest.linked_npc_names,
                "linked_location": quest.linked_location,
                "progress_notes": quest.progress_notes,
                "completion_hint": quest.completion_hint,
                "reward_claimed": quest.reward_claimed,
                "turn_created": quest.turn_created,
                "turn_completed": quest.turn_completed,
                "branch_id": quest.branch_id,
                "branch_state": quest.branch_state,
                "branch_checkpoint": quest.branch_checkpoint,
                "branch_start_turn": quest.branch_start_turn,
                "branch_end_turn": quest.branch_end_turn,
                "branch_origin_location": quest.branch_origin_location,
                "branch_origin_npcs": quest.branch_origin_npcs,
                "branch_story_snapshot": quest.branch_story_snapshot,
                "return_transition": quest.return_transition,
            }

        return {
            "player_state": {
                "current_turn": orchestrator.player_state.currentTurn,
                "current_location_name": orchestrator.player_state.currentLocation.name if orchestrator.player_state.currentLocation else None,
                "current_npc_names": [npc.name for npc in orchestrator.player_state.currentNPCs],
                "inventory": [serialize_item(item) for item in orchestrator.player_state.inventory],
                "available_quests": [serialize_quest(q) for q in getattr(orchestrator.player_state, "available_quests", [])],
                "active_quests": [serialize_quest(q) for q in getattr(orchestrator.player_state, "active_quests", [])],
                "completed_quests": [serialize_quest(q) for q in getattr(orchestrator.player_state, "completed_quests", [])],
                "quest_notifications": list(getattr(orchestrator.player_state, "quest_notifications", [])),
                "quest_branch_active": getattr(orchestrator.player_state, "quest_branch_active", False),
                "current_quest_branch_id": getattr(orchestrator.player_state, "current_quest_branch_id", None),
                "quest_branch_checkpoint": getattr(orchestrator.player_state, "quest_branch_checkpoint", None),
                "quest_branch_title": getattr(orchestrator.player_state, "quest_branch_title", None),
                "quest_branch_story_snapshot": getattr(orchestrator.player_state, "quest_branch_story_snapshot", ""),
            },
            "world_state": {
                "name": orchestrator.world_state.name,
                "type": orchestrator.world_state.type,
                "theme_and_tone": orchestrator.world_state.theme_and_tone,
                "core_conflict": orchestrator.world_state.core_conflict,
                "mission": orchestrator.world_state.mission,
                "dynamic_vocabulary": orchestrator.world_state.dynamic_vocabulary
            },
            "short_term_memory": {
                "context_window": orchestrator.memory_sys.short_term_memory.context_window,
                "current_structured_memory": orchestrator.memory_sys.short_term_memory.current_structured_memory
            }
        }

    async def save_game(self, orchestrator, slot_name: str):
        save_dir_base = os.path.dirname(orchestrator.db.db_path)
        slot_dir = os.path.join(save_dir_base, slot_name)
        os.makedirs(slot_dir, exist_ok=True)

        # 🌟 SỬA TẠI ĐÂY: Chủ động đóng DB để SQLite ép mọi dữ liệu/bảng từ file WAL vào file .db chính
        if orchestrator.db.conn:
            await orchestrator.db.conn.commit()
            await orchestrator.db.conn.close()
            orchestrator.db.conn = None

        if hasattr(orchestrator.memory_sys.long_term_memory, 'save_db'):
            orchestrator.memory_sys.long_term_memory.save_db()

        # Sao chép an toàn (Lúc này file eldoria.db chắc chắn đã được đồng bộ 100% dữ liệu)
        if os.path.exists(orchestrator.db.db_path):
            shutil.copy(orchestrator.db.db_path, os.path.join(slot_dir, "eldoria.db"))
        
        idx_path = orchestrator.memory_sys.long_term_memory.index_path
        meta_path = orchestrator.memory_sys.long_term_memory.meta_path
        if os.path.exists(idx_path): shutil.copy(idx_path, os.path.join(slot_dir, "vector_index.bin"))
        if os.path.exists(meta_path): shutil.copy(meta_path, os.path.join(slot_dir, "vector_meta.pkl"))

        # 🌟 SỬA TẠI ĐÂY: Mở lại kết nối ngay lập tức để Python sẵn sàng hoạt động tiếp nếu người chơi không thoát game
        await orchestrator.db.connect()

        runtime_data = self.serialize_runtime_state(orchestrator)
        with open(os.path.join(slot_dir, "runtime_state.json"), "w", encoding="utf-8") as f:
            json.dump(runtime_data, f, ensure_ascii=False, indent=4)

        game_logger.info(f"[SaveSystem] Đã lưu thành công vào {slot_name}")

    async def load_game(self, orchestrator, slot_name: str):
        save_dir_base = os.path.dirname(orchestrator.db.db_path)
        slot_dir = os.path.join(save_dir_base, slot_name)

        if not os.path.exists(slot_dir):
            game_logger.error(f"[SaveSystem] Không tìm thấy slot save: {slot_name}")
            return False, "Khe lưu trữ không tồn tại!"

        # Đóng DB an toàn để xả file
        if orchestrator.db.conn:
            await orchestrator.db.conn.close()
            orchestrator.db.conn = None

        target_db_path = orchestrator.db.db_path
        target_faiss_idx = orchestrator.memory_sys.long_term_memory.index_path
        target_faiss_meta = orchestrator.memory_sys.long_term_memory.meta_path

        try:
            src_db = os.path.join(slot_dir, "eldoria.db")
            if os.path.exists(src_db): shutil.copy(src_db, target_db_path)
            
            src_idx = os.path.join(slot_dir, "vector_index.bin")
            if os.path.exists(src_idx): shutil.copy(src_idx, target_faiss_idx)
            
            src_meta = os.path.join(slot_dir, "vector_meta.pkl")
            if os.path.exists(src_meta): shutil.copy(src_meta, target_faiss_meta)
        except Exception as e:
            game_logger.error(f"[SaveSystem] Lỗi copy đè: {e}")
            return False, f"Lỗi ghi đè tệp tin: {e}"

        # Mở lại kết nối
        await orchestrator.db.connect()
        if hasattr(orchestrator.memory_sys.long_term_memory, '_load_db'):
            orchestrator.memory_sys.long_term_memory._load_db()

        try:
            with open(os.path.join(slot_dir, "runtime_state.json"), "r", encoding="utf-8") as f:
                state_data = json.load(f)

            p_state = state_data.get("player_state", {})
            w_state = state_data.get("world_state", {})
            mem_state = state_data.get("short_term_memory", {})

            # Khôi phục WorldState
            orchestrator.world_state.name = w_state.get("name")
            orchestrator.world_state.type = w_state.get("type")
            orchestrator.world_state.theme_and_tone = w_state.get("theme_and_tone")
            orchestrator.world_state.core_conflict = w_state.get("core_conflict")
            orchestrator.world_state.mission = w_state.get("mission")
            orchestrator.world_state.dynamic_vocabulary = w_state.get("dynamic_vocabulary", {})

            # Khôi phục PlayerState
            orchestrator.player_state.currentTurn = p_state.get("current_turn", 0)
            orchestrator.memory_sys.long_term_memory.game_turn = orchestrator.player_state.currentTurn

            # 🌟 Khôi phục Location (Đã sửa để không bị Crash DB)
            loc_name = p_state.get("current_location_name")
            if loc_name:
                all_locs = await orchestrator.db.location_manager.get_all()
                found_loc = next((l for l in all_locs if l.name == loc_name), None)
                if found_loc: orchestrator.player_state.currentLocation = found_loc

            # 🌟 Khôi phục NPC (Đã sửa để không bị Crash DB)
            npc_names = p_state.get("current_npc_names", [])
            if npc_names:
                all_npcs = await orchestrator.db.npc_manager.get_all()
                orchestrator.player_state.currentNPCs = [n for n in all_npcs if n.name in npc_names]
            else:
                orchestrator.player_state.currentNPCs = []

            # Khôi phục Inventory
            orchestrator.player_state.inventory = []
            for item_payload in p_state.get("inventory", []):
                if isinstance(item_payload, str):
                    item_payload = {
                        "name": item_payload,
                        "description": "Vật phẩm khôi phục từ tiến trình lưu.",
                        "item_type": "QuestItem",
                    }

                item_type = item_payload.get("item_type", "QuestItem")
                item_name = item_payload.get("name", "Vật phẩm")
                description = item_payload.get("description", "Vật phẩm khôi phục từ tiến trình lưu.")
                quest_id = item_payload.get("quest_id")

                if item_type == "ConsumableItem":
                    restored_item = ConsumableItem(
                        id=None,
                        name=item_name,
                        description=description,
                        effect=item_payload.get("effect", {}),
                        quest_id=quest_id,
                    )
                elif item_type == "WeaponItem":
                    restored_item = WeaponItem(
                        id=None,
                        name=item_name,
                        description=description,
                        damage=int(item_payload.get("effect", {}).get("damage", item_payload.get("damage", 0)) or 0),
                        rarity=item_payload.get("effect", {}).get("rarity", item_payload.get("rarity", "common")),
                        quest_id=quest_id,
                    )
                elif item_type == "QuestItem":
                    restored_item = QuestItem(
                        id=None,
                        name=item_name,
                        description=description,
                        quest_id=quest_id,
                    )
                else:
                    restored_item = Item(
                        id=None,
                        name=item_name,
                        description=description,
                        item_type=item_type,
                        effect=item_payload.get("effect", {}),
                        quest_id=quest_id,
                    )

                restored_item.quote = "Ký ức mơ hồ..."
                img_filename = orchestrator.image_manager._get_safe_filename(f"item_{item_name}")
                full_img_path = os.path.join(orchestrator.image_manager.item_folder, img_filename)
                if os.path.exists(full_img_path):
                    restored_item.image_path = full_img_path
                orchestrator.player_state.inventory.append(restored_item)

            orchestrator.player_state.available_quests = []
            for quest_payload in p_state.get("available_quests", []):
                quest = Quest(
                    id=None,
                    title=quest_payload.get("title", ""),
                    description=quest_payload.get("description", ""),
                    objectives=quest_payload.get("objectives", []),
                    status=quest_payload.get("status", "available"),
                    reward_type=quest_payload.get("reward_type", "ConsumableItem"),
                    reward_data=quest_payload.get("reward_data", {}),
                    linked_npc_names=quest_payload.get("linked_npc_names", []),
                    linked_location=quest_payload.get("linked_location"),
                    progress_notes=quest_payload.get("progress_notes", []),
                    completion_hint=quest_payload.get("completion_hint", ""),
                    reward_claimed=quest_payload.get("reward_claimed", False),
                    turn_created=quest_payload.get("turn_created", 0),
                    turn_completed=quest_payload.get("turn_completed"),
                    branch_id=quest_payload.get("branch_id"),
                    branch_state=quest_payload.get("branch_state", "available"),
                    branch_checkpoint=quest_payload.get("branch_checkpoint", {}),
                    branch_start_turn=quest_payload.get("branch_start_turn"),
                    branch_end_turn=quest_payload.get("branch_end_turn"),
                    branch_origin_location=quest_payload.get("branch_origin_location"),
                    branch_origin_npcs=quest_payload.get("branch_origin_npcs", []),
                    branch_story_snapshot=quest_payload.get("branch_story_snapshot", ""),
                    return_transition=quest_payload.get("return_transition", ""),
                )
                orchestrator.player_state.available_quests.append(quest)

            # Khôi phục Quest
            orchestrator.player_state.active_quests = []
            for quest_payload in p_state.get("active_quests", []):
                quest = Quest(
                    id=None,
                    title=quest_payload.get("title", ""),
                    description=quest_payload.get("description", ""),
                    objectives=quest_payload.get("objectives", []),
                    status=quest_payload.get("status", "active"),
                    reward_type=quest_payload.get("reward_type", "ConsumableItem"),
                    reward_data=quest_payload.get("reward_data", {}),
                    linked_npc_names=quest_payload.get("linked_npc_names", []),
                    linked_location=quest_payload.get("linked_location"),
                    progress_notes=quest_payload.get("progress_notes", []),
                    completion_hint=quest_payload.get("completion_hint", ""),
                    reward_claimed=quest_payload.get("reward_claimed", False),
                    turn_created=quest_payload.get("turn_created", 0),
                    turn_completed=quest_payload.get("turn_completed"),
                    branch_id=quest_payload.get("branch_id"),
                    branch_state=quest_payload.get("branch_state", "active"),
                    branch_checkpoint=quest_payload.get("branch_checkpoint", {}),
                    branch_start_turn=quest_payload.get("branch_start_turn"),
                    branch_end_turn=quest_payload.get("branch_end_turn"),
                    branch_origin_location=quest_payload.get("branch_origin_location"),
                    branch_origin_npcs=quest_payload.get("branch_origin_npcs", []),
                    branch_story_snapshot=quest_payload.get("branch_story_snapshot", ""),
                    return_transition=quest_payload.get("return_transition", ""),
                )
                orchestrator.player_state.active_quests.append(quest)

            orchestrator.player_state.completed_quests = []
            for quest_payload in p_state.get("completed_quests", []):
                quest = Quest(
                    id=None,
                    title=quest_payload.get("title", ""),
                    description=quest_payload.get("description", ""),
                    objectives=quest_payload.get("objectives", []),
                    status=quest_payload.get("status", "completed"),
                    reward_type=quest_payload.get("reward_type", "ConsumableItem"),
                    reward_data=quest_payload.get("reward_data", {}),
                    linked_npc_names=quest_payload.get("linked_npc_names", []),
                    linked_location=quest_payload.get("linked_location"),
                    progress_notes=quest_payload.get("progress_notes", []),
                    completion_hint=quest_payload.get("completion_hint", ""),
                    reward_claimed=quest_payload.get("reward_claimed", True),
                    turn_created=quest_payload.get("turn_created", 0),
                    turn_completed=quest_payload.get("turn_completed"),
                    branch_id=quest_payload.get("branch_id"),
                    branch_state=quest_payload.get("branch_state", "completed"),
                    branch_checkpoint=quest_payload.get("branch_checkpoint", {}),
                    branch_start_turn=quest_payload.get("branch_start_turn"),
                    branch_end_turn=quest_payload.get("branch_end_turn"),
                    branch_origin_location=quest_payload.get("branch_origin_location"),
                    branch_origin_npcs=quest_payload.get("branch_origin_npcs", []),
                    branch_story_snapshot=quest_payload.get("branch_story_snapshot", ""),
                    return_transition=quest_payload.get("return_transition", ""),
                )
                orchestrator.player_state.completed_quests.append(quest)

            orchestrator.player_state.quest_notifications = p_state.get("quest_notifications", [])
            orchestrator.player_state.quest_branch_active = p_state.get("quest_branch_active", False)
            orchestrator.player_state.current_quest_branch_id = p_state.get("current_quest_branch_id")
            orchestrator.player_state.quest_branch_checkpoint = p_state.get("quest_branch_checkpoint")
            orchestrator.player_state.quest_branch_title = p_state.get("quest_branch_title")
            orchestrator.player_state.quest_branch_story_snapshot = p_state.get("quest_branch_story_snapshot", "")

            # Khôi phục Short term Memory
            orchestrator.memory_sys.short_term_memory.context_window = mem_state.get("context_window", [])
            orchestrator.memory_sys.short_term_memory.current_structured_memory = mem_state.get("current_structured_memory")

            return True, "Khôi phục dữ liệu hoàn tất!"
        except Exception as e:
            game_logger.error(f"[SaveSystem] Thất bại khi nạp trạng thái RAM: {e}")
            return False, "Tệp trạng thái runtime bị lỗi."