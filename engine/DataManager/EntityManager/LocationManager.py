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