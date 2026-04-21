import sqlite3
import os
import json 
from typing import Dict, List, Union
from world.Entity import *

class BaseManager:
    """Lớp cha cung cấp kết nối và các công cụ tiện ích cho CSDL."""
    def __init__(self, db_path: str, connection):
        self.db_path = db_path
        self.conn = connection
        self.table_name = ''


    def reset(self):
        raise NotImplementedError

    def _fetch_records_by_names(self, query_template: str, names: List[str], limit: int) -> list:
        """Hàm Helper dùng chung để tránh lặp code khi tìm kiếm theo tên."""
        normalized_names = [name.strip() for name in names if name and str(name).strip()]
        if not normalized_names: return []

        placeholders = ", ".join(["?"] * len(normalized_names))
        final_query = query_template.format(placeholders=placeholders)

        with self.conn:  # Tự động commit/rollback
            cursor = self.conn.cursor()
            params = (*[name.lower() for name in normalized_names], limit)
            cursor.execute(final_query, params)
            return cursor.fetchall()


    def _get_insert_data(self, entity):
        raise NotImplementedError


    def add_to_db(self, entity: BaseEntity):
        if not entity:
            return False

        cursor = self.conn.cursor()

        # 1. Kiểm tra tồn tại
        cursor.execute(f"SELECT 1 FROM {self.table_name} WHERE LOWER(name) = ?", (entity.name.lower(),))
        if cursor.fetchone() is not None:
            print(f"[{self.table_name}] Đối tượng có tên '{entity.name}' đã tồn tại!")
            return False

        # 2. Lấy câu SQL và Dữ liệu nguyên thủy từ lớp con
        insert_query, raw_params = self._get_insert_data(entity)

        # ========================================================
        # 3. ÉP KIỂU TỰ ĐỘNG (Sửa lỗi "type 'list' is not supported")
        # ========================================================
        processed_params = []
        for param in raw_params:
            if isinstance(param, (list, dict)):
                # Biến list/dict thành chuỗi JSON, giữ nguyên tiếng Việt
                processed_params.append(json.dumps(param, ensure_ascii=False))
            else:
                # Giữ nguyên nếu là string, int, float...
                processed_params.append(param)
        
        # Chuyển lại thành tuple để SQLite đọc được
        final_params = tuple(processed_params)
        # ========================================================

        # 4. Thực thi chèn dữ liệu
        cursor.execute(insert_query, final_params)
        return True


    def get_by_names(self, npc_names: List[str], limit: int = 3):
        raise NotImplementedError


class NPCManager(BaseManager):

    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.num_npc = 0
        self.table_name = 'NPCs'


    def reset(self):
        self.num_npc = 0


    def _get_insert_data(self, npc: NPC):
        query = """
                INSERT INTO NPCs (name, personality, description, affectionate, location, currentStatus, image_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
        params = (npc.name, npc.personality, npc.description, npc.affectionate, npc.location, npc.status,
                  npc.image_path)
        self.num_npc += 1  # Tăng biến đếm

        return query, params


    def get_by_names(self, npc_names: List[str], limit: int = 3) -> List[NPC]:
        """Truy xuất thông tin NPC theo tên (không phân biệt hoa thường)."""
        query_template = """
            SELECT npc_id, name, personality, description, affectionLevel, location, currentStatus, image_path 
            FROM NPCs
            WHERE LOWER(name) IN ({placeholders})
            LIMIT ?
            """
        npc_rows = self._fetch_records_by_names(query_template=query_template, names=npc_names, limit = limit)

        npcs = [NPC(id = row[0],
                    name = row[1],
                    personality=row[2],
                    description=row[3],
                    affectionate=row[4],
                    location = row[5],
                    status = row[6],
                    image_path=row[7])
                for row in npc_rows]

        return npcs


class LocationManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.num_location = 0
        self.table_name = 'Locations'


    def reset(self):
        self.num_location = 0


    def _get_insert_data(self, location: Location):
        """Cung cấp nguyên liệu INSERT cho lớp cha."""
        query = """
            INSERT INTO Locations (name, description, currentState, image_path) 
            VALUES (?, ?, ?, ?)
        """
        params = (location.name, location.description, location.state, location.image_path)
        self.num_location += 1 #
        return query, params


    def get_by_names(self, location_names: List[str], limit: int = 3) -> List[Location]:
        """Truy xuất thông tin Location theo tên (không phân biệt hoa thường)."""
        query_template = """
                         SELECT location_id, name, description, currentState, image_path
                         FROM Locations
                         WHERE LOWER(name) IN ({placeholders}) LIMIT ? \
                         """
        location_rows = self._fetch_records_by_names(query_template=query_template, names=location_names, limit=limit)

        locations = [Location(id=row[0],
                              name=row[1],
                              description=row[2],
                              state=row[3],
                              image_path=row[4])
                     for row in location_rows]

        return locations


class MemoryManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'Memory'


    def reset(self):
        """Reset các thông số nội bộ của Ký ức (nếu có)."""
        pass


    def ensure_memory_type_column(self, cursor):
        """Bổ sung cột id_type cho bảng Memory và backfill dữ liệu cũ."""
        cursor.execute("PRAGMA table_info(Memory)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'id_type' not in columns:
            cursor.execute("ALTER TABLE Memory ADD COLUMN id_type TEXT DEFAULT 'memory'")

        cursor.execute(
            """
            UPDATE Memory
            SET
                id_type = COALESCE(id_type, 'memory')
            """
        )


    def _get_memory_text_column(self, cursor) -> str:
        """Helper: Xác định tên cột lưu text để tương thích với CSDL cũ/mới."""
        cursor.execute(f"PRAGMA table_info({self.table_name})")
        columns = {row[1] for row in cursor.fetchall()}

        if 'story' in columns:
            return 'story'
        if 'description' in columns:
            return 'description'

        raise ValueError("[Lỗi DB] Bảng Memory không có cột văn bản hợp lệ (story/description).")

    def add_memory(self, memory_obj: Memory) -> int:
        """
        Nhận vào một đối tượng Memory (dataclass) và lưu xuống CSDL.
        """
        cursor = self.conn.cursor()
        text_column = self._get_memory_text_column(cursor)

        # 1. Chèn dữ liệu trực tiếp từ các thuộc tính của Object
        cursor.execute(
            f"INSERT INTO {self.table_name} (made_at, npc, location, {text_column}) VALUES (?, ?, ?, ?)",
            (memory_obj.made_at, memory_obj.npc, memory_obj.location, memory_obj.text)
        )

        # 2. Lấy ID do SQLite vừa tự động cấp
        new_id = cursor.lastrowid

        # 3. Cập nhật ngược ID này lại vào Object ban đầu
        # (Để code bên ngoài có thể biết Object này mang ID số mấy)
        memory_obj.id = new_id

        # 4. Cập nhật id_type
        cursor.execute(
            f"UPDATE {self.table_name} SET id_type = ? WHERE id = ?",
            (memory_obj.id_type, new_id)
        )

        return new_id

    def get_memories_by_ids(self, memory_ids: List[int]) -> List[Memory]:
        """
        Truy xuất Ký ức theo danh sách ID.
        Trả về danh sách các đối tượng Memory (thay vì Dictionary cục mịch như xưa).
        """
        if not memory_ids:
            return []

        cursor = self.conn.cursor()
        text_column = self._get_memory_text_column(cursor)
        placeholders = ", ".join(["?"] * len(memory_ids))

        cursor.execute(
            f"""
            SELECT id, id_type, made_at, npc, location, {text_column} AS text
            FROM {self.table_name}
            WHERE id IN ({placeholders})
            """,
            tuple(memory_ids)
        )

        rows = cursor.fetchall()

        # Ánh xạ Tuple của SQLite thành Object Memory
        rows_by_id = {}
        for row in rows:
            mem_id = int(row[0])
            mem_obj = Memory(
                id=mem_id,
                id_type=row[1] if row[1] else 'memory',
                made_at=row[2],
                npc=row[3],
                location=row[4],
                text=row[5]
            )
            rows_by_id[mem_id] = mem_obj

        # Trả về danh sách Object, giữ nguyên thứ tự sắp xếp (phục vụ RAG/VectorDB)
        return [rows_by_id[mem_id] for mem_id in memory_ids if mem_id in rows_by_id]


class DatabaseManager:
    """
    Trình quản lý Cơ sở dữ liệu (SQLite) cho Game Engine.
    Chịu trách nhiệm lưu trữ và truy xuất trạng thái của NPC, Địa điểm và Ký ức (Memory).
    """

    def __init__(self, db_path='./data/World.db', db_folder='./data'):

        self.db_path = db_path
        self.db_folder = db_folder
        self.conn = self._get_connection()
        self.npc_manager = NPCManager(db_path, self.conn)
        self.location_manager = LocationManager(db_path, self.conn)
        self.memory_manager = MemoryManager(db_path, self.conn)
        self.created_at = None


    def _get_connection(self):
        """Mở kết nối an toàn với WAL mode."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute('PRAGMA journal_mode=WAL;')
        conn.execute('PRAGMA foreign_keys = ON;')
        return conn


    def create_tables(self):
        """
        Khởi tạo cấu trúc cơ sở dữ liệu.
        Tạo thư mục chứa data nếu chưa có, và tự động tạo các bảng cần thiết.
        """
        # Đảm bảo thư mục lưu trữ tồn tại
        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            print(f"Folder was created: {self.db_folder}")

        try:
            self.created_at = time.time()
            cursor = self.conn.cursor()
            print("Successfully connected to database!")

            # Khởi tạo bảng danh mục Địa điểm
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Locations
                (
                    location_id INTEGER CONSTRAINT PK_Locations PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE,
                    description TEXT NOT NULL,
                    currentState TEXT,
                    image_path TEXT
                )
                """)

            # Khởi tạo bảng quản lý Trạng thái & Hình ảnh của Địa điểm
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Location_states
                (
                    state TEXT,  
                    location_name TEXT, image_path TEXT NOT NULL, 
                    CONSTRAINT PK_Locations PRIMARY KEY (state, location_name), 
                    CONSTRAINT FK_state_location FOREIGN KEY(location_name) REFERENCES Locations(name))
                """)

            # Khởi tạo bảng danh mục NPC
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPCs
                (
                    npc_id INTEGER CONSTRAINT PK_NPCs PRIMARY KEY AUTOINCREMENT, 
                    name TEXT UNIQUE,
                    personality TEXT,
                    description TEXT,
                    affectionLevel INTEGER,
                    location TEXT NOT NULL,
                    currentStatus TEXT,
                    image_path TEXT,
                    CONSTRAINT fk_npc_location FOREIGN KEY (location) REFERENCES Locations (name)
                )
                """
            )

            # Khởi tạo bảng quản lý Trạng thái & Hình ảnh của NPC
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPC_status
                (
                    npc_id INTEGER,
                    status TEXT,
                    image_path TEXT,
                    CONSTRAINT PK_NPC_Status PRIMARY KEY (npc_id,status),
                    CONSTRAINT FK_status_NPC FOREIGN KEY (npc_id) REFERENCES NPCs(npc_id)
                    )
                """
            )

            # Khởi tạo bảng Ký ức (Ghi nhận lại sự kiện lịch sử)
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS Memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    made_at INT DEFAULT (unixepoch()),
                    npc TEXT,
                    location TEXT NOT NULL,
                    description TEXT NOT NULL,
                    CONSTRAINT FK_Memory_NPCs FOREIGN KEY (npc) REFERENCES NPCs(name),
                    CONSTRAINT FK_Memory_Locations FOREIGN KEY (location) REFERENCES Locations(name)
                )
                """
            )

            self.memory_manager.ensure_memory_type_column(cursor)
            self.conn.commit()


        except Exception as e:
            print(f"[Database Lỗi] Không thể khởi tạo cấu trúc CSDL: {e}")
            self.conn.rollback()  # Rollback ngay nếu có lỗi


    def reset_database(self):
        """Xóa sạch dữ liệu trong các bảng và reset bộ đếm ID. Dùng khi tạo Game mới."""
        cursor = self.conn.cursor()
        try:
            cursor.execute("DELETE FROM Memory")
            cursor.execute("DELETE FROM NPCs")
            cursor.execute("DELETE FROM Locations")

            cursor.execute("DELETE FROM sqlite_sequence WHERE name='Memory'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='NPCs'")
            cursor.execute("DELETE FROM sqlite_sequence WHERE name='Locations'")

            print("[Database] Đã dọn dẹp sạch sẽ toàn bộ dữ liệu SQL!")
        except Exception as loi_he_thong:
            print(f"[Database] Bỏ qua dọn dẹp do cấu trúc chưa tồn tại. Lỗi: {loi_he_thong}")

        self.location_manager.reset()
        self.npc_manager.reset()
        self.memory_manager.reset()

        self.conn.commit()
        print("[Database] Đã dọn dẹp sạch sẽ toàn bộ dữ liệu SQL!")


    def add_memory_to_db(self, memory_obj: Memory):
        """
        Lưu diễn biến cốt truyện vào bảng Memory.
        Trả về khóa chính (ID) để có thể đồng bộ ánh xạ sang VectorDB (RAG).
        """
        new_id = self.memory_manager.add_memory(memory_obj)
        self.conn.commit()  # Chốt sổ an toàn
        return new_id


    def get_memories_by_ids(self, memory_ids: List[int]) -> List[Memory]:
        """Truy xuất bản ghi Memory theo danh sách ID và giữ đúng thứ tự đầu vào."""
        memories = self.memory_manager.get_memories_by_ids(memory_ids)
        return memories


    def get_npc_by_names(self, npc_names: List[str], limit: int = 3):
        npcs = self.npc_manager.get_by_names(npc_names, limit)
        return npcs


    def add_npc_to_db(self, npc_obj: NPC) -> bool:
        """Uỷ quyền lưu NPC và chốt sổ."""
        success = self.npc_manager.add_to_db(npc_obj)
        if success:
            self.conn.commit()  # <--- CHỐT SỔ TẠI ĐÂY
        return success


    def get_location_by_names(self, location_names: List[str], limit: int = 3):
        locations = self.location_manager.get_by_names(location_names, limit)
        return locations

    def add_location_to_db(self, location_obj: Location) -> bool:
        """Uỷ quyền lưu Địa điểm và chốt sổ."""
        success = self.location_manager.add_to_db(location_obj)
        if success:
            self.conn.commit()  # <--- CHỐT SỔ TẠI ĐÂY
        return success


    def search_entities_by_query(self, query: str, limit_per_table: int = 2) -> Dict[str, List[Union[NPC, Location]]]:
        """Tìm thực thể liên quan trực tiếp từ query trong bảng NPCs và Locations."""
        query = (query or '').strip()
        if not query:
            return {'npcs': [], 'locations': []}

        # LIKE search này là lớp fallback để bổ sung context ngoài top memory.
        like_query = f"%{query.lower()}%"
        cursor = self.conn.cursor()

        cursor.execute(
            """
            SELECT npc_id, name, personality, description, affectionLevel, location, currentStatus, image_path 
            FROM NPCs
            WHERE LOWER(name) LIKE ? OR LOWER(personality) LIKE ? OR LOWER(description) LIKE ?
            LIMIT ?
            """,
            (like_query, like_query, like_query, limit_per_table)
        )
        npc_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT location_id, name, description, currentState, image_path
            FROM Locations
            WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(currentState) LIKE ?
            LIMIT ?
            """,
            (like_query, like_query, like_query, limit_per_table)
        )
        location_rows = cursor.fetchall()

        npcs = [NPC(id=row[0],
                    name=row[1],
                    personality=row[2],
                    description=row[3],
                    affectionate=row[4],
                    location=row[5],
                    status=row[6],
                    image_path=row[7])
                for row in npc_rows]

        locations = [Location(id=row[0],
                              name=row[1],
                              description=row[2],
                              state=row[3],
                              image_path=row[4])
                     for row in location_rows]

        return {'npcs': npcs, 'locations': locations}


class PlayerState:
    """Đối tượng lưu trữ các trạng thái, vị trí và thông tin theo thời gian thực của người chơi."""

    def __init__(self):
        self.currentLocation = None
        self.inventory = {}
        self.active_quests = {}
        self.completed_quests = []


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

