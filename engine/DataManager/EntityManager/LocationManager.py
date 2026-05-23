"""Lớp quản lý các Location"""
from engine.DataManager.EntityManager.BaseManager import BaseManager
from typing import List, Tuple
from world.Entity import Location

class LocationManager(BaseManager):
    """Lớp quản lý table Location"""

    def __init__(self, db_path, connection):
        super().__init__(db_path, connection)
        self.table_name = 'Locations'

    async def _get_insert_data(self, location: Location) -> Tuple[str, tuple] :
        """Tạo template và danh sách tham số cần thiết để truy vấn Location"""
        query = f"INSERT INTO {self.table_name} (name, description, atmosphere, image_path) VALUES (?, ?, ?, ?)"
        params = (location.name, location.description, location.atmosphere, location.image_path)
        return query, params

    async def get_by_names(self, location_names: List[str], limit: int = 3) -> List[Location]:
        """Truy vấn Location theo danh sách tên"""

        query_template = "SELECT location_id, name, description, atmosphere, image_path FROM Locations WHERE LOWER(name) IN ({placeholders}) LIMIT ?"
        location_rows = await self._fetch_records_by_names(query_template, location_names, limit)
        return [Location(id=r[0], name=r[1], description=r[2], atmosphere=r[3], image_path=r[4]) for r in location_rows]
    
    async def get_all(self):
        """Lấy toàn bộ danh sách Địa điểm từ Database (Dùng cho Sổ tay)"""
        try:
            async with self.conn.execute("SELECT location_id, name, description, atmosphere, image_path FROM Locations") as cursor:
                rows = await cursor.fetchall()
                from world.Entity import Location
                return [Location(id=row[0], name=row[1], description=row[2], atmosphere=row[3], image_path=row[4]) for row in rows]
        except Exception as e:
            print(f"Lỗi khi get_all Locations: {e}")
            return []