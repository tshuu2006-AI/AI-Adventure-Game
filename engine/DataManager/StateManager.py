import sqlite3
import time
import os
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

        finally:
            if 'conn' in locals():
                conn.close()

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

        if existing_npc is None:
            cursor.execute(
                "INSERT INTO NPCs (name, personality, description, affectionate, location, currentStatus, image_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (npc.name, npc.personality, npc.description, npc.affectionate, location.id, npc.status, image_path)
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

        cursor.execute(
            "INSERT INTO Memory (made_at, npc, location, story) VALUES (?, ?, ?, ?)",
            (now, npc_name, location_name, text)
        )

        new_id = cursor.lastrowid

        conn.commit()

        return new_id, now


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