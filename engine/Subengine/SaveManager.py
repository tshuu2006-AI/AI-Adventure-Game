import shutil
import json
import os
from engine.Utils.logger import  game_logger
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

        # 1. Ép SQLite và FAISS dump hết dữ liệu từ RAM xuống đĩa cứng hiện tại
        if orchestrator.db.conn:
            await orchestrator.db.conn.commit()
        orchestrator.memory_sys.long_term_memory.save_db()

        # 2. Sao chép các file vật lý vào thư mục Slot
        shutil.copy(orchestrator.db.db_path, os.path.join(slot_dir, "eldoria.db"))
        shutil.copy(orchestrator.memory_sys.long_term_memory.index_path, os.path.join(slot_dir, "vector_index.bin"))
        shutil.copy(orchestrator.memory_sys.long_term_memory.meta_path, os.path.join(slot_dir, "vector_meta.pkl"))

        # 3. Ghi dữ liệu RAM (JSON)
        runtime_data = self.serialize_runtime_state(orchestrator)
        with open(os.path.join(slot_dir, "runtime_state.json"), "w", encoding="utf-8") as f:
            json.dump(runtime_data, f, ensure_ascii=False, indent=4)

        game_logger.info(f"[SaveSystem] Đã lưu thành công vào {slot_name}")

    async def load_game(self, orchestrator, slot_name: str):
        """
        Nhận vào slot_name, tiến hành giải phóng các kết nối đang mở
        và ghi đè toàn bộ tệp tin của slot đó vào db_path cùng hệ thống VectorDB.
        """
        save_dir_base = os.path.dirname(orchestrator.db.db_path)
        slot_dir = os.path.join(save_dir_base, slot_name)

        # 1. Kiểm tra sự tồn tại của thư mục lưu trữ slot
        if not os.path.exists(slot_dir):
            orchestrator.game_logger.error(f"[SaveSystem] Không tìm thấy slot save: {slot_name}")
            return False, "Khe lưu trữ không tồn tại!"

        # 2. Giải phóng kết nối SQLite hiện tại (Bắt buộc để db_path không bị khóa file)
        if orchestrator.db.conn:
            await orchestrator.db.conn.close()
            orchestrator.db.conn = None
            orchestrator.game_logger.debug("[SaveSystem] Đã đóng kết nối SQLite hiện hành để chuẩn bị ghi đè.")

        # 3. Xác định các đường dẫn đích từ thuộc tính/biến cấu hình của hệ thống
        target_db_path = orchestrator.db.db_path
        target_faiss_idx = orchestrator.memory_sys.long_term_memory.index_path
        target_faiss_meta = orchestrator.memory_sys.long_term_memory.meta_path

        # 4. Tiến hành ghi đè toàn bộ dữ liệu vật lý
        try:
            shutil.copy(os.path.join(slot_dir, "eldoria.db"), target_db_path)
            shutil.copy(os.path.join(slot_dir, "vector_index.bin"), target_faiss_idx)
            shutil.copy(os.path.join(slot_dir, "vector_meta.pkl"), target_faiss_meta)
            orchestrator.game_logger.debug(
                f"[SaveSystem] Đã ghi đè toàn bộ file dữ liệu từ '{slot_name}' vào hệ thống.")
        except Exception as e:
            orchestrator.game_logger.error(f"[SaveSystem Lỗi] Không thể sao chép đè dữ liệu: {e}")
            return False, f"Lỗi ghi đè tệp tin vật lý: {e}"

        # 5. Khởi động lại các kết nối dữ liệu sau khi ghi đè hoàn tất
        await orchestrator.db.connect()
        orchestrator.memory_sys.long_term_memory._load_db()

        # 6. Đọc file snapshot runtime_state.json để đồng bộ lại RAM
        try:
            with open(os.path.join(slot_dir, "runtime_state.json"), "r", encoding="utf-8") as f:
                state_data = json.load(f)

            p_state = state_data.get("player_state", {})
            w_state = state_data.get("world_state", {})
            mem_state = state_data.get("short_term_memory", {})

            # --- Khôi phục WorldState ---
            orchestrator.world_state.name = w_state.get("name")
            orchestrator.world_state.type = w_state.get("type")
            orchestrator.world_state.theme_and_tone = w_state.get("theme_and_tone")
            orchestrator.world_state.core_conflict = w_state.get("core_conflict")
            orchestrator.world_state.mission = w_state.get("mission")
            orchestrator.world_state.dynamic_vocabulary = w_state.get("dynamic_vocabulary", {})

            # --- Khôi phục PlayerState ---
            orchestrator.player_state.currentTurn = p_state.get("current_turn", 0)
            orchestrator.memory_sys.long_term_memory.game_turn = orchestrator.player_state.currentTurn

            # Đồng bộ hóa vị trí từ dữ liệu SQLite vừa được ghi đè
            loc_name = p_state.get("current_location_name")
            if loc_name:
                locs = await orchestrator.db.get_location_by_names([loc_name])
                if locs:
                    orchestrator.player_state.currentLocation = locs[0]

            # Đồng bộ hóa danh sách NPC có mặt tại phân cảnh
            npc_names = p_state.get("current_npc_names", [])
            if npc_names:
                orchestrator.player_state.currentNPCs = await orchestrator.db.get_npc_by_names(npc_names)
            else:
                orchestrator.player_state.currentNPCs = []

            # Tái dựng cấu trúc túi đồ (Inventory)
            orchestrator.player_state.inventory = []  # Khởi tạo mảng trống
            for item_name in p_state.get("inventory", []):
                restored_item = Item(id=None, name=item_name, description="Vật phẩm khôi phục từ tiến trình lưu.")
                restored_item.quote = "Ký ức mơ hồ..."

                img_filename = orchestrator.image_manager._get_safe_filename(f"item_{item_name}")
                full_img_path = os.path.join(orchestrator.image_manager.item_folder, img_filename)
                if os.path.exists(full_img_path):
                    restored_item.image_path = full_img_path

                # 🌟 THÊM VÀO LIST THAY VÌ GÁN KEY DICT:
                orchestrator.player_state.inventory.append(restored_item)

            # --- Khôi phục Ngữ cảnh ngắn hạn (Sliding Window Context) ---
            orchestrator.memory_sys.short_term_memory.context_window = mem_state.get("context_window", [])
            orchestrator.memory_sys.short_term_memory.current_structured_memory = mem_state.get(
                "current_structured_memory")

            orchestrator.game_logger.info(
                f"[SaveSystem] Tiến trình game tại slot '{slot_name}' đã được tải thành công.")
            return True, "Khôi phục dữ liệu hoàn tất!"

        except Exception as e:
            orchestrator.game_logger.error(f"[SaveSystem Lỗi] Thất bại khi nạp trạng thái RAM: {e}", exc_info=True)
            return False, "Tệp trạng thái runtime bị lỗi hoặc không đồng bộ."