import hashlib
import os
from engine.Utils.logger import game_logger
from engine.ImageAPI import ImageAPI


class ImageManager:
    """
    Quản lý bộ nhớ đệm (cache) hình ảnh. Tránh việc gọi API tạo lại ảnh đã có.
    """

    def __init__(self, api: ImageAPI, base_folder="./data"):
        self.api = api
        self.npc_folder = os.path.join(base_folder, "npc_images")
        self.loc_folder = os.path.join(base_folder, "location_images")
        self.item_folder = os.path.join(base_folder, "item_images")

        # Tự động tạo thư mục nếu chưa có
        os.makedirs(self.npc_folder, exist_ok=True)
        os.makedirs(self.loc_folder, exist_ok=True)
        os.makedirs(self.item_folder, exist_ok=True)
        game_logger.debug("[ImageManager] Đã khởi tạo các thư mục bộ nhớ đệm ảnh.")

    def _get_safe_filename(self, name: str) -> str:
        """
        Mã hóa tên (tiếng Việt có dấu, khoảng trắng...) thành chuỗi MD5 ngắn.
        Tránh lỗi hệ điều hành không đọc được đường dẫn.
        """
        hash_object = hashlib.md5(name.encode('utf-8'))
        return f"{hash_object.hexdigest()[:12]}.png"

    async def get_or_create_location_image(self, location_name: str, description: str, atmosphere: str) -> str:
        """
        Lấy đường dẫn ảnh địa điểm. Nếu chưa có thì tạo mới.
        """
        filename = self._get_safe_filename(f"loc_{location_name}")
        filepath = os.path.join(self.loc_folder, filename)

        #Kiểm tra ảnh có sẵn
        if os.path.exists(filepath):
            game_logger.debug(f"[ImageManager] Cache hit - Ảnh địa điểm '{location_name}' đã có sẵn.")
            return filepath

        #Xử lý tạo mới
        game_logger.info(f"[ImageManager] Đang vẽ bối cảnh mới: '{location_name}'...")

        # Thêm các keyword tối ưu cho background
        prompt = f"digital concept art, environment scenery, {description}, atmosphere: {atmosphere}, highly detailed, masterpiece, no characters"

        image_bytes = await self.api.generate_image(prompt, image_type="background")

        #Lưu file
        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            game_logger.debug(f"[ImageManager] Đã lưu thành công bối cảnh: {filepath}")
            return filepath

        game_logger.warning(f"[ImageManager] Tạo ảnh bối cảnh '{location_name}' thất bại.")
        return None

    async def get_or_create_npc_image(self, npc_name: str, description: str) -> str:
        """
        Lấy đường dẫn ảnh NPC. Nếu chưa có thì tạo mới (có tách nền).
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
        """Vẽ icon vật phẩm và tách nền trong suốt."""
        filename = self._get_safe_filename(f"item_{item_name}")
        filepath = os.path.join(self.item_folder, filename)

        if os.path.exists(filepath):
            game_logger.debug(f"[ImageManager] Cache hit - Ảnh vật phẩm '{item_name}' đã có sẵn.")
            return filepath

        game_logger.info(f"[ImageManager] Đang vẽ vật phẩm mới: '{item_name}'...")
        # Prompt vẽ Icon 2D (Bạn có thể tinh chỉnh phong cách)
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
        """Xóa toàn bộ file ảnh cũ trong thư mục để dọn chỗ cho Game mới."""
        game_logger.info("[ImageManager] Bắt đầu dọn dẹp thư mục ảnh cũ cho Game mới...")
        for folder in [self.npc_folder, self.loc_folder, self.item_folder]:
            if os.path.exists(folder):
                for filename in os.listdir(folder):
                    file_path = os.path.join(folder, filename)
                    try:
                        # Chỉ xóa file, bỏ qua nếu nó là thư mục con (mặc dù ở đây không có)
                        if os.path.isfile(file_path):
                            os.remove(file_path)
                    except Exception as e:
                        game_logger.error(f"[ImageManager] Không thể xóa ảnh cũ {file_path}: {e}", exc_info=True)
        game_logger.info("[ImageManager] Dọn dẹp thư mục ảnh hoàn tất.")

    def delete_image(self, file_path: str):
        """Xóa một file ảnh cụ thể khỏi ổ cứng."""
        if not file_path:
            return

        try:
            # Kiểm tra xem đường dẫn có tồn tại và đúng là một file hay không
            if os.path.exists(file_path) and os.path.isfile(file_path):
                os.remove(file_path)
                game_logger.debug(f"[ImageManager] Đã xóa ảnh vật lý: {file_path}")
            else:
                game_logger.warning(f"[ImageManager] Yêu cầu xóa nhưng không tìm thấy file: {file_path}")
        except Exception as e:
            # Bắt lỗi an toàn để game không bị crash nếu ổ cứng có vấn đề
            game_logger.error(f"[ImageManager] Không thể xóa ảnh {file_path}: {e}", exc_info=True)