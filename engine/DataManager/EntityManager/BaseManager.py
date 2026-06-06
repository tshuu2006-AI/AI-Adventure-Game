"""
Module quản lý kết nối và các thao tác CRUD cơ bản với SQLite Database.
Bao gồm các class BaseManager và các manager con cho NPC, Location, Memory.
"""
from typing import List, Tuple
import json
import sqlite3
from world.Entity import BaseEntity
from engine.Utils.logger import game_logger
from abc import ABC, abstractmethod

class BaseManager(ABC):
    """Lớp cha cung cấp kết nối và các công cụ tiện ích cho CSDL."""

    def __init__(self, db_path: str, connection):
        self.db_path = db_path
        self.conn = connection
        self.table_name = ''


    def reset(self):
        """Reset các manager"""
        raise NotImplementedError

    @abstractmethod
    async def _get_insert_data(self, entity: BaseEntity) -> Tuple[str, tuple]:
        """
        Bắt buộc lớp con phải tạo template query và data.
        Trả về: (Câu query SQL, Tuple chứa các tham số)
        """
        pass

    async def _fetch_records_by_names(self, query_template: str, names: List[str], limit: int) -> list:
        """
        Hàm helper truy xuất các entity theo tên.
        Tự động tạo số lượng placeholder (?) tương ứng với độ dài danh sách truyền vào.
        """
        normalized_names = [name.strip() for name in names if name and str(name).strip()]
        if not normalized_names: return []

        # Tạo chuỗi "?, ?, ?" động cho mệnh đề IN trong SQL
        placeholders = ", ".join(["?"] * len(normalized_names))
        final_query = query_template.format(placeholders=placeholders)

        # Gộp các tham số tên và tham số limit vào chung một tuple
        params = (*[name.lower() for name in normalized_names], limit)

        async with self.conn.execute(final_query, params) as cursor:
            return await cursor.fetchall()


    async def add_to_db(self, entity: BaseEntity):
        """
        Thêm entity vào CSDL
        """
        if not entity:
            return False

        # 1. Kiểm tra tồn tại trước khi chèn để tránh lỗi trùng lặp dữ liệu (UNIQUE constraint)
        async with self.conn.execute(f"SELECT 1 as alias FROM {self.table_name} WHERE LOWER(name) = ?",
                                     (entity.name.lower(),)) as cursor:

            if await cursor.fetchone() is not None:
                game_logger.debug(f"[{self.table_name}] Đối tượng '{entity.name}' đã tồn tại, bỏ qua lưu mới.")
                return False

        # 2. Lấy câu query và tham số dạng thô từ các subclass
        insert_query, raw_params = await self._get_insert_data(entity)

        # 3. Tiền xử lý: Tự động ép kiểu các dict/list thành chuỗi JSON trước khi lưu vào SQLite
        processed_params = [json.dumps(p, ensure_ascii=False) if isinstance(p, (list, dict)) else p for p in raw_params]

        try:
            await self.conn.execute(insert_query, tuple(processed_params))
            await self.conn.commit()
            game_logger.debug(f"[{self.table_name}] Đã lưu thành công '{entity.name}'.")
            return True
        except sqlite3.IntegrityError:
            game_logger.warning(
                f"[{self.table_name}] Đã chặn lỗi chèn trùng lặp (UNIQUE constraint) với: '{entity.name}'")
            return False
