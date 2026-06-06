"""Lớp quản lý NPC"""
from engine.DataManager.EntityManager.BaseManager import BaseManager
from world.Entity import NPC
from engine.Utils.logger import game_logger
from typing import List
class NPCManager(BaseManager):
    """
    Lớp quản lý table NPCs
    """
    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'NPCs'


    async def _get_insert_data(self, npc: NPC):
        query = f"INSERT INTO {self.table_name} (name, personality, description, affectionate, location, currentStatus, image_path) VALUES (?, ?, ?, ?, ?, ?, ?)"
        params = (npc.name, npc.personality, npc.description, npc.affectionate, npc.location, npc.status,
                  npc.image_path)
        return query, params


    async def get_by_names(self, npc_names: List[str], limit: int = 3) -> List[NPC]:
        """
       Truy vấn NPC dựa trên danh sách tên
        """
        query_template = "SELECT npc_id, name, personality, description, affectionate, location, currentStatus, image_path FROM NPCs WHERE LOWER(name) IN ({placeholders}) LIMIT ?"
        npc_rows = await self._fetch_records_by_names(query_template, npc_names, limit)
        npcs = [
            NPC(id=r[0],
                name=r[1],
                personality=r[2],
                description=r[3],
                affectionate=r[4],
                location=r[5],
                status=r[6],
                image_path=r[7]) for r in npc_rows]
        return npcs

    async def update_npc_state(self, npc_name: str, affection_change: int = 0, new_status: str = None) -> bool:
        """Cập nhật điểm thiện cảm và/hoặc thể trạng vật lý (status) của NPC."""
        if not npc_name:
            return False

        try:
            # Nếu có trạng thái vật lý mới (bị thương, mù, v.v...)
            if new_status:
                query = f"""
                    UPDATE {self.table_name} 
                    SET affectionate = MAX(-100, MIN(100, affectionate + ?)), 
                        currentStatus = ? 
                    WHERE LOWER(name) = ?
                """
                async with self.conn.execute(query, (affection_change, new_status, npc_name.lower())) as cursor:
                    if cursor.rowcount > 0:
                        game_logger.info(
                            f"[NPCManager] 🩸 Cập nhật {npc_name}: Thể trạng -> '{new_status}', Thiện cảm ({affection_change:+d})")
                        return True

            # Nếu chỉ thay đổi điểm thiện cảm, giữ nguyên thể trạng
            elif affection_change != 0:
                query = f"""
                    UPDATE {self.table_name} 
                    SET affectionate = MAX(-100, MIN(100, affectionate + ?))
                    WHERE LOWER(name) = ?
                """
                async with self.conn.execute(query, (affection_change, npc_name.lower())) as cursor:
                    if cursor.rowcount > 0:
                        game_logger.info(f"[NPCManager] 💖 Cập nhật {npc_name}: Thiện cảm ({affection_change:+d})")
                        return True

            return False
        except Exception as e:
            game_logger.error(f"[NPCManager Lỗi] Không thể cập nhật trạng thái cho {npc_name}: {e}", exc_info=True)
            return False
        
    async def get_all(self):
        """Lấy toàn bộ danh sách NPC từ Database (Dùng cho Sổ tay)"""
        try:
            # SỬA 'affectionLevel' thành 'affectionate'
            async with self.conn.execute("SELECT npc_id, name, personality, description, affectionate, location, currentStatus, image_path FROM NPCs") as cursor:
                rows = await cursor.fetchall()
                from world.Entity import NPC
                return [NPC(id=row[0], name=row[1], personality=row[2], description=row[3], affectionate=row[4], location=row[5], status=row[6], image_path=row[7]) for row in rows]
        except Exception as e:
            print(f"Lỗi khi get_all NPCs: {e}")
            return []