
import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from engine.Utils.PromptManager import PromptManager

class BaseLocalAgent:
    """
    Class Cha (Base Class) xử lý việc giao tiếp với Ollama chạy ở Local.
    Tất cả các Agent chạy Local sẽ kế thừa từ class này.
    """
    DEFAULT_MODEL = "qwen2.5:1.5b"

    # Đã thêm PromptManager vào __init__
    def __init__(self, pm: PromptManager, model_name: str = None):
        self.client = AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"
        )
        self.model = model_name or self.DEFAULT_MODEL
        self.pm = pm
        self.logger = logging.getLogger(self.__class__.__name__)

    def _log_error(self, context: str, error: Exception):
        """Ghi log lỗi chi tiết kèm theo Stack Trace."""
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)

    async def _generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 200) -> Dict[str, Any]:
        """
        Hàm dùng chung để ép LLM trả về JSON chuẩn xác và tối ưu RAM.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
                extra_body={
                    "options": {
                        "num_ctx": 1024,
                        "num_predict": max_tokens
                    }
                }
            )

            raw_content = response.choices[0].message.content
            return json.loads(raw_content)

        except json.JSONDecodeError as e:
            # Thay print bằng log
            self._log_error("_generate_json (Lỗi parse JSON)", e)
            return {}
        except Exception as e:
            # Thay print bằng log
            self._log_error("_generate_json (Lỗi kết nối Ollama)", e)
            return {}


# ==========================================
# CÁC CLASS CON (CHILD CLASSES)
# ==========================================
class IntentRouter(BaseLocalAgent):
    """
    Agent làm nhiệm vụ gác cổng: Phân tích hành động của người chơi.
    """
    # Đã xóa __init__ thừa

    # Chỉ nhận dữ liệu thô (player_input)
    async def parse_intent(self, player_input: str) -> Dict[str, Any]:
        """
        Phân loại câu nói của người chơi thành các Intent.
        """
        # Tự quản lý prompt
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
    Agent Kế toán viên: Trích xuất sự thay đổi vật phẩm, NPC và địa điểm từ lịch sử trò chuyện.
    Phiên bản Tối ưu (Slim Extraction) dành cho LLM 1.5B để tránh ảo giác và tăng tốc độ.
    """
    async def extract_state(self, player_input: str, story_response: str, player_state) -> Dict[str, Any]:
        """
        Đọc đoạn hội thoại và tìm sự thay đổi về danh sách vật phẩm, NPC và Khu vực.
        """
        # 1. Trích xuất ngữ cảnh (Context) từ PlayerState hiện tại
        if player_state.inventory:
            # Lấy danh sách tên các vật phẩm đang có trong túi
            inventory_str = ", ".join(list(player_state.inventory.keys()))
        else:
            inventory_str = "Trống rỗng"

        if player_state.currentNPCs:
            # Lấy danh sách tên các NPC đang đứng cùng người chơi
            npc_str = ", ".join([npc.name for npc in player_state.currentNPCs])
        else:
            npc_str = "Không có ai"

        location_str = player_state.currentLocation.name if player_state.currentLocation else "Chưa xác định"

        # 2. Gọi PromptManager và nhồi dữ liệu
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

        # 3. Gọi API LLM Local
        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=220  # Giữ ở mức 200 là quá đủ cho các mảng chỉ chứa tên
        )

        # 4. Fallback an toàn (Giá trị mặc định nếu API lỗi hoặc trả về JSON hỏng)
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


import json
import re
from engine.Utils.logger import game_logger


class MemoryExtractor(BaseLocalAgent):
    def __init__(self, pm, model_name="qwen2.5:1.5b"):
        super().__init__(pm=pm, model_name=model_name)
        self.model_name = model_name

    async def extract_memory(self, player_input: str, story_response: str) -> dict:
        """Trích xuất Ký ức nguyên tử từ lượt chơi hiện tại."""

        # 1. Lấy Prompt từ YAML
        sys_prompt = self.pm.get_prompt("MemoryExtractor", 'system')
        few_shots = self.pm.get_prompt("MemoryExtractor", "FewShot_Examples")

        full_system_prompt = f"{sys_prompt}\n{few_shots}"

        user_prompt = self.pm.get_prompt(
            'MemoryExtractor',
            'user',
            player_input=player_input,
            story_response=story_response
        )

        try:
            # 2. Gọi Qwen 1.5b
            raw_response = await self._generate_json(
                system_prompt=full_system_prompt,
                user_prompt=user_prompt,
                max_tokens=200  # Giữ ở mức 200 là quá đủ cho các mảng chỉ chứa tên
            )

            # 3. LÀM SẠCH VÀ ÉP KIỂU JSON (Cực kỳ quan trọng)
            if isinstance(raw_response, dict):
                return raw_response
            return self._parse_json_safely(raw_response)

        except Exception as e:
            game_logger.error(f"[MemoryExtractor] Lỗi trích xuất ký ức: {e}", exc_info=True)
            return {"atomic_memories": []}

    def _parse_json_safely(self, text: str) -> dict:
        """Tìm và trích xuất khối JSON từ chuỗi văn bản hỗn loạn."""
        try:
            # Tìm đoạn text nằm giữa { và } (Bao gồm cả nhiều dòng)
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                json_str = match.group(0)
                return json.loads(json_str)
            else:
                game_logger.warning(f"[MemoryExtractor] Không tìm thấy JSON hợp lệ trong chuỗi: {text[:50]}...")
                return {"atomic_memories": []}
        except json.JSONDecodeError as e:
            game_logger.warning(f"[MemoryExtractor] Lỗi parse JSON: {e} | Text gốc: {text}")
            return {"atomic_memories": []}


class MusicClassifier(BaseLocalAgent):
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
        
        # Gọi Local LLM sinh JSON 
        result = await self._generate_json(sys_prompt, user_prompt, max_tokens = 30)
        
        # Lấy kết quả, kiểm tra xem nó có đúng 1 trong 5 chữ không
        if result and "emotion" in result:
            emotion = str(result["emotion"]).lower().strip()
            valid_emotions = ["bình thường", "căng thẳng", "buồn", "vui", "sợ hãi"]
            
            if emotion in valid_emotions:
                return emotion

        return "bình thường"
