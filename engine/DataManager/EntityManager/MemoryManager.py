from engine.DataManager.EntityManager.BaseManager import BaseManager
from world.Entity import Memory
from typing import List
from engine.Utils.logger import game_logger


class MemoryManager(BaseManager):
    """
    Lớp quản lý các thao tác tương tác với cơ sở dữ liệu (SQLite) cho thực thể Memory.
    Kế thừa từ BaseManager, đảm nhiệm việc thêm, truy xuất và liên kết các ký ức
    của người chơi hoặc hệ thống với các NPC và địa điểm.
    """

    def __init__(self, db_path: str, connection):
        """
        Khởi tạo MemoryManager.

        Args:
            db_path (str): Đường dẫn tới file cơ sở dữ liệu SQLite.
            connection: Đối tượng kết nối cơ sở dữ liệu (thường là aiosqlite connection).
        """
        super().__init__(db_path, connection)
        self.table_name = 'Memory'

    async def _get_insert_data(self, memory: Memory):
        """
        Tạo template query và danh sách tham số để chèn Memory vào CSDL.
        (Hiện tại bỏ qua vì MemoryManager sử dụng hàm add_memory chuyên biệt
        để lấy ID trả về).

        Args:
            memory (Memory): Đối tượng ký ức.
        """
        pass

    async def _get_memory_text_column(self) -> str:
        """
        Đọc schema của bảng để xác định tên cột chứa nội dung văn bản của ký ức.
        Đảm bảo tính tương thích ngược nếu CSDL phiên bản cũ dùng cột 'story'
        còn CSDL phiên bản mới dùng cột 'description'.

        Returns:
            str: Tên cột thực tế trong CSDL ('story' hoặc 'description').
        """
        async with self.conn.execute(f"PRAGMA table_info({self.table_name})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        return 'story' if 'story' in columns else 'description'

    async def add_memory(self, memory_obj: Memory) -> int:
        """
        Thêm một ký ức mới vào cơ sở dữ liệu SQLite và lấy lại ID tự tăng.

        Args:
            memory_obj (Memory): Đối tượng ký ức chứa nội dung, vị trí và turn hiện tại.

        Returns:
            int: ID của ký ức vừa được chèn vào CSDL (dùng để đồng bộ với FAISS
                 và lưu bảng trung gian MEMORY_NPC).
        """
        text_column = await self._get_memory_text_column()
        query = f"INSERT INTO {self.table_name} (location, {text_column}, gameturn) VALUES (?,?,?)"

        async with self.conn.execute(query, (memory_obj.location, memory_obj.text, memory_obj.game_turn)) as cursor:
            new_id = cursor.lastrowid
            memory_obj.id = new_id
            return new_id  # Trả về ID để dùng cho việc link với bảng FAISS hoặc MEMORY_NPC

    async def get_memories_by_ids(self, memory_ids: List[int]) -> List[Memory]:
        """
        Truy xuất danh sách các đối tượng Memory hoàn chỉnh dựa trên danh sách ID.
        Hàm này đặc biệt quan trọng cho hệ thống RAG vì nó giữ nguyên thứ tự kết quả
        trả về khớp chính xác với danh sách ID đầu vào (phục vụ việc Reranking).

        Args:
            memory_ids (List[int]): Danh sách các ID ký ức cần truy xuất từ DB.

        Returns:
            List[Memory]: Danh sách các đối tượng Memory tương ứng, theo đúng thứ tự ID.
        """
        if not memory_ids:
            return []

        text_column = await self._get_memory_text_column()
        placeholders = ", ".join(["?"] * len(memory_ids))
        query = f"SELECT memory_id, {text_column}, location, gameturn FROM {self.table_name} WHERE memory_id IN ({placeholders})"

        async with self.conn.execute(query, tuple(memory_ids)) as cursor:
            rows = await cursor.fetchall()

        # Tạo mapping để giữ nguyên thứ tự kết quả trả về theo đúng danh sách ID truyền vào
        rows_by_id = {
            r[0]: Memory(id=r[0], text=r[1], location=r[2], game_turn=r[3]) for r in rows
        }
        return [rows_by_id[m_id] for m_id in memory_ids if m_id in rows_by_id]

    async def get_memory_ids_by_npc_name(self, npc_name: str, limit: int = 5) -> list:
        """
        Lấy các ký ức gần nhất liên quan đến một NPC cụ thể dựa trên tên của họ
        (Thông qua truy vấn JOIN với bảng trung gian MEMORY_NPC).

        Args:
            npc_name (str): Tên của NPC cần tra cứu ký ức.
            limit (int, optional): Số lượng ký ức tối đa cần lấy. Mặc định là 5.

        Returns:
            list: Danh sách các dictionary chứa thông tin tóm tắt của ký ức
                  (gồm 'id', 'text', 'game_turn'). Trả về mảng rỗng nếu có lỗi.
        """
        text_column = await self._get_memory_text_column()
        query = f"""
            SELECT m.memory_id, m.{text_column}, m.gameturn
            FROM {self.table_name} m
            JOIN MEMORY_NPC link ON m.memory_id = link.memory_id
            JOIN NPCs n ON link.npc_id = n.npc_id
            WHERE n.name = ?
            ORDER BY m.gameturn DESC
            LIMIT ?
        """

        try:
            async with self.conn.execute(query, (npc_name, limit)) as cursor:
                rows = await cursor.fetchall()

            return [
                {"id": row[0], "text": row[1], "game_turn": row[2]}
                for row in rows
            ]
        except Exception as e:
            game_logger.error(
                f"[MemoryManager] Lỗi khi lấy ký ức của NPC '{npc_name}': {e}",
                exc_info=True
            )
            return []