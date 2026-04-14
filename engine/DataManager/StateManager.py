import sqlite3
import time
import os
from typing import Any, Dict, List
from world.Entity import *


class StateManager:
    """
    Trình quản lý Cơ sở dữ liệu (SQLite) cho Game Engine.
    Chịu trách nhiệm lưu trữ và truy xuất trạng thái của NPC, Địa điểm và Ký ức (Memory).
    """

    def __init__(self, db_path='./data/World.db',
                 db_folder='./data',
                 npc_image_path='./data/npc_images',
                 location_image_path='./data/location_images'):

        self.db_path = db_path
        self.db_folder = db_folder
        self.created_at = None
        self.num_locations = 0
        self.num_npc = 0

        self.npc_image_path = npc_image_path
        self.location_image_path = location_image_path

    def _get_connection(self):
        """Mở và trả về kết nối đến file cơ sở dữ liệu SQLite."""
        return sqlite3.connect(self.db_path)

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
            conn = self._get_connection()
            self.created_at = time.time()
            cursor = conn.cursor()
            print("Successfully connected to database!")

            # Khởi tạo bảng danh mục Địa điểm
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Locations
                (
                    location_id
                    INTEGER
                    CONSTRAINT
                    PK_Locations
                    PRIMARY
                    KEY
                    AUTOINCREMENT,
                    name
                    TEXT,
                    description
                    TEXT
                    NOT
                    NULL,
                    currentState
                    TEXT
                )
                """)

            # Khởi tạo bảng quản lý Trạng thái & Hình ảnh của Địa điểm
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Location_states
                (
                    state
                    TEXT,
                    location_name
                    TEXT,
                    image_path
                    TEXT
                    NOT
                    NULL,
                    CONSTRAINT
                    PK_Locations
                    PRIMARY
                    KEY
                (
                    state,
                    location_name
                ),
                    CONSTRAINT FK_state_location FOREIGN KEY
                (
                    location_name
                ) REFERENCES Locations
                (
                    name
                )
                    )
                """)

            # Khởi tạo bảng danh mục NPC
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPCs
                (
                    npc_id
                    TEXT
                    CONSTRAINT
                    PK_NPCs
                    PRIMARY
                    KEY,
                    name
                    TEXT,
                    personality
                    TEXT,
                    description
                    TEXT,
                    affectionLevel
                    INTEGER,
                    location
                    TEXT
                    NOT
                    NULL,
                    currentStatus
                    TEXT,
                    image_path
                    TEXT,
                    CONSTRAINT
                    fk_npc_location
                    FOREIGN
                    KEY
                (
                    location
                ) REFERENCES Locations
                (
                    name
                )
                    )
                """
            )

            # Khởi tạo bảng quản lý Trạng thái & Hình ảnh của NPC
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPC_status
                (
                    npc_id
                    INTEGER,
                    status
                    TEXT,
                    image_path
                    TEXT,
                    CONSTRAINT
                    PK_NPC_Status
                    PRIMARY
                    KEY
                (
                    npc_id,
                    status
                ),
                    CONSTRAINT FK_status_NPC FOREIGN KEY
                (
                    npc_id
                ) REFERENCES NPCs
                (
                    npc_id
                )
                    )
                """
            )

            # Khởi tạo bảng Ký ức (Ghi nhận lại sự kiện lịch sử)
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS Memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    made_at INT DEFAULT (unixepoch() - {self.created_at}),
                    npc TEXT,
                    location TEXT NOT NULL,
                    description TEXT NOT NULL,
                    CONSTRAINT FK_Memory_NPCs FOREIGN KEY (npc) REFERENCES NPCs(name),
                    CONSTRAINT FK_Memory_Locations FOREIGN KEY (location) REFERENCES Locations(name)
                )
                """
            )

            self._ensure_memory_type_column(cursor)

        finally:
            if 'conn' in locals():
                conn.commit()
                conn.close()

    def _ensure_memory_type_column(self, cursor):
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

    def reset_database(self):
        """Xóa sạch dữ liệu trong các bảng và reset bộ đếm ID. Dùng khi tạo Game mới."""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("DELETE FROM NPCs")
        cursor.execute("DELETE FROM Locations")
        cursor.execute("DELETE FROM Memory")

        cursor.execute("DELETE FROM sqlite_sequence WHERE name='NPCs'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='Locations'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='Memory'")

        if hasattr(self, 'num_npc'):
            self.num_npc = 0
        if hasattr(self, 'num_locations'):
            self.num_locations = 0

        conn.commit()
        print("[Database] Đã dọn dẹp sạch sẽ toàn bộ dữ liệu SQL!")

    def add_npc_to_db(self, npc: NPC, location: Location):
        """Lưu trữ thông tin NPC mới vào CSDL nếu tên chưa tồn tại."""
        if not npc or not location:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM NPCs WHERE name = ?", (npc.name,))
        existing_npc = cursor.fetchone()

        image_path = os.path.join(self.npc_image_path, f'{self.num_npc}')
        npc_id = npc.id if getattr(npc, 'id', None) else f"npc_{self.num_npc}"

        if existing_npc is None:
            cursor.execute(
                "INSERT INTO NPCs (npc_id, name, personality, description, affectionLevel, location, currentStatus, image_path) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (npc_id, npc.name, npc.personality, npc.description, npc.affectionate, location.name, npc.status, image_path)
            )

            self.num_npc += 1
            conn.commit()
            return True

        else:
            print(f"NPC có tên '{npc.name}' đã tồn tại trong Database!")
            return False

    def add_location_to_db(self, location):
        """Lưu trữ thông tin Địa điểm mới vào CSDL nếu tên chưa tồn tại."""
        if not location:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute("SELECT 1 FROM Locations WHERE name = ?", (location.name,))
        existing_location = cursor.fetchone()

        if existing_location is None:
            cursor.execute(
                "INSERT INTO Locations (name, description, currentState) VALUES (?, ?, ?)",
                (location.name, location.description, location.state)
            )

            self.num_locations += 1
            conn.commit()
            return True

        else:
            print(f"Địa điểm có tên '{location.name}' đã tồn tại trong Database!")
            return False

    def add_memory_to_db(self, npc_name: str, location_name: str, text: str):
        """
        Lưu diễn biến cốt truyện vào bảng Memory.
        Trả về khóa chính (ID) để có thể đồng bộ ánh xạ sang VectorDB (RAG).
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        now = int(time.time())

        # Chấp nhận cả object (NPC/Location) hoặc string đầu vào.
        npc_value = getattr(npc_name, 'name', npc_name)
        location_value = getattr(location_name, 'name', location_name)

        text_column = self._get_memory_text_column(cursor)

        cursor.execute(
            f"INSERT INTO Memory (made_at, npc, location, {text_column}) VALUES (?, ?, ?, ?)",
            (now, npc_value, location_value, text)
        )

        new_id = cursor.lastrowid

        cursor.execute(
            "UPDATE Memory SET id_type = ? WHERE id = ?",
            ('memory', new_id)
        )

        conn.commit()
        conn.close()

        return new_id, now

    def _get_memory_text_column(self, cursor) -> str:
        """Xác định tên cột lưu text trong bảng Memory để tương thích schema cũ/mới."""
        cursor.execute("PRAGMA table_info(Memory)")
        columns = {row[1] for row in cursor.fetchall()}

        if 'story' in columns:
            return 'story'
        if 'description' in columns:
            return 'description'

        raise ValueError("[Lỗi DB] Bảng Memory không có cột văn bản hợp lệ (story/description).")

    def get_memories_by_ids(self, memory_ids: List[int]) -> List[Dict[str, Any]]:
        """Truy xuất bản ghi Memory theo danh sách ID và giữ đúng thứ tự đầu vào."""
        if not memory_ids:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        text_column = self._get_memory_text_column(cursor)
        placeholders = ", ".join(["?"] * len(memory_ids))

        cursor.execute(
            f"""
            SELECT id, id_type, made_at, npc, location, {text_column} AS text
            FROM Memory
            WHERE id IN ({placeholders})
            """,
            tuple(memory_ids)
        )

        rows = cursor.fetchall()
        conn.close()

        # Ánh xạ theo ID để có thể trả lại đúng thứ tự top-k từ vector search.
        rows_by_id = {
            int(row[0]): {
                'id': int(row[0]),
                'id_type': row[1] if row[1] else 'memory',
                'made_at': row[2],
                'npc': row[3],
                'location': row[4],
                'text': row[5],
            }
            for row in rows
        }

        return [rows_by_id[memory_id] for memory_id in memory_ids if memory_id in rows_by_id]

    def get_npcs_by_names(self, npc_names: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """Truy xuất thông tin NPC theo tên (không phân biệt hoa thường)."""
        # Loại bỏ tên rỗng trước khi query để tránh tạo WHERE IN không cần thiết.
        normalized_names = [name.strip() for name in npc_names if name and str(name).strip()]
        if not normalized_names:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        placeholders = ", ".join(["?"] * len(normalized_names))
        cursor.execute(
            f"""
            SELECT npc_id, name, personality, description, affectionLevel, location, currentStatus
            FROM NPCs
            WHERE LOWER(name) IN ({placeholders})
            LIMIT ?
            """,
            tuple([name.lower() for name in normalized_names] + [limit])
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'id': row[0],
                'id_type': 'npc',
                'name': row[1],
                'personality': row[2],
                'description': row[3],
                'affection_level': row[4],
                'location': row[5],
                'status': row[6],
            }
            for row in rows
        ]

    def get_locations_by_names(self, location_names: List[str], limit: int = 3) -> List[Dict[str, Any]]:
        """Truy xuất thông tin Location theo tên (không phân biệt hoa thường)."""
        # Loại bỏ giá trị rỗng để query gọn và tránh trả về nhiễu.
        normalized_names = [name.strip() for name in location_names if name and str(name).strip()]
        if not normalized_names:
            return []

        conn = self._get_connection()
        cursor = conn.cursor()

        placeholders = ", ".join(["?"] * len(normalized_names))
        cursor.execute(
            f"""
            SELECT location_id, name, description, currentState
            FROM Locations
            WHERE LOWER(name) IN ({placeholders})
            LIMIT ?
            """,
            tuple([name.lower() for name in normalized_names] + [limit])
        )

        rows = cursor.fetchall()
        conn.close()

        return [
            {
                'id': row[0],
                'id_type': 'location',
                'name': row[1],
                'description': row[2],
                'state': row[3],
            }
            for row in rows
        ]

    def search_entities_by_query(self, query: str, limit_per_table: int = 2) -> Dict[str, List[Dict[str, Any]]]:
        """Tìm thực thể liên quan trực tiếp từ query trong bảng NPCs và Locations."""
        query = (query or '').strip()
        if not query:
            return {'npcs': [], 'locations': []}

        # LIKE search này là lớp fallback để bổ sung context ngoài top memory.
        like_query = f"%{query.lower()}%"
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT npc_id, name, personality, description, affectionLevel, location, currentStatus
            FROM NPCs
            WHERE LOWER(name) LIKE ? OR LOWER(personality) LIKE ? OR LOWER(description) LIKE ?
            LIMIT ?
            """,
            (like_query, like_query, like_query, limit_per_table)
        )
        npc_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT location_id, name, description, currentState
            FROM Locations
            WHERE LOWER(name) LIKE ? OR LOWER(description) LIKE ? OR LOWER(currentState) LIKE ?
            LIMIT ?
            """,
            (like_query, like_query, like_query, limit_per_table)
        )
        location_rows = cursor.fetchall()
        conn.close()

        npcs = [
            {
                'id': row[0],
                'id_type': 'npc',
                'name': row[1],
                'personality': row[2],
                'description': row[3],
                'affection_level': row[4],
                'location': row[5],
                'status': row[6],
            }
            for row in npc_rows
        ]

        locations = [
            {
                'id': row[0],
                'id_type': 'location',
                'name': row[1],
                'description': row[2],
                'state': row[3],
            }
            for row in location_rows
        ]

        return {'npcs': npcs, 'locations': locations}


class PlayerState:
    """Đối tượng lưu trữ các trạng thái, vị trí và thông tin theo thời gian thực của người chơi."""

    def __init__(self):
        self.currentLocation = None
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