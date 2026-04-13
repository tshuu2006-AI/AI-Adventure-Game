import json
from groq import AsyncGroq
from typing import List, Dict, Any, AsyncGenerator


class BaseCloudAgent:
    """
    Lớp cơ sở (Base Class) cho tất cả các Agent chạy trên nền tảng Cloud (Groq).
    Quản lý việc kết nối API và cung cấp hàm gọi LLM dùng chung.
    """

    def __init__(self, api_key: str, model_name: str = "openai/gpt-oss-20b"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model_name

    async def _chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, stream: bool = False,
                    response_format: Dict = None, n: int = 1):
        """
        Hàm bao bọc (wrapper) để gọi API Groq một cách bất đồng bộ.
        """
        return await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format,
            n=n
        )


# ==================
# CÁC CLOUD AGENTS
# ==================

class WorldGenerateAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm khởi tạo 'Kinh thánh Thế giới' (World Bible) ở dạng JSON."""

    async def generate_bible(self, system_prompt: str, user_prompt: str) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        # Sử dụng JSON mode (response_format) và nhiệt độ thấp (0.4) để đảm bảo cấu trúc chặt chẽ
        response = await self._chat(messages=messages, temperature=0.4, stream=False,
                                    response_format={"type": "json_object"})
        return json.loads(response.choices[0].message.content)


class NPCAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm thiết kế và sinh ra thông tin NPC ở dạng JSON."""

    async def generate_npc(self, system_prompt: str, user_prompt: str):
        try:
            # Nhiệt độ cao (0.8) giúp NPC có tính cách đa dạng và sáng tạo hơn
            response = await self._chat(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.8, response_format={"type": "json_object"})
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[NPC ERROR] {e}")
            return {}


class LocationAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm tạo ra các địa điểm và bối cảnh xung quanh ở dạng JSON."""

    async def generate_location(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        try:
            response = await self._chat(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.8, response_format={"type": "json_object"})
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[LOCATION ERROR] {e}")
            return {}


class StoryAgent(BaseCloudAgent):
    """Agent Game Master đóng vai trò kể chuyện và phản hồi hành động của người chơi theo thời gian thực."""

    async def generate_stream(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        # Kích hoạt chế độ stream để trả về từng đoạn chữ (chunk) tạo cảm giác AI đang "gõ"
        stream = await self._chat(messages=messages, temperature=0.9, stream=True)
        async for chunk in stream:
            content = chunk.choices[0].delta.content
            if content:
                yield content


class SummarizeAgent(BaseCloudAgent):
    """
    Agent chạy trên Cloud (Groq) làm nhiệm vụ tóm tắt hội thoại thành 1 câu.
    """

    async def summarize_chat(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # temperature=0.3 để câu văn khách quan, chính xác, không bịa chuyện
            response = await self._chat(
                messages=messages,
                temperature=0.3,
                stream=False
            )

            # Vì file YAML của bạn yêu cầu trả về MỘT CÂU DUY NHẤT,
            # nên ta lấy thẳng content text, dùng strip() để xóa khoảng trắng thừa
            summary_text = response.choices[0].message.content.strip()

            return summary_text

        except Exception as e:
            print(f"[SUMMARIZE ERROR] Lỗi khi gọi API tóm tắt: {e}")
            return ""
        

class ChoiceAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm phân tích tình huống và gợi ý các hành động tiếp theo."""

    async def generate_choices(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        try:
            response = await self._chat(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7, 
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[CHOICE ERROR] {e}")
            return {"choices": []}


class QueryAgent(BaseCloudAgent):
    """
    Agent chịu trách nhiệm tổng hợp ngữ cảnh (context, location, NPC)
    thành một câu truy vấn ngắn gọn để search trong Vector Memory (FAISS).
    """

    async def generate_query(self, system_prompt: str, user_prompt: str) -> str:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            # Nhiệt độ thấp (0.2) để trích xuất keyword chính xác, khách quan
            response = await self._chat(
                messages=messages,
                temperature=0.2,
                stream=False
            )

            # Lấy chuỗi truy vấn và loại bỏ khoảng trắng/dấu nháy thừa
            search_query = response.choices[0].message.content.strip().strip('"\'')
            return search_query

        except Exception as e:
            print(f"[QUERY ERROR] Lỗi khi tạo câu truy vấn VectorDB: {e}")
            return ""