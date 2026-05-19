import json
import asyncio
from groq import AsyncGroq
from typing import List, Dict, Any, AsyncGenerator
from engine.Utils.PromptManager import PromptManager
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

    def __init__(self, api_key: str, pm: PromptManager, model_name: str = "openai/gpt-oss-120b"):
        self.client = AsyncGroq(api_key=api_key)
        self.model = model_name
        self.pm = pm

        self.logger = logging.getLogger(self.__class__.__name__)

    async def _chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, stream: bool = False,
                    response_format: Dict = None, n: int = 1):
        """Hàm bao bọc (wrapper) để gọi API Groq một cách bất đồng bộ."""
        return await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format,
            n=n
        )

    def _log_error(self, context: str, error: Exception):
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)

    # ---------------------------------------------------------
    # HÀM MỚI: Gọi API ép xuất JSON, có cơ chế Retry và Validate
    # ---------------------------------------------------------
    async def _generate_json_with_retry(self, system_prompt: str, user_prompt: str, required_keys: List[str],
                                        max_retries: int = 3, temperature: float = 0.8) -> dict:
        """
        Gọi API và đảm bảo JSON trả về có đầy đủ các key yêu cầu.
        Sẽ thử lại tối đa `max_retries` lần nếu thất bại.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for attempt in range(1, max_retries + 1):
            try:
                response = await self._chat(messages=messages, temperature=temperature, stream=False,
                                            response_format={"type": "json_object"})
                json_str = response.choices[0].message.content
                data = json.loads(json_str)

                # 1. Kiểm tra xem kết quả có phải là Dictionary không
                if not isinstance(data, dict):
                    raise ValueError(f"Kết quả không phải là đối tượng JSON (Dictionary). Trả về kiểu: {type(data)}")

                # 2. Kiểm tra xem có thiếu Key nào không
                missing_keys = [key for key in required_keys if key not in data]
                if missing_keys:
                    raise ValueError(f"JSON bị thiếu các key bắt buộc: {missing_keys}")

                # Nếu qua hết các bài kiểm tra -> JSON hoàn hảo
                return data

            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"[Attempt {attempt}/{max_retries}] Lỗi trích xuất JSON: {e}")
                if attempt == max_retries:
                    self.logger.error(f"Đã thử {max_retries} lần nhưng vẫn lỗi. Đành trả về dict rỗng.")
                    return {}

                # Chờ một chút xíu trước khi thử lại để tránh spam API
                await asyncio.sleep(0.5)
            except Exception as e:
                self._log_error(f"Lỗi API trong lúc sinh JSON (Lần {attempt})", e)
                return {}

        return {}


# ==================
# CÁC CLOUD AGENTS
# ==================

class WorldGenerateAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm khởi tạo 'Kinh thánh Thế giới' (World Bible) ở dạng JSON."""

    async def generate_bible(self, player_idea: str) -> dict:
        system_prompt = self.pm.get_prompt('WorldGenerateAgent', 'system')
        user_prompt = self.pm.get_prompt('WorldGenerateAgent', 'user', user_input=player_idea)

        # Các khóa BẮT BUỘC LLM phải trả về
        required_keys = ["world_name", "world_type", "theme_and_tone", "core_conflict", "world_mission",
                         "dynamic_vocabulary"]

        return await self._generate_json_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.4
        )


class NPCAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm thiết kế và sinh ra thông tin NPC ở dạng JSON."""

    async def generate_npc(self, npc_name, context):
        sys_prompt = self.pm.get_prompt('NPCAgent', 'system')
        user_prompt = self.pm.get_prompt('NPCAgent', 'user', context=context, npc_name=npc_name)

        required_keys = ["name", "personality", "description", "affectionate", "status"]

        result = await self._generate_json_with_retry(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.8
        )

        if not result:
            # Fallback an toàn nếu thử 3 lần đều xịt
            return {"name": npc_name, "personality": "Bí ẩn", "description": "Một bóng người không rõ mặt",
                    "affectionate": 0, "status": "Bình thường"}
        return result


class LocationAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm tạo ra các địa điểm và bối cảnh xung quanh ở dạng JSON."""

    async def initialize_location(self, world_name, world_type, theme) -> Location:
        sys_init = self.pm.get_prompt('LocationAgent', 'systemInit')
        user_init = self.pm.get_prompt('LocationAgent', 'userInit', world_name=world_name, world_type=world_type,
                                       theme_and_tone=theme)
        return await self._generate_location(sys_init, user_init)

    async def generate_location(self, current_location: str, target_location: str, context: str) -> Location:
        sys_prompt = self.pm.get_prompt('LocationAgent', 'system')
        user_prompt = self.pm.get_prompt('LocationAgent', 'user', current_location=current_location,
                                         target_location_from_router=target_location, context=context)
        return await self._generate_location(sys_prompt, user_prompt)

    async def _generate_location(self, system_prompt: str, user_prompt: str) -> Location:
        required_keys = ["location_name", "description", "atmosphere"]

        location_data = await self._generate_json_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.8
        )

        # Nếu lỗi (data rỗng), trả về 1 Location mặc định thay vì sập game
        if not location_data:
            return Location(id=0, name="Vùng Đất Vô Danh", description="Mọi thứ mờ mịt...", atmosphere="bình thường")

        return Location(id=0, name=location_data['location_name'], description=location_data['description'],
                        atmosphere=location_data['atmosphere'])


class ChoiceAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm phân tích tình huống và gợi ý các hành động tiếp theo."""

    async def generate_choices(self, current_location: str, npc_name: str, recent_story_summary: str) -> Dict[str, Any]:
        sys_prompt = self.pm.get_prompt('ChoiceAgent', 'system')
        user_prompt = self.pm.get_prompt('ChoiceAgent', 'user', current_location=current_location, npc_name=npc_name,
                                         recent_story_summary=recent_story_summary)

        required_keys = ["choices"]

        result = await self._generate_json_with_retry(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.7
        )

        if not result:
            return {"choices": [{"id": 1, "action_text": "Tiếp tục quan sát xung quanh", "style": "Thận trọng"}]}
        return result


# ===============================================
# CÁC AGENT KHÔNG XUẤT JSON (Story và Query)
# (Phần này được giữ nguyên hoàn toàn như code của bạn)
# ===============================================

class StoryAgent(BaseCloudAgent):
    """Agent Game Master đóng vai trò kể chuyện và phản hồi hành động của người chơi theo thời gian thực."""

    async def initialize_story(self, name, theme, core_conflict, mission, vocab, location_name, location_atmosphere,
                               location_description) -> AsyncGenerator[str, None]:
        sys_init = self.pm.get_prompt('StoryAgent', 'systemInit')
        user_init = self.pm.get_prompt(
            'StoryAgent', 'userInit',
            world_name=name, world_theme=theme, world_conflict=core_conflict, world_mission=mission,
            world_vocabulary=vocab, location_name=location_name, location_atmosphere=location_atmosphere,
            location_description=location_description
        )
        async for chunk in self._generate_stream(system_prompt=sys_init, user_prompt=user_init):
            yield chunk

    async def generate_story(self, world_theme: str, world_conflict: str, world_vocabulary: dict,
                             current_location: str, npc_names: list, rag_context: str,
                             system_directive: str, user_input: str) -> AsyncGenerator[str, None]:
        sys_prompt = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme=world_theme, world_conflict=world_conflict, world_vocabulary=world_vocabulary,
            current_location=current_location, npc_names=npc_names, npc_personality=None,
            rag_context=rag_context, valid_paths_from_sql=None, system_directive=system_directive
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
            stream = await self._chat(messages=messages, temperature=0.9, stream=True)
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content:
                    yield content
        except Exception as e:
            self._log_error("generate_stream", e)
            yield "Có một sự xáo trộn trong không gian... (Lỗi kết nối cốt truyện)"


class QueryAgent(BaseCloudAgent):
    """
    Agent chịu trách nhiệm tổng hợp ngữ cảnh thành một câu truy vấn ngắn gọn.
    """

    async def generate_query(self, current_location: str, npc_names: list, context: str) -> str:
        sys_prompt = self.pm.get_prompt('QueryAgent', 'system')
        user_prompt = self.pm.get_prompt(
            'QueryAgent', 'user',
            current_location=current_location, npc_name=npc_names, context_window=context
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