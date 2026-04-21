import json
from groq import AsyncGroq
from typing import List, Dict, Any, AsyncGenerator
from engine.PromptManager import PromptManager
from world.Entity import *
import logging


logging.basicConfig(
    level=logging.ERROR,
    format='[%(asctime)s] %(name)s - %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class BaseCloudAgent:
    """
    Lớp cơ sở (Base Class) cho tất cả các Agent chạy trên nền tảng Cloud (Groq).
    Quản lý việc kết nối API và cung cấp hàm gọi LLM dùng chung.
    """

    def __init__(self, api_key: str, pm: PromptManager,  model_name: str = "qwen/qwen3-32b"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model_name
        self.pm = pm

        self.logger = logging.getLogger(self.__class__.__name__)

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

    def _log_error(self, context: str, error: Exception):
        """
        Hàm dùng chung để bắt và ghi nhận lỗi.
        exc_info=True sẽ in ra toàn bộ dấu vết (Stack Trace) để bạn biết lỗi ở dòng nào.
        """
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)


# ==================
# CÁC CLOUD AGENTS
# ==================

class WorldGenerateAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm khởi tạo 'Kinh thánh Thế giới' (World Bible) ở dạng JSON."""
    async def generate_bible(self, player_idea: str) -> dict:

        system_prompt = self.pm.get_prompt('WorldGenerateAgent', 'system')
        user_prompt = self.pm.get_prompt('WorldGenerateAgent', 'user', user_input=player_idea)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._chat(messages=messages, temperature=0.4, stream=False,
                                        response_format={"type": "json_object"})
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            self._log_error("generate_choices", e)

            return {}


class NPCAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm thiết kế và sinh ra thông tin NPC ở dạng JSON có tính liên kết cốt truyện (RAG)."""
    def __init__(self, api_key, pm):
        super().__init__(api_key, pm)

    async def generate_npc(self, world_mission: str, world_conflict: str, rag_context: str, location_name: str, atmosphere: str, recent_story: str):
        # Gọi PromptManager để nạp các biến động vào file yaml
        system_prompt = self.pm.get_prompt(
            'NPCAgent', 'system',
            world_mission=world_mission,
            world_conflict=world_conflict
        )
        
        user_prompt = self.pm.get_prompt(
            'NPCAgent', 'user',
            rag_context=rag_context,
            location_name=location_name,
            atmosphere=atmosphere,
            recent_story=recent_story
        )

        try:
            response = await self._chat(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.8, response_format={"type": "json_object"})
            
            return json.loads(response.choices[0].message.content)

        except Exception as e:
            print(f"[NPC ERROR] Lỗi khi sinh NPC: {e}")
            return {}


class LocationAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm tạo ra các địa điểm và bối cảnh xung quanh ở dạng JSON."""
    async def initialize_location(self, world_name, world_type, theme) -> Location:
        sys_init = self.pm.get_prompt('LocationAgent', 'systemInit')
        user_init = self.pm.get_prompt(
            'LocationAgent', 'userInit',
            world_name=world_name,
            world_type=world_type,
            theme_and_tone=theme,
        )

        location_data = await self._generate_location(sys_init, user_init)
        return location_data


    async def generate_location(self, current_location: str, target_location: str) -> Dict:
        sys_prompt = self.pm.get_prompt('LocationAgent', 'system')
        user_prompt = self.pm.get_prompt('LocationAgent', 'user', current_location=current_location,
                                         target_location_from_router=target_location)
        location_data = await self._generate_location(sys_prompt, user_prompt)
        return location_data


    async def _generate_location(self, system_prompt: str, user_prompt: str) -> Location:
        try:
            response = await self._chat(messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ], temperature=0.8, response_format={"type": "json_object"})

            location_data =  json.loads(response.choices[0].message.content)
            location = Location(id = 0,
                                name=location_data['location_name'],
                                description=location_data['description'],
                                state=location_data['atmosphere'])
            return location

        except Exception as e:
            self._log_error("generate_location", e)
            return {}


class StoryAgent(BaseCloudAgent):
    """Agent Game Master đóng vai trò kể chuyện và phản hồi hành động của người chơi theo thời gian thực."""
    async def initialize_story(self, name, theme, core_conflict, mission, vocab, location_name, location_state,
                               location_description) -> AsyncGenerator[str, None]:

        # 1. Tự động lấy Prompt (Chuyên viên tự lo)
        sys_init = self.pm.get_prompt('StoryAgent', 'systemInit')
        user_init = self.pm.get_prompt(
            'StoryAgent', 'userInit',
            world_name=name,
            world_theme=theme,
            world_conflict=core_conflict,
            world_mission=mission,
            world_vocabulary=vocab,
            location_name=location_name,
            location_atmosphere=location_state,
            location_description=location_description
        )

        # 2. Gọi hàm stream nội bộ và "bắn" từng đoạn chữ (chunk) ra ngoài
        async for chunk in self._generate_stream(system_prompt=sys_init, user_prompt=user_init):
            yield chunk

    async def generate_story(self, world_theme: str, world_conflict: str, world_vocabulary: dict,
                              current_location: str, npc_names: list, rag_context: str,
                              system_directive: str, user_input: str) -> AsyncGenerator[str, None]:

        # 1. Agent TỰ LOAD prompt của chính nó
        sys_prompt = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme=world_theme,
            world_conflict=world_conflict,
            world_vocabulary=world_vocabulary,
            current_location=current_location,
            npc_name=npc_names,
            npc_personality=None,
            rag_context=rag_context,
            valid_paths_from_sql=None,
            system_directive=system_directive
        )

        user_prompt = self.pm.get_prompt('StoryAgent', 'user', user_input=user_input)

        async for chunk in self._generate_stream(system_prompt=sys_prompt, user_prompt=user_prompt):
            yield chunk


    async def _generate_stream(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        try:
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


        except Exception as e:
            self._log_error("generate_stream", e)
            yield "Có một sự xáo trộn trong không gian... (Lỗi kết nối cốt truyện)"


class SummarizeAgent(BaseCloudAgent):
    """
    Agent chạy trên Cloud (Groq) làm nhiệm vụ tóm tắt hội thoại.
    Phục vụ cho việc tối ưu bộ nhớ dài hạn (RAG).
    """
    async def summarize_chat(self, context_window: list) -> str:
        """
        Nhận danh sách lịch sử hội thoại, tự build prompt và trả về bản tóm tắt.
        """
        # 1. Tự quản lý việc lấy prompt thay vì bắt Orchestrator làm hộ
        sys_prompt = self.pm.get_prompt('SummarizeAgent', 'system')
        user_prompt = self.pm.get_prompt(
            'SummarizeAgent', 'user',
            context_window=context_window
        )

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]

        try:
            response = await self._chat(
                messages=messages,
                temperature=0.3,
                stream=False
            )
            summary_text = response.choices[0].message.content.strip()

            return summary_text

        except Exception as e:
            self._log_error("summarize_chat", e)
            return ""


class ChoiceAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm phân tích tình huống và gợi ý các hành động tiếp theo."""

    async def generate_choices(self, current_location: str, npc_name: str, recent_story_summary: str) -> Dict[str, Any]:

        # Tự load prompt
        sys_prompt = self.pm.get_prompt('ChoiceAgent', 'system')
        user_prompt = self.pm.get_prompt(
            'ChoiceAgent', 'user',
            current_location=current_location,
            npc_name=npc_name,
            recent_story_summary=recent_story_summary
        )

        try:
            response = await self._chat(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                response_format={"type": "json_object"}
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            self._log_error("generate_choices", e)
            return {"choices": [{"id": 1, "action_text": "Tiếp tục quan sát xung quanh", "style": "Thận trọng"}]}


class QueryAgent(BaseCloudAgent):
    """
    Agent chịu trách nhiệm tổng hợp ngữ cảnh (context, location, NPC)
    thành một câu truy vấn ngắn gọn để search trong Vector Memory (FAISS).
    """
    async def generate_query(self, current_location: str, npc_name: str, context_window: str) -> str:
        sys_prompt = self.pm.get_prompt('QueryAgent', 'system')
        user_prompt = self.pm.get_prompt(
            'QueryAgent', 'user',
            current_location=current_location,
            npc_name=npc_name,
            context_window=context_window
        )
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt}
        ]
        try:
            response = await self._chat(messages=messages, temperature=0.2, stream=False)
            return response.choices[0].message.content.strip().strip('"\'')

        except Exception as e:
            self._log_error("generate_query", e)
            return ""