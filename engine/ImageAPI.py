import aiohttp
import os

class ImageAPI:
    """
    Class xử lý việc gọi API sang server Kaggle (SDXL).
    """
    def __init__(self, base_url: str = "https://unspelt-nonbrutally-eleanore.ngrok-free.dev"):
        # URL này lấy từ file Kaggle ngrok public_url của bạn
        self.api_url = f"{base_url}/api/image"
        self.enable_image = os.getenv("ENABLE_IMAGE", "False").lower() == "true"
        self.quality = os.getenv("IMAGE_QUALITY", "medium").lower()

    async def generate_image(self, prompt: str, image_type: str = "background") -> bytes:
        if not self.enable_image:
            return None
            
        print(f"[ImageAPI] Vẽ {image_type.upper()} | Chất lượng: {self.quality.upper()}...")
        
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            data.add_field("prompt", prompt)
            data.add_field("image_type", image_type) # Gửi loại ảnh
            data.add_field("quality", self.quality)  # Gửi chất lượng
            
            try:
                async with session.post(self.api_url, data=data, timeout=60) as response:
                    if response.status == 200:
                        return await response.read()
                    else:
                        print(f"[ImageAPI Lỗi] HTTP {response.status}")
                        return None
            except Exception as e:
                return None