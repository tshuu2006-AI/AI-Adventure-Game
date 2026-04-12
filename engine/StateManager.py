import sqlite3
import time
import os
from world.Entity import *

class StateManager:
    def __init__(self, db_path='./data/World.db',
                 db_folder = './data',
                 npc_image_path = './data/npc_images',
                 location_image_path = './data/location_images'):

        self.db_path = db_path
        self.db_folder = db_folder
        self.created_at = None
        self._create_tables_if_not_exists()
        self.num_locations = 0
        self.num_npc = 0

        self.npc_image_path = npc_image_path
        self.location_image_path = location_image_path


    def _get_connection(self):
        return sqlite3.connect(self.db_path)


    def _create_tables_if_not_exists(self):

        if not os.path.exists(self.db_folder):
            os.makedirs(self.db_folder)
            print(f"Folder was created: {self.db_folder}")
        try:
            conn = self._get_connection()
            self.created_at = time.time()
            cursor = conn.cursor()
            print("Successfully connected to database!")
            # Tạo bảng locations
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Locations
                (   
                    location_id INTEGER CONSTRAINT PK_Locations PRIMARY KEY AUTOINCREMENT,
                    name        TEXT,
                    description TEXT NOT NULL,
                    currentState TEXT
                )
                """)

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS Location_states
                (
                    state         TEXT,
                    location_name TEXT,
                    image_path    TEXT NOT NULL,
                    CONSTRAINT PK_Locations PRIMARY KEY (state, location_name),
                    CONSTRAINT FK_state_location FOREIGN KEY (location_name) REFERENCES Locations (name)
                )
                """)

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPCs
                (   
                    npc_id TEXT CONSTRAINT PK_NPCs PRIMARY KEY,
                    name           TEXT,
                    personality    TEXT,
                    description     TEXT,
                    affectionLevel INTEGER,
                    location       TEXT NOT NULL,
                    currentStatus TEXT,
                    image_path     TEXT,
                    CONSTRAINT fk_npc_location FOREIGN KEY (location) REFERENCES Locations (name)
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS NPC_status
                (   
                    npc_id INTEGER,
                    status     TEXT,
                    image_path TEXT,
                    CONSTRAINT PK_NPC_Status PRIMARY KEY (npc_id, status),
                    CONSTRAINT FK_status_NPC FOREIGN KEY (npc_id) REFERENCES NPCs (npc_id)
                )
                """
            )

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
            # Luôn đảm bảo đóng kết nối
            if 'conn' in locals():
                conn.close()


    def add_npc_to_db(self, npc : NPC, location: Location):
        if not npc or not location:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Tìm kiếm xem NPC với tên này đã tồn tại hay chưa
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
            # Nếu đã tồn tại thì bỏ qua không thêm nữa
            print(f"NPC có tên '{npc.name}' đã tồn tại trong Database!")
            return False  # Trả về False báo hiệu trùng lặp


    def add_location_to_db(self, location):
        if not location:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        # 1. Kiểm tra xem Địa điểm (Location) với tên này đã tồn tại hay chưa
        cursor.execute("SELECT 1 FROM Locations WHERE name = ?", (location.name,))
        existing_location = cursor.fetchone()

        if existing_location is None:
            # Nếu chưa tồn tại thì tiến hành thêm mới
            cursor.execute(
                "INSERT INTO Locations (name, description, currentState) VALUES (?, ?, ?)",
                (location.name, location.description, location.state)
            )

            # LƯU Ý: Đừng quên commit để lưu thay đổi vào Database
            self.num_locations += 1
            conn.commit()
            return True

        else:
            # Nếu đã tồn tại thì bỏ qua không thêm nữa
            print(f"Địa điểm có tên '{location.name}' đã tồn tại trong Database!")
            return False  # Trả về False báo hiệu trùng lặp

    def add_memory_to_db(self, npc_name: str, location_name: str, text: str):
        """
        Hàm quan trọng nhất để liên kết với RAG.
        Lưu ký ức vào SQLite và trả về ID để làm khóa cho FAISS.
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        # Lấy thời gian thực (Unix timestamp)
        now = int(time.time())

        # Dùng đúng tên biến tham số (text) thay vì description
        cursor.execute(
            "INSERT INTO Memory (made_at, npc, location, story) VALUES (?, ?, ?, ?)",
            (now, npc_name, location_name, text)
        )

        # Lấy ID của dòng vừa được insert thành công
        new_id = cursor.lastrowid

        # Bắt buộc phải commit để lưu thay đổi
        conn.commit()

        # TRÁNH gọi conn.close() ở đây nếu hệ thống của bạn (StateManager)
        # đang duy trì một connection chung cho toàn bộ game.

        return new_id, now


class PlayerState:
    def __init__(self):
        pass


class WorldState:
    def __init__(self):
        pass
