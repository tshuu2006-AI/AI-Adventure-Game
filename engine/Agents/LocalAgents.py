import json
import logging
from typing import Dict, Any
from openai import AsyncOpenAI
from engine.PromptManager import PromptManager

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
    Agent Kế toán viên: Trích xuất vật phẩm/chỉ số từ lịch sử trò chuyện.
    """
    # Đã xóa __init__ thừa

    # Chỉ nhận dữ liệu thô (chat_history)
    async def extract_state(self, chat_history: str) -> Dict[str, Any]:
        """
        Đọc đoạn hội thoại và tính toán sự thay đổi vật phẩm, độ hảo cảm.
        """
        # Tự quản lý prompt
        sys_prompt = self.pm.get_prompt('StateExtractor', 'system')
        user_prompt = self.pm.get_prompt('StateExtractor', 'user', conversation_history=chat_history)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=250
        )

        # Trả về fallback data an toàn nếu parse lỗi
        if not result:
            return {
                "npc_affection_change": 0,
                "items_added": [],
                "items_removed": [],
                "new_npc_encountered": None,
                "new_location_entered": None
            }
        return result