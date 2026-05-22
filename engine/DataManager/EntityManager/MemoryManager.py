from engine.DataManager.EntityManager.BaseManager import BaseManager
from world.Entity import Memory
from typing import List
from engine.Utils.logger import game_logger
class MemoryManager(BaseManager):
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'Memory'
    

    async def _get_insert_data(self, memory: Memory):
        pass


    async def _get_memory_text_column(self) -> str:
        """
        Đọc schema của bảng để xác định tên cột text.
        Đảm bảo tính tương thích ngược nếu db cũ dùng 'story' còn db mới dùng 'description'.
        """
        async with self.conn.execute(f"PRAGMA table_info({self.table_name})") as cursor:
            columns = {row[1] for row in await cursor.fetchall()}
        return 'story' if 'story' in columns else 'description'

    async def add_memory(self, memory_obj: Memory) -> int:
        text_column = await self._get_memory_text_column()
        query = f"INSERT INTO {self.table_name} (location, {text_column}, gameturn) VALUES (?,?,?)"

        async with self.conn.execute(query, (memory_obj.location, memory_obj.text, memory_obj.game_turn)) as cursor:
            new_id = cursor.lastrowid
            memory_obj.id = new_id
            return new_id  # Trả về ID để dùng cho việc link với bảng FAISS hoặc MEMORY_NPC

    async def get_memories_by_ids(self, memory_ids: List[int]) -> List[Memory]:
        if not memory_ids: return []
        text_column = await self._get_memory_text_column()
        placeholders = ", ".join(["?"] * len(memory_ids))
        query = f"SELECT memory_id, {text_column}, location, gameturn FROM {self.table_name} WHERE memory_id IN ({placeholders})"

        async with self.conn.execute(query, tuple(memory_ids)) as cursor:
            rows = await cursor.fetchall()

        # Tạo mapping để giữ nguyên thứ tự kết quả trả về theo đúng danh sách ID truyền vào
        rows_by_id = {
            r[0]: Memory(id=r[0], text=r[1], location=r[2], game_turn=r[3]) for r in
            rows}
        return [rows_by_id[m_id] for m_id in memory_ids if m_id in rows_by_id]

    async def get_memory_ids_by_npc_name(self, npc_name: str, limit: int = 5) -> list:
        """
        Lấy các ký ức gần nhất liên quan đến một NPC cụ thể bằng TÊN
        (Thông qua truy vấn JOIN với bảng trung gian MEMORY_NPC).
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