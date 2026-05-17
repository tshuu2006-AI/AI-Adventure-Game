import os
import json
import aiosqlite
from typing import List
from world.Entity import *
from engine.Utils.logger import game_logger


class BaseManager:
    """Lớp cha cung cấp kết nối và các công cụ tiện ích cho CSDL."""

    def __init__(self, db_path: str, connection):
        self.db_path = db_path
        self.conn = connection
        self.table_name = ''

    def reset(self):
        raise NotImplementedError

    async def _fetch_records_by_names(self, query_template: str, names: List[str], limit: int) -> list:
        normalized_names = [name.strip() for name in names if name and str(name).strip()]
        if not normalized_names: return []

        placeholders = ", ".join(["?"] * len(normalized_names))
        final_query = query_template.format(placeholders=placeholders)
        params = (*[name.lower() for name in normalized_names], limit)

        async with self.conn.execute(final_query, params) as cursor:
            return await cursor.fetchall()

    async def add_to_db(self, entity: BaseEntity):
        if not entity: return False

        # 1. Kiểm tra tồn tại sử dụng async context manager
        async with self.conn.execute(f"SELECT 1 FROM {self.table_name} WHERE LOWER(name) = ?",
                                     (entity.name.lower(),)) as cursor:
            if await cursor.fetchone() is not None:
                game_logger.debug(f"[{self.table_name}] Đối tượng '{entity.name}' đã tồn tại, bỏ qua lưu mới.")
                return False

        # 2. Lấy data từ lớp con (Hàm này giờ phải là async)
        insert_query, raw_params = await self._get_insert_data(entity)

        # 3. Ép kiểu JSON
        processed_params = [json.dumps(p, ensure_ascii=False) if isinstance(p, (list, dict)) else p for p in raw_params]

        await self.conn.execute(insert_query, tuple(processed_params))
        game_logger.debug(f"[{self.table_name}] Đã lưu thành công '{entity.name}'.")
        return True


class NPCManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'NPCs'

    async def _get_insert_data(self, npc: NPC):
        query = f"INSERT INTO {self.table_name} (name, personality, description, affectionate, location, currentStatus, image_path) VALUES (?, ?, ?, ?, ?, ?, ?)"
        params = (npc.name, npc.personality, npc.description, npc.affectionate, npc.location, npc.status,
                  npc.image_path)
        return query, params

    async def get_by_names(self, npc_names: List[str], limit: int = 3) -> List[NPC]:
        query_template = "SELECT npc_id, name, personality, description, affectionate, location, currentStatus, image_path FROM NPCs WHERE LOWER(name) IN ({placeholders}) LIMIT ?"
        npc_rows = await self._fetch_records_by_names(query_template, npc_names, limit)
        return [
            NPC(id=r[0],
                name=r[1],
                personality=r[2],
                description=r[3],
                affectionate=r[4],
                location=r[5],
                status=r[6],
                image_path=r[7]) for r in npc_rows]


class LocationManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'Locations'

    async def _get_insert_data(self, location: Location):
        query = f"INSERT INTO {self.table_name} (name, description, atmosphere, image_path) VALUES (?, ?, ?, ?)"
        params = (location.name, location.description, location.atmosphere, location.image_path)
        return query, params

    async def get_by_names(self, location_names: List[str], limit: int = 3) -> List[Location]:
        query_template = "SELECT location_id, name, description, atmosphere, image_path FROM Locations WHERE LOWER(name) IN ({placeholders}) LIMIT ?"
        location_rows = await self._fetch_records_by_names(query_template, location_names, limit)
        return [Location(id=r[0], name=r[1], description=r[2], atmosphere=r[3], image_path=r[4]) for r in location_rows]


class MemoryManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'Memory'

    async def ensure_memory_type_column(self):
        async with self.conn.execute(f"PRAGMA table_info({self.table_name})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}

        if 'id_type' not in columns:
            game_logger.debug(f"[{self.table_name}] Đang cập nhật schema, thêm cột 'id_type'...")
            await self.conn.execute(f"ALTER TABLE {self.table_name} ADD COLUMN id_type TEXT DEFAULT 'memory'")

        await self.conn.execute(f"UPDATE {self.table_name} SET id_type = COALESCE(id_type, 'memory')")
        await self.conn.commit()

    async def _get_memory_text_column(self) -> str:
        async with self.conn.execute(f"PRAGMA table_info({self.table_name})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        return 'story' if 'story' in columns else 'description'

    async def add_memory(self, memory_obj: Memory) -> int:
        text_column = await self._get_memory_text_column()
        query = f"INSERT INTO {self.table_name} (npc, location, {text_column}, gameturn, id_type) VALUES (?, ?, ?, ?, ?)"

        async with self.conn.execute(query, (memory_obj.npc, memory_obj.location, memory_obj.text, memory_obj.game_turn,
                                             memory_obj.id_type)) as cursor:
            new_id = cursor.lastrowid
            memory_obj.id = new_id
            return new_id

    async def get_memories_by_ids(self, memory_ids: List[int]) -> List[Memory]:
        if not memory_ids: return []
        text_column = await self._get_memory_text_column()
        placeholders = ", ".join(["?"] * len(memory_ids))
        query = f"SELECT id, id_type, npc, location, {text_column}, gameturn FROM {self.table_name} WHERE id IN ({placeholders})"

        async with self.conn.execute(query, tuple(memory_ids)) as cursor:
            rows = await cursor.fetchall()

        rows_by_id = {
            r[0]: Memory(id=r[0], id_type=r[1] or 'memory', npc=r[2], location=r[3], text=r[4], game_turn=r[5]) for r in
            rows}
        return [rows_by_id[m_id] for m_id in memory_ids if m_id in rows_by_id]


class DatabaseManager:
    def __init__(self, db_path='./data/World.db', db_folder='./data'):
        self.db_path = db_path
        self.db_folder = db_folder
        self.conn = None
        self.npc_manager = NPCManager(db_path, None)
        self.location_manager = LocationManager(db_path, None)
        self.memory_manager = MemoryManager(db_path, None)

    async def connect(self):
        self.conn = await aiosqlite.connect(self.db_path)
        await self.conn.execute('PRAGMA journal_mode=WAL;')
        await self.conn.execute('PRAGMA foreign_keys = ON;')
        self.npc_manager.conn = self.conn
        self.location_manager.conn = self.conn
        self.memory_manager.conn = self.conn
        game_logger.info(f"[Database] Đã mở kết nối bất đồng bộ tới {self.db_path}")

    async def create_tables(self):
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            game_logger.info(f"[Database] Đã tạo thư mục lưu trữ: {self.db_folder}")

        try:
            # Sử dụng await self.conn.execute trực tiếp cho các bảng
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS Locations (location_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, description TEXT NOT NULL, atmosphere TEXT, image_path TEXT)")
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS NPCs (npc_id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, personality TEXT, description TEXT, affectionate INTEGER, location TEXT NOT NULL, currentStatus TEXT, image_path TEXT, FOREIGN KEY (location) REFERENCES Locations (name))")
            await self.conn.execute(
                "CREATE TABLE IF NOT EXISTS Memory (id INTEGER PRIMARY KEY AUTOINCREMENT, made_at INT DEFAULT (unixepoch()), npc TEXT, location TEXT NOT NULL, description TEXT NOT NULL, gameturn INT NOT NULL, FOREIGN KEY (npc) REFERENCES NPCs (name), FOREIGN KEY (location) REFERENCES Locations (name))")

            await self.memory_manager.ensure_memory_type_column()
            await self.conn.commit()
            game_logger.info("[Database] Khởi tạo các bảng SQL thành công!")
        except Exception as e:
            game_logger.error(f"[Database Lỗi] Không thể tạo bảng SQL: {e}", exc_info=True)
            await self.conn.rollback()

    async def reset_database(self):
        if self.conn is None:
            game_logger.error("[Database Lỗi] Không thể reset do chưa mở kết nối (self.conn = None).")
            return

        try:
            for table in ["Memory", "NPCs", "Locations"]:
                await self.conn.execute(f"DELETE FROM {table}")
                await self.conn.execute(f"DELETE FROM sqlite_sequence WHERE name='{table}'")
            await self.conn.commit()
            game_logger.info("[Database] Đã dọn dẹp sạch sẽ toàn bộ dữ liệu SQLite!")
        except Exception as e:
            game_logger.error(f"[Database Lỗi] Xảy ra sự cố khi dọn dẹp CSDL: {e}", exc_info=True)

    # --- PROXY METHODS (Hàm ủy quyền) ---
    async def add_memory_to_db(self, memory_obj: Memory):
        res = await self.memory_manager.add_memory(memory_obj)
        await self.conn.commit()
        game_logger.debug(f"[Database] Đã ghi một ký ức mới vào Turn {memory_obj.game_turn}.")
        return res

    async def get_memories_by_ids(self, memory_ids: List[int]):
        return await self.memory_manager.get_memories_by_ids(memory_ids)

    async def get_npc_by_names(self, npc_names: List[str], limit: int = 3):
        return await self.npc_manager.get_by_names(npc_names, limit)

    async def add_npc_to_db(self, npc_obj: NPC):
        res = await self.npc_manager.add_to_db(npc_obj)
        if res: await self.conn.commit()
        return res

    async def get_location_by_names(self, location_names: List[str], limit: int = 3):
        return await self.location_manager.get_by_names(location_names, limit)

    async def add_location_to_db(self, location_obj: Location):
        res = await self.location_manager.add_to_db(location_obj)
        if res: await self.conn.commit()
        return res

    async def search_entities_by_query(self, query: str, limit_per_table: int = 2):
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
        self.inventory = {}


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