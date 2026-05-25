"""Module quản lý cơ sở dữ liệu"""
import os
import sqlite3
import aiosqlite
from typing import List
from world.Entity import *
from engine.Utils.logger import game_logger
from engine.DataManager.EntityManager.MemoryManager import MemoryManager
from engine.DataManager.EntityManager.NPCManager import NPCManager
from engine.DataManager.EntityManager.LocationManager import LocationManager


class DatabaseManager:
    """Lớp quản lý cơ sở dữ liệu"""
    def __init__(self, db_path : str, db_folder : str):
        self.db_path = db_path
        self.db_folder = db_folder
        self.conn = None

        # Khởi tạo các Manager con
        self.npc_manager = NPCManager(db_path, None)
        self.location_manager = LocationManager(db_path, None)
        self.memory_manager = MemoryManager(db_path, None)

    async def connect(self):
        """Mở kết nối tới SQLite với WAL mode để hỗ trợ đọc/ghi đồng thời tốt hơn"""
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute('PRAGMA journal_mode=WAL;')
        await self.conn.execute('PRAGMA foreign_keys = ON;')  # Bật khóa ngoại để bảo vệ toàn vẹn dữ liệu

        # Bơm (inject) kết nối vào các manager con
        self.npc_manager.conn = self.conn
        self.location_manager.conn = self.conn
        self.memory_manager.conn = self.conn
        game_logger.info(f"[Database] Đã mở kết nối bất đồng bộ tới {self.db_path}")

    async def create_tables(self):
        """Khởi tạo các bảng"""
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            game_logger.info(f"[Database] Đã tạo thư mục lưu trữ: {self.db_folder}")

        try:
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS Locations (location_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT NOT NULL, atmosphere TEXT, image_path TEXT)")
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS NPCs (npc_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, personality TEXT, description TEXT, affectionate INTEGER, location TEXT NOT NULL, currentStatus TEXT, image_path TEXT, FOREIGN KEY (location) REFERENCES Locations (name))")
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS Memory (memory_id INTEGER PRIMARY KEY AUTOINCREMENT, made_at INT DEFAULT (unixepoch()), location TEXT NOT NULL, description TEXT NOT NULL, gameturn INT NOT NULL, FOREIGN KEY (location) REFERENCES Locations (name))")

            # Bảng nối (Junction Table) giải quyết quan hệ n-n giữa Ký ức và NPC
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS MEMORY_NPC (npc_id INT, memory_id INT, FOREIGN KEY(npc_id) REFERENCES NPCs(npc_id), FOREIGN KEY(memory_id) REFERENCES Memory(memory_id), PRIMARY KEY (npc_id, memory_id))")
            await self.conn.commit()
            game_logger.info("[Database] Khởi tạo các bảng SQL thành công!")
        except Exception as e:
            game_logger.error(f"[Database Lỗi] Không thể tạo bảng SQL: {e}", exc_info=True)
            await self.conn.rollback()

    async def reset_database(self):
        """Xóa toàn bộ data nhưng giữ lại cấu trúc bảng."""
        if self.conn is None:
            game_logger.error("[Database Lỗi] Không thể reset do chưa mở kết nối (self.conn = None).")
            return

        for table in ["MEMORY_NPC", "Memory", "NPCs", "Locations"]:
            try:
                await self.conn.execute(f"DELETE FROM {table}")
                # Đặt lại bộ đếm ID (AUTOINCREMENT) về 0 thông qua bảng hệ thống sqlite_sequence
                if table != "MEMORY_NPC":
                    await self.conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            except sqlite3.OperationalError as e:
                # Tránh văng lỗi nếu bảng chưa được tạo
                if "no such table" in str(e):
                    game_logger.debug(f"[Database] Bảng '{table}' chưa tồn tại, bỏ qua bước dọn dẹp.")
                else:
                    game_logger.error(f"[Database Lỗi] Lỗi SQLite ở bảng '{table}': {e}")
            except Exception as e:
                game_logger.error(f"[Database Lỗi] Lỗi không xác định ở bảng '{table}': {e}", exc_info=True)

        try:
            await self.conn.commit()
            game_logger.info("[Database] Đã dọn dẹp sạch sẽ toàn bộ dữ liệu SQLite!")
        except Exception as e:
            game_logger.error(f"[Database Lỗi] Lỗi khi lưu thay đổi (commit): {e}", exc_info=True)

    # --- PROXY METHODS (Hàm ủy quyền cho Orchestrator dễ gọi) ---
    async def add_memory_to_db(self, memory_obj: Memory):
        """Thêm memory vào CSDL"""
        res = await self.memory_manager.add_memory(memory_obj)
        await self.conn.commit()
        game_logger.debug(f"[Database] Đã ghi một ký ức mới vào Turn {memory_obj.game_turn}.")
        return res

    async def get_recent_memories_by_npc(self, npc_name: str, limit: int = 5) -> list:
        """Lấy các memory gần dựa trên tên NPC"""
        return await self.memory_manager.get_memory_ids_by_npc_name(npc_name, limit)

    async def get_memories_by_ids(self, memory_ids: List[int]):
        """Lấy các memory dựa trên memory_id"""
        return await self.memory_manager.get_memories_by_ids(memory_ids)

    async def get_npc_by_names(self, npc_names: List[str], limit: int = 3):
        """Lấy các NPC dựa trên tên"""
        return await self.npc_manager.get_by_names(npc_names, limit)

    async def add_npc_to_db(self, npc_obj: NPC):
        """Thêm NPC vào CSDL"""
        res = await self.npc_manager.add_to_db(npc_obj)
        if res: await self.conn.commit()
        return res

    async def get_location_by_names(self, location_names: List[str], limit: int = 3):
        """Lấy các Location bằng tên"""
        return await self.location_manager.get_by_names(location_names, limit)

    async def add_location_to_db(self, location_obj: Location):
        """Thêm Location vào CSDL"""
        res = await self.location_manager.add_to_db(location_obj)
        if res: await self.conn.commit()
        return res

    async def _get_npc_id_by_name(self, npc_name: str):
        async with self.conn.execute("SELECT npc_id FROM NPCs WHERE name = ?", (npc_name,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

    async def link_memory_to_npc(self, npc_name: str, memory_id: int):
        """Tạo mối liên kết giữa Ký ức và NPC để sau này truy xuất RAG theo nhân vật"""
        npc_id = await self._get_npc_id_by_name(npc_name)
        if not npc_id:
            game_logger.warning(f"[Database] Không tìm thấy NPC '{npc_name}' để link với memory #{memory_id}")
            return

        query = "INSERT OR IGNORE INTO MEMORY_NPC (npc_id, memory_id) VALUES (?, ?)"
        await self.conn.execute(query, (npc_id, memory_id))
        await self.conn.commit()


    async def update_npc_state(self, npc_name: str, affection_change: int = 0, new_status: str = None):
        """Cập nhật thiện cảm và/hoặc thể trạng vật lý của NPC"""
        res = await self.npc_manager.update_npc_state(npc_name, affection_change, new_status)
        if res:
            await self.conn.commit()
        return res


    async def search_entities_by_query(self, query: str, limit_per_table: int = 2):
        """Fallback tìm kiếm mờ (Fuzzy Search) khi RAG trả về kết quả không chính xác."""
        if not query: return {'npcs': [], 'locations': []}
        like_q = f"%{query.lower()}%"

        game_logger.debug(f"[Database] Đang tìm kiếm fallback SQL với từ khóa: '{query}'")

        async with self.conn.execute(
                "SELECT npc_id, name, personality, description, affectionate, location, currentStatus, image_path FROM NPCs WHERE LOWER(name) LIKE ? OR LOWER(personality) LIKE ? OR LOWER(description) LIKE ? LIMIT ?",
                (like_q, like_q, like_q, limit_per_table)) as cursor:
            npc_rows = await cursor.fetchall()

        async with self.conn.execute(
                "SELECT location_id, name, description, atmosphere, image_path FROM Locations WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(atmosphere) LIKE ? LIMIT ?",
                (like_q, like_q, like_q, limit_per_table)) as cursor:
            loc_rows = await cursor.fetchall()

        return {
            'npcs': [NPC(id=r[0], name=r[1], personality=r[2], description=r[3], affectionate=r[4], location=r[5],
                         status=r[6], image_path=r[7]) for r in npc_rows],
            'locations': [Location(id=r[0], name=r[1], description=r[2], atmosphere=r[3], image_path=r[4]) for r in
                          loc_rows]
        }


class PlayerState:
    """Đối tượng lưu trữ các trạng thái, vị trí và thông tin theo thời gian thực của người chơi."""


    def __init__(self):
        self.currentLocation = None
        self.currentTurn = 0
        self.currentNPCs = []
        self.inventory = []


class WorldState:
    """Đối tượng lưu trữ các quy tắc bối cảnh (World Bible) đang áp dụng cho phiên chơi hiện tại."""

    def __init__(self):
        self.name = None
        self.type = None
        self.theme_and_tone = None
        self.core_conflict = None
        self.mission = None

        self.dynamic_lore = {}
        self.dynamic_vocabulary = {}