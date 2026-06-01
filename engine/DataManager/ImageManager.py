"""
    Quản lý bộ nhớ đệm (cache) và vòng đời của hình ảnh trong game.
    Đảm nhiệm việc kiểm tra ảnh cục bộ, gọi API sinh ảnh mới nếu cần,
    và dọn dẹp không gian lưu trữ cho các thực thể: Địa điểm, NPC, Vật phẩm.
"""
import hashlib
import os
from engine.Utils.logger import game_logger
from engine.ImageAPI import ImageAPI


class ImageManager:
    """
        Quản lý bộ nhớ đệm (cache) và vòng đời của hình ảnh trong game.
        Đảm nhiệm việc kiểm tra ảnh cục bộ, gọi API sinh ảnh mới nếu cần,
        và dọn dẹp không gian lưu trữ cho các thực thể: Địa điểm, NPC, Vật phẩm.
    """
    def __init__(self, api: ImageAPI, base_folder: str):
        """
        Khởi tạo ImageManager và thiết lập cấu trúc thư mục cache.

        Args:
            api (ImageAPI): Đối tượng xử lý giao tiếp với API sinh ảnh (SDXL Kaggle).
            base_folder (str): Thư mục gốc chứa dữ liệu của phiên chơi hiện tại.
        """
        self.api = api
        self.npc_folder = os.path.join(base_folder, "npc_images")
        self.loc_folder = os.path.join(base_folder, "location_images")
        self.item_folder = os.path.join(base_folder, "item_images")

        os.makedirs(self.npc_folder, exist_ok=True)
        os.makedirs(self.loc_folder, exist_ok=True)
        os.makedirs(self.item_folder, exist_ok=True)
        game_logger.debug("[ImageManager] Đã khởi tạo các thư mục bộ nhớ đệm ảnh.")

    def _get_safe_filename(self, name: str) -> str:
        """
        Mã hóa tên thực thể thành chuỗi MD5 để tạo tên file an toàn.
        Giúp tránh lỗi hệ thống tệp khi tên chứa tiếng Việt có dấu hoặc ký tự đặc biệt.

        Args:
            name (str): Tên gốc của thực thể (VD: "loc_Rừng hắc ám").

        Returns:
            str: Tên file đã mã hóa kèm đuôi .png (VD: "a1b2c3d4e5f6.png").
        """
        hash_object = hashlib.md5(name.encode('utf-8'))
        return f"{hash_object.hexdigest()[:12]}.png"

    async def get_or_create_location_image(self, location_name: str, description: str, atmosphere: str) -> str:
        """
        Truy xuất đường dẫn ảnh của địa điểm, hoặc gọi API sinh ảnh bối cảnh mới nếu chưa tồn tại.

        Args:
            location_name (str): Tên địa điểm.
            description (str): Mô tả chi tiết cảnh quan.
            atmosphere (str): Bầu không khí chủ đạo (VD: "u ám", "tươi sáng").

        Returns:
            str: Đường dẫn vật lý đến file ảnh, hoặc None nếu quá trình sinh ảnh thất bại.
        """
        filename = self._get_safe_filename(f"loc_{location_name}")
        filepath = os.path.join(self.loc_folder, filename)

        if os.path.exists(filepath):
            game_logger.debug(f"[ImageManager] Cache hit - Ảnh địa điểm '{location_name}' đã có sẵn.")
            return filepath

        game_logger.info(f"[ImageManager] Đang vẽ bối cảnh mới: '{location_name}'...")
        prompt = f"digital concept art, environment scenery, {description}, atmosphere: {atmosphere}, highly detailed, masterpiece, no characters"

        image_bytes = await self.api.generate_image(prompt, image_type="background")

        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            game_logger.debug(f"[ImageManager] Đã lưu thành công bối cảnh: {filepath}")
            return filepath

        game_logger.warning(f"[ImageManager] Tạo ảnh bối cảnh '{location_name}' thất bại.")
        return None

    async def get_or_create_npc_image(self, npc_name: str, description: str) -> str:
        """
        Truy xuất đường dẫn ảnh của NPC, hoặc gọi API sinh ảnh chân dung mới (có tách nền).

        Args:
            npc_name (str): Tên NPC.
            description (str): Ngoại hình và đặc điểm nhận dạng của NPC.

        Returns:
            str: Đường dẫn vật lý đến file ảnh, hoặc None nếu thất bại.
        """
        filename = self._get_safe_filename(f"npc_{npc_name}")
        filepath = os.path.join(self.npc_folder, filename)

        if os.path.exists(filepath):
            game_logger.debug(f"[ImageManager] Cache hit - Ảnh NPC '{npc_name}' đã có sẵn.")
            return filepath

        game_logger.info(f"[ImageManager] Đang vẽ NPC mới: '{npc_name}'...")
        prompt = f"character concept art, single character, {description}, full body, isolated on pure white background, highly detailed, masterpiece"

        image_bytes = await self.api.generate_image(prompt, image_type="npc")

        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            game_logger.debug(f"[ImageManager] Đã lưu thành công NPC (đã tách nền): {filepath}")
            return filepath

        game_logger.warning(f"[ImageManager] Tạo ảnh NPC '{npc_name}' thất bại.")
        return None

    async def get_or_create_item_image(self, item_name: str) -> str:
        """
        Truy xuất đường dẫn ảnh icon vật phẩm, hoặc gọi API sinh icon 2D mới.

        Args:
            item_name (str): Tên vật phẩm.

        Returns:
            str: Đường dẫn vật lý đến file ảnh, hoặc chuỗi rỗng ("") nếu thất bại.
        """
        filename = self._get_safe_filename(f"item_{item_name}")
        filepath = os.path.join(self.item_folder, filename)

        if os.path.exists(filepath):
            game_logger.debug(f"[ImageManager] Cache hit - Ảnh vật phẩm '{item_name}' đã có sẵn.")
            return filepath

        game_logger.info(f"[ImageManager] Đang vẽ vật phẩm mới: '{item_name}'...")
        prompt = f"game icon, single item, {item_name}, isolated on pure white background, highly detailed, 2d game art style"

        image_bytes = await self.api.generate_image(prompt, image_type="item")

        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            game_logger.debug(f"[ImageManager] Đã lưu thành công icon vật phẩm: {filepath}")
            return filepath

        game_logger.warning(f"[ImageManager] Tạo ảnh vật phẩm '{item_name}' thất bại.")
        return ""

    def clear_image_folders(self):
        """
        Dọn dẹp toàn bộ file ảnh trong các thư mục cache (NPC, Location, Item).
        Thường được gọi khi khởi tạo một phiên chơi (Game Loop) mới để giải phóng ổ cứng.
        """
        game_logger.info("[ImageManager] Bắt đầu dọn dẹp thư mục ảnh cũ cho Game mới...")
        for folder in [self.npc_folder, self.loc_folder, self.item_folder]:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    try:
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        game_logger.error(f"[ImageManager] Không thể xóa ảnh cũ {file_path}: {e}", exc_info=True)
        game_logger.info("[ImageManager] Dọn dẹp thư mục ảnh hoàn tất.")

    @staticmethod
    def delete_image(file_path: str):
        """
        Xóa một file ảnh cụ thể khỏi hệ thống tệp.
        Có cơ chế bắt lỗi an toàn để không làm crash game nếu file không tồn tại hoặc bị khóa.

        Args:
            file_path (str): Đường dẫn tuyệt đối hoặc tương đối tới file ảnh cần xóa.
        """
        if not file_path:
            return

        try:
            if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                game_logger.debug(f"[ImageManager] Đã xóa ảnh vật lý: {file_path}")
            else:
                game_logger.warning(f"[ImageManager] Yêu cầu xóa nhưng không tìm thấy file: {file_path}")
        except Exception as e:
            game_logger.error(f"[ImageManager] Không thể xóa ảnh {file_path}: {e}", exc_info=True)