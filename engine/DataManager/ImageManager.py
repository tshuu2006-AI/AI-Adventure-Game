import os
import hashlib
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

        # 1. Kiểm tra ảnh có sẵn
        if os.path.exists(filepath):
            print(f"[ImageManager] Ảnh địa điểm '{location_name}' đã có sẵn trong máy.")
            return filepath

        # 2. Xử lý tạo mới
        print(f"[ImageManager] Đang vẽ bối cảnh mới: '{location_name}'...")
        
        # Thêm các keyword tối ưu cho background
        prompt = f"digital concept art, environment scenery, {description}, atmosphere: {atmosphere}, highly detailed, masterpiece, no characters"
        
        image_bytes = await self.api.generate_image(prompt, image_type="background")
        
        # 3. Lưu file
        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            print(f"[ImageManager] Đã lưu thành công: {filepath}")
            return filepath
            
        return None

    async def get_or_create_npc_image(self, npc_name: str, description: str) -> str:
        """
        Lấy đường dẫn ảnh NPC. Nếu chưa có thì tạo mới (có tách nền).
        """
        filename = self._get_safe_filename(f"npc_{npc_name}")
        filepath = os.path.join(self.npc_folder, filename)

        if os.path.exists(filepath):
            print(f"[ImageManager] Ảnh NPC '{npc_name}' đã có sẵn trong máy.")
            return filepath

        print(f"[ImageManager] Đang vẽ NPC mới: '{npc_name}'...")
        
        # Thêm từ khóa "white background" để rembg dễ tách nền hơn
        prompt = f"character concept art, single character, {description}, full body, isolated on pure white background, highly detailed, masterpiece"
        
        image_bytes = await self.api.generate_image(prompt, image_type="npc")
        
        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            print(f"[ImageManager] Đã lưu thành công NPC (đã tách nền): {filepath}")
            return filepath
            
        return None
    
    async def get_or_create_item_image(self, item_name: str) -> str:
        """Vẽ icon vật phẩm và tách nền trong suốt."""
        filename = self._get_safe_filename(f"item_{item_name}")
        filepath = os.path.join(self.item_folder, filename)

        if os.path.exists(filepath):
            return filepath

        print(f"[ImageManager] Đang vẽ vật phẩm mới: '{item_name}'...")
        # Prompt vẽ Icon 2D (Bạn có thể tinh chỉnh phong cách)
        prompt = f"game icon, single item, {item_name}, isolated on pure white background, highly detailed, 2d game art style"
        
        image_bytes = await self.api.generate_image(prompt, image_type="item")
        
        if image_bytes:
            with open(filepath, "wb") as f:
                f.write(image_bytes)
            return filepath
            
        return ""