import json
from typing import Dict, Any
from openai import AsyncOpenAI


class BaseLocalAgent:
    """
    Class Cha (Base Class) xử lý việc giao tiếp với Ollama chạy ở Local.
    Tất cả các Agent chạy Local sẽ kế thừa từ class này.
    """
    DEFAULT_MODEL = "qwen2.5:1.5b"

    def __init__(self, model_name: str = None):
        # Kết nối tới Ollama API (tương thích chuẩn OpenAI)
        self.client = AsyncOpenAI(
            base_url="http://localhost:11434/v1",
            api_key="ollama"  # Khóa giả lập cho Ollama
        )
        self.model = model_name or self.DEFAULT_MODEL

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
                temperature=0.0,  # Nhiệt độ = 0 để đảm bảo tính logic, không sáng tạo linh tinh
                response_format={"type": "json_object"},
                # Ép khung ngữ cảnh để chống tràn VRAM (RTX 3050)
                extra_body={
                    "options": {
                        "num_ctx": 1024,  # Chỉ nhớ tối đa 1024 tokens
                        "num_predict": max_tokens  # Giới hạn độ dài JSON sinh ra
                    }
                }
            )

            raw_content = response.choices[0].message.content
            return json.loads(raw_content)

        except json.JSONDecodeError:
            print(f"[Lỗi LocalAgent] LLM không trả về JSON hợp lệ: {raw_content}")
            return {}
        except Exception as e:
            print(f"[Lỗi LocalAgent] Mất kết nối tới Ollama: {e}")
            return {}


# ==========================================
# CÁC CLASS CON (CHILD CLASSES)
# ==========================================
class IntentRouter(BaseLocalAgent):
    """
    Agent làm nhiệm vụ gác cổng: Phân tích hành động của người chơi.
    """

    def __init__(self, model_name: str = None):
        super().__init__(model_name)

    async def parse_intent(self, system_prompt: str, user_input: str) -> Dict[str, Any]:
        """
        Phân loại câu nói của người chơi thành các Intent (MOVE, TALK, ACTION...).
        """
        print("[Local] Đang phân tích Ý định người chơi...")

        # Router thường trả JSON rất ngắn, nên max_tokens = 150 là đủ
        result = await self._generate_json(
            system_prompt=system_prompt,
            user_prompt=user_input,
            max_tokens=150
        )

        # Bắt lỗi dự phòng nếu mô hình ngáo
        if "intent" not in result:
            result["intent"] = "UNKNOWN"
            result["target"] = None
            result["action_details"] = user_input

        return result


class StateExtractor(BaseLocalAgent):
    """
    Agent Kế toán viên: Trích xuất vật phẩm/chỉ số từ lịch sử trò chuyện.
    """

    def __init__(self, model_name: str = None):
        super().__init__(model_name)

    async def extract_state(self, system_prompt: str, chat_history: str) -> Dict[str, Any]:
        """
        Đọc đoạn hội thoại và tính toán sự thay đổi vật phẩm, độ hảo cảm.
        """
        print("[Local] Đang rà soát túi đồ & trạng thái...")

        # Extractor cần trích xuất mảng vật phẩm nên cho max_tokens dài hơn một chút
        result = await self._generate_json(
            system_prompt=system_prompt,
            user_prompt=chat_history,
            max_tokens=250
        )

        return result