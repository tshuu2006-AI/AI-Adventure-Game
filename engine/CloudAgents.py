import json
from groq import AsyncGroq
from typing import List, Dict, Any, AsyncGenerator

class BaseCloudAgent:
    def __init__(self, api_key: str, model_name: str = "llama3-8b-8192"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model_name

    async def _chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, stream: bool = False, response_format: Dict = None, n: int = 1):
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
    async def generate_bible(self, system_prompt: str, user_prompt: str) -> dict:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        response = await self._chat(messages=messages, temperature=0.4, stream=False, response_format={"type": "json_object"})
        return json.loads(response.choices[0].message.content)


class NPCAgent(BaseCloudAgent):
    async def generate_npc(self, system_prompt: str, user_prompt: str):
        try:
            response = await self._chat(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.8, response_format={"type": "json_object"})
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[NPC ERROR] {e}")
            return {}


class LocationAgent(BaseCloudAgent):
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
    async def generate_stream(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
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