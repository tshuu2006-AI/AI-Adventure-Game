import json
import re
import logging
from typing import Dict, Any

# Sử dụng SDK mới của Google
from google import genai
from google.genai import types

from engine.Utils.PromptManager import PromptManager
from engine.Utils.logger import game_logger


class BaseLocalAgent:
    """
    Class Cha (Base Class) giữ nguyên tên cũ để tương thích với hệ thống.
    Bên trong đã được nâng cấp sử dụng lõi Google Gemini API SDK MỚI.
    """

    def __init__(self, pm: PromptManager, model_name: str = "gemini-2.5-flash-lite", gemini_api_key: str = None):
        self.api_key = gemini_api_key

        # Khởi tạo Client theo chuẩn SDK mới
        try:
            if self.api_key:
                self.client = genai.Client(api_key=self.api_key)
            else:
                # Nếu không truyền key, SDK sẽ tự động tìm biến môi trường GEMINI_API_KEY
                self.client = genai.Client()
        except Exception as e:
            game_logger.warning(f"[Gemini] Lỗi khởi tạo Client (Kiểm tra lại GEMINI_API_KEY trong .env): {e}")
            self.client = None

        self.model_name = model_name
        self.pm = pm
        self.logger = logging.getLogger(self.__class__.__name__)

    def _log_error(self, context: str, error: Exception):
        """Ghi log lỗi chi tiết kèm theo Stack Trace."""
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)

    # Giữ nguyên tham số max_tokens để tương thích ngược với code cũ
    async def _generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 200) -> Dict[str, Any]:
        """
        Hàm dùng chung để ép LLM trả về JSON chuẩn xác bằng Gemini SDK mới.
        """
        if not self.client:
            self.logger.error("Gemini Client chưa được khởi tạo. Không thể sinh nội dung.")
            return {}

        try:
            # Cấu hình System Prompt và Ép kiểu JSON bằng `types.GenerateContentConfig`
            config = types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.0  # Giữ ở mức 0 để kết quả logic, ổn định
            )

            # Gọi API bất đồng bộ (Lưu ý: SDK mới dùng client.aio cho async)
            response = await self.client.aio.models.generate_content(
                model=self.model_name,
                contents=user_prompt,
                config=config
            )

            raw_content = response.text

            # Thử parse JSON trực tiếp
            try:
                return json.loads(raw_content)
            except json.JSONDecodeError:
                # Fallback: Phương án dự phòng dùng Regex
                return self._parse_json_safely(raw_content)

        except Exception as e:
            self._log_error("_generate_json (Lỗi kết nối hoặc thực thi API Gemini)", e)
            return {}

    def _parse_json_safely(self, text: str) -> dict:
        """Phương án dự phòng: Tìm và trích xuất khối JSON."""
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            else:
                self.logger.warning(f"[_parse_json_safely] Không tìm thấy JSON hợp lệ trong: {text[:100]}...")
                return {}
        except json.JSONDecodeError as e:
            self._log_error(f"_parse_json_safely (Lỗi Regex JSON) | Text: {text[:100]}", e)
            return {}


# ==========================================
# CÁC CLASS CON (CHILD CLASSES)
# ==========================================

class IntentRouter(BaseLocalAgent):
    """
    Agent làm nhiệm vụ gác cổng: Phân tích hành động của người chơi.
    """

    async def parse_intent(self, player_input: str) -> Dict[str, Any]:
        sys_prompt = self.pm.get_prompt('IntentRouter', 'system')
        user_prompt = self.pm.get_prompt('IntentRouter', 'user', user_input=player_input)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=150
        )

        if not result or "intent" not in result:
            return {"intent": "UNKNOWN", "target": None, "action_details": player_input}

        return result


class StateExtractor(BaseLocalAgent):
    """
    Agent Kế toán viên: Trích xuất sự thay đổi vật phẩm, NPC và địa điểm.
    """

    async def extract_state(self, player_input: str, story_response: str, player_state) -> Dict[str, Any]:
        inventory_str = ", ".join(list(player_state.inventory.keys())) if player_state.inventory else "Trống rỗng"
        npc_str = ", ".join(
            [npc.name for npc in player_state.currentNPCs]) if player_state.currentNPCs else "Không có ai"
        location_str = player_state.currentLocation.name if player_state.currentLocation else "Chưa xác định"

        sys_prompt = self.pm.get_prompt('StateExtractor', 'system')
        user_prompt = self.pm.get_prompt(
            'StateExtractor',
            'user',
            current_location=location_str,
            current_npcs=npc_str,
            current_inventory=inventory_str,
            player_input=player_input,
            story_response=story_response
        )

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=220
        )

        if not result:
            self.logger.warning("[StateExtractor] Fallback kích hoạt do không nhận được JSON hợp lệ.")
            return {
                "items_added": [],
                "items_removed": [],
                "npcs_arrived": [],
                "npcs_left": [],
                "new_location_entered": None,
                "scene_emotion": "bình thường"
            }

        return result


class MemoryExtractor(BaseLocalAgent):
    """
    Agent Phân tích Ký ức: Bóc tách các sự kiện quan trọng.
    """

    async def extract_memory(self, player_input: str, story_response: str) -> dict:
        sys_prompt = self.pm.get_prompt("MemoryExtractor", 'system')

        few_shots = self.pm.yaml_data.get("MemoryExtractor", {}).get("FewShot_Examples", "")
        full_system_prompt = f"{sys_prompt}\n{few_shots}"

        user_prompt = self.pm.get_prompt(
            'MemoryExtractor',
            'user',
            player_input=player_input,
            story_response=story_response
        )

        result = await self._generate_json(
            system_prompt=full_system_prompt,
            user_prompt=user_prompt,
            max_tokens=200
        )

        if not result or "atomic_memories" not in result:
            game_logger.warning("[MemoryExtractor] Trả về cấu trúc trống hoặc thiếu key 'atomic_memories'.")
            return {"atomic_memories": []}

        return result


class MusicClassifier(BaseLocalAgent):
    """
    Agent phân tích cảm xúc phân cảnh để kích hoạt nhạc nền tương ứng.
    """

    async def classify_emotion(self, atmosphere_text: str) -> str:
        sys_prompt = (
            "Role: Music Director. Language: Vietnamese.\n"
            "Task: Classify the atmosphere or context into exactly ONE of the following moods: "
            "\"bình thường\", \"căng thẳng\", \"buồn\", \"vui\", or \"sợ hãi\".\n"
            "Rules:\n"
            "1. Read the input text and understand the underlying semantic emotion.\n"
            "2. Output STRICTLY JSON format. No explanations.\n"
            "Format: {\"emotion\": \"chosen_mood\"}"
        )

        user_prompt = f"Context: {atmosphere_text}"

        result = await self._generate_json(sys_prompt, user_prompt, max_tokens=30)

        if result and "emotion" in result:
            emotion = str(result["emotion"]).lower().strip()
            valid_emotions = ["bình thường", "căng thẳng", "buồn", "vui", "sợ hãi"]

            if emotion in valid_emotions:
                return emotion

        return "bình thường"