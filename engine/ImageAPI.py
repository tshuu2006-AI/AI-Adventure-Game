import aiohttp
import time
class ImageAPI:
    """
    Class xử lý việc gọi API sang server Kaggle (SDXL).
    """
    def __init__(self, base_url: str = "https://unspelt-nonbrutally-eleanore.ngrok-free.dev"):
        # URL này lấy từ file Kaggle ngrok public_url của bạn
        self.api_url = f"{base_url}/api/image"
        self.enable_image = "true"
        self.quality = "medium"

    async def generate_image(self, prompt: str, image_type: str = "background") -> bytes:
        if not self.enable_image:
            return None
            
        print(f"[ImageAPI] Vẽ {image_type.upper()} | Chất lượng: {self.quality.upper()}...")

        start_img = time.perf_counter()
        
        safe_prompt = prompt
        if image_type.lower() == "npc":
            # Ép buộc NPC phải mặc đồ đàng hoàng, phong cách fantasy, nghiêm cấm hở hang
            safe_prompt += ", fully clothed, wearing detailed modest fantasy clothing/armor, sfw, masterpiece, high quality, no nude, no cleavage"
        else:
            # Ép buộc Background/Item mượt mà, không dính nhân vật (để tránh AI tự vẽ thêm người hở hang vào cảnh)
            safe_prompt += ", sfw, masterpiece, high quality, highly detailed, no humans"
            
        async with aiohttp.ClientSession() as session:
            data = aiohttp.FormData()
            # 🌟 Gửi safe_prompt thay cho prompt gốc
            data.add_field("prompt", safe_prompt)
            data.add_field("image_type", image_type) 
            data.add_field("quality", self.quality)  
            
            try:
                async with session.post(self.api_url, data=data, timeout=60) as response:
                    if response.status == 200:
                        img_bytes = await response.read()
                        print(f"[Profile] Sinh ảnh {image_type} mất: {time.perf_counter() - start_img:.3f}s")
                        return img_bytes
                    else:
                        print(f"[ImageAPI] Lỗi HTTP: {response.status}")
                        return None
            except Exception as e:
                print(f"[ImageAPI] Lỗi kết nối Kaggle: {e}")
                return None