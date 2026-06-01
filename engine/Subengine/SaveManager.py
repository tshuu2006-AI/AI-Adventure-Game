import os
import shutil
import json
from engine.Utils.logger import game_logger

class SaveManager:
    def serialize_runtime_state(self, orchestrator) -> dict:
        """Thu thập JSON đóng gói từ từng thành phần riêng lẻ"""
        return {
            "player_state": orchestrator.player_state.to_dict(),
            "world_state": orchestrator.world_state.to_dict(),
            "short_term_memory": orchestrator.memory_sys.short_term_memory.to_dict()
        }

    async def save_game(self, orchestrator, slot_name: str):
        save_dir_base = os.path.dirname(orchestrator.db.db_path)
        slot_dir = os.path.join(save_dir_base, slot_name)
        os.makedirs(slot_dir, exist_ok=True)

        # 1. Đóng DB an toàn
        if orchestrator.db.conn:
            await orchestrator.db.conn.commit()
            await orchestrator.db.conn.close()
            orchestrator.db.conn = None

        if hasattr(orchestrator.memory_sys.long_term_memory, 'save_db'):
            orchestrator.memory_sys.long_term_memory.save_db()

        # 2. Copy file vật lý
        if os.path.exists(orchestrator.db.db_path):
            shutil.copy(orchestrator.db.db_path, os.path.join(slot_dir, "eldoria.db"))

        idx_path = orchestrator.memory_sys.long_term_memory.index_path
        meta_path = orchestrator.memory_sys.long_term_memory.meta_path
        if os.path.exists(idx_path): shutil.copy(idx_path, os.path.join(slot_dir, "vector_index.bin"))
        if os.path.exists(meta_path): shutil.copy(meta_path, os.path.join(slot_dir, "vector_meta.pkl"))

        # 3. Bật lại DB
        await orchestrator.db.connect()

        # 4. Lưu RAM State
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

        # 1. Đóng DB để copy đè file
        if orchestrator.db.conn:
            await orchestrator.db.conn.close()
            orchestrator.db.conn = None

        try:
            shutil.copy(os.path.join(slot_dir, "eldoria.db"), orchestrator.db.db_path)

            src_idx = os.path.join(slot_dir, "vector_index.bin")
            if os.path.exists(src_idx): shutil.copy(src_idx, orchestrator.memory_sys.long_term_memory.index_path)

            src_meta = os.path.join(slot_dir, "vector_meta.pkl")
            if os.path.exists(src_meta): shutil.copy(src_meta, orchestrator.memory_sys.long_term_memory.meta_path)
        except Exception as e:
            game_logger.error(f"[SaveSystem] Lỗi copy đè: {e}")
            return False, f"Lỗi ghi đè tệp tin: {e}"

        # 2. Khởi động lại DB & FAISS
        await orchestrator.db.connect()
        if hasattr(orchestrator.memory_sys.long_term_memory, '_load_db'):
            orchestrator.memory_sys.long_term_memory._load_db()

        # 3. Yêu cầu từng Object tự khôi phục dữ liệu
        try:
            with open(os.path.join(slot_dir, "runtime_state.json"), "r", encoding="utf-8") as f:
                state_data = json.load(f)

            # Gọi các hàm load_state vừa tạo
            orchestrator.world_state.load_state(state_data.get("world_state", {}))
            orchestrator.memory_sys.short_term_memory.load_state(state_data.get("short_term_memory", {}))

            # Cập nhật Turn cho Vector Memory
            orchestrator.memory_sys.long_term_memory.game_turn = state_data.get("player_state", {}).get("current_turn",
                                                                                                        0)

            # Do dính dáng tới DB nên load_state của PlayerState cần chạy bất đồng bộ (await)
            await orchestrator.player_state.load_state(
                state_data.get("player_state", {}),
                orchestrator.db,
                orchestrator.image_manager
            )

            return True, "Khôi phục dữ liệu hoàn tất!"
        except Exception as e:
            game_logger.error(f"[SaveSystem] Thất bại khi nạp trạng thái RAM: {e}", exc_info=True)
            return False, "Tệp trạng thái runtime bị lỗi."