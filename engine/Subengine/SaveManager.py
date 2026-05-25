import shutil
import json
import os
from engine.Utils.logger import game_logger
from world.Entity import Item

class SaveManager():
    def serialize_runtime_state(self, orchestrator) -> dict:
        return {
            "player_state": {
                "current_turn": orchestrator.player_state.currentTurn,
                "current_location_name": orchestrator.player_state.currentLocation.name if orchestrator.player_state.currentLocation else None,
                "current_npc_names": [npc.name for npc in orchestrator.player_state.currentNPCs],
                "inventory": [item.name for item in orchestrator.player_state.inventory]
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
            for item_name in p_state.get("inventory", []):
                restored_item = Item(id=None, name=item_name, description="Vật phẩm khôi phục từ tiến trình lưu.")
                restored_item.quote = "Ký ức mơ hồ..."
                img_filename = orchestrator.image_manager._get_safe_filename(f"item_{item_name}")
                full_img_path = os.path.join(orchestrator.image_manager.item_folder, img_filename)
                if os.path.exists(full_img_path):
                    restored_item.image_path = full_img_path
                orchestrator.player_state.inventory.append(restored_item)

            # Khôi phục Short term Memory
            orchestrator.memory_sys.short_term_memory.context_window = mem_state.get("context_window", [])
            orchestrator.memory_sys.short_term_memory.current_structured_memory = mem_state.get("current_structured_memory")

            return True, "Khôi phục dữ liệu hoàn tất!"
        except Exception as e:
            game_logger.error(f"[SaveSystem] Thất bại khi nạp trạng thái RAM: {e}")
            return False, "Tệp trạng thái runtime bị lỗi."