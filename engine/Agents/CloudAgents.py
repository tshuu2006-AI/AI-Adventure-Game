"""
Module quản lý các Cloud Agents (sử dụng Groq API).
Bao gồm các class phục vụ cho việc sinh cốt truyện, NPC, địa điểm, lựa chọn, và xử lý JSON.
"""

import json
import asyncio
from groq import AsyncGroq
from typing import List, Dict, Any, AsyncGenerator
from engine.Utils.PromptManager import PromptManager
from world.Entity import *
import logging
from engine.DataManager.WorldState import WorldState

# Thiết lập cấu hình cơ bản cho logging
logging.basicConfig(
    level=logging.ERROR,
    format='[%(asctime)s] %(name)s - %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class BaseCloudAgent:
    """
    Lớp cơ sở (Base Class) cho tất cả các Agent chạy trên nền tảng Cloud (Groq).
    Quản lý việc kết nối API, bộ đếm token, và cung cấp các hàm gọi LLM dùng chung.
    """

    # Biến class (static) để theo dõi tổng lượng token sử dụng của tất cả các Cloud Agent trong 1 lượt
    _turn_token_registry: Dict[str, int] = {}

    def __init__(self, api_key: str, pm: PromptManager, model_name: str):
        """
        Khởi tạo BaseCloudAgent.

        Args:
            api_key (str): Khóa API Groq.
            pm (PromptManager): Trình quản lý prompt để load template.
            model_name (str): Tên model LLM trên hệ thống Groq (VD: 'llama3-8b-8192').
        """
        self.client = AsyncGroq(api_key=api_key)
        self.model = model_name
        self.pm = pm

        self.logger = logging.getLogger(self.__class__.__name__)

        # Đăng ký Agent vào bộ đếm token nếu chưa có
        if self.__class__.__name__ not in BaseCloudAgent._turn_token_registry:
            BaseCloudAgent._turn_token_registry[self.__class__.__name__] = 0

    @classmethod
    def get_and_reset_token_usage(cls) -> str:
        """
        Tổng hợp báo cáo sử dụng token của tất cả các Agent trong lượt hiện tại,
        sau đó reset bộ đếm về 0 cho lượt tiếp theo.

        Returns:
            str: Chuỗi báo cáo chi tiết về lượng token đã sử dụng, hoặc chuỗi rỗng nếu không có dữ liệu.
        """
        total = sum(cls._turn_token_registry.values())
        if total == 0:
            return ""

        # Lọc ra danh sách các Agent có xài token để báo cáo
        details = " | ".join([f"{name}: {count}" for name, count in cls._turn_token_registry.items() if count > 0])
        report = f"[Groq Tokens] TỔNG CỘNG: {total} ({details})"

        # Reset bộ đếm về 0 cho lượt (turn) sau
        cls._turn_token_registry = {k: 0 for k in cls._turn_token_registry.keys()}
        return report

    async def _chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, stream: bool = False,
                    response_format: Dict = None, n: int = 1):
        """
        Hàm bao bọc (wrapper) để gọi API Groq chat completions một cách bất đồng bộ.

        Args:
            messages (List[Dict[str, str]]): Danh sách các message ngữ cảnh chứa luồng hội thoại.
            temperature (float, optional): Độ ngẫu nhiên của câu trả lời. Mặc định là 0.7.
            stream (bool, optional): Trả về stream data (True) hoặc đợi nhận toàn bộ một lần (False). Mặc định False.
            response_format (Dict, optional): Định dạng mong muốn (ví dụ: {"type": "json_object"}).
            n (int, optional): Số lượng phản hồi muốn tạo. Mặc định là 1.

        Returns:
            Response: Object response từ Groq API.
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            stream=stream,
            response_format=response_format,
            n=n
        )

        # Cập nhật số token đã dùng (chỉ áp dụng cho non-stream, đối với stream sẽ được tính ở hàm khác)
        if not stream and hasattr(response, 'usage') and response.usage:
            agent_name = self.__class__.__name__
            BaseCloudAgent._turn_token_registry[agent_name] += response.usage.total_tokens

        return response

    def _log_error(self, context: str, error: Exception):
        """
        Ghi log hệ thống khi có lỗi xảy ra trong quá trình gọi API.

        Args:
            context (str): Bối cảnh xảy ra lỗi (VD: tên hàm).
            error (Exception): Object lỗi bắt được (exception).
        """
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)

    async def _generate_json_with_retry(self, system_prompt: str, user_prompt: str, required_keys: List[str],
                                        max_retries: int = 3, temperature: float = 0.8) -> dict:
        """
        Gọi API và ép xuất dữ liệu dưới dạng JSON, bao gồm cơ chế kiểm tra và thử lại (retry) nếu LLM xuất sai.

        Args:
            system_prompt (str): Lệnh hệ thống quy định luật sinh JSON.
            user_prompt (str): Dữ liệu ngữ cảnh đầu vào của người chơi.
            required_keys (List[str]): Danh sách các key bắt buộc phải có trong JSON trả về.
            max_retries (int, optional): Số lần thử lại tối đa nếu JSON lỗi hoặc thiếu key. Mặc định là 3.
            temperature (float, optional): Độ ngẫu nhiên. Mặc định là 0.8.

        Returns:
            dict: Dictionary chứa dữ liệu hợp lệ, hoặc dictionary rỗng nếu thất bại sau max_retries.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        for attempt in range(1, max_retries + 1):
            try:
                # Gọi API ép buộc trả về JSON
                response = await self._chat(messages=messages, temperature=temperature, stream=False,
                                            response_format={"type": "json_object"})
                json_str = response.choices[0].message.content
                data = json.loads(json_str)

                # Xác thực kiểu dữ liệu
                if not isinstance(data, dict):
                    raise ValueError(f"Kết quả không phải là đối tượng JSON (Dictionary). Trả về kiểu: {type(data)}")

                # Kiểm tra các key thiết yếu
                missing_keys = [key for key in required_keys if key not in data]
                if missing_keys:
                    raise ValueError(f"JSON bị thiếu các key bắt buộc: {missing_keys}")

                return data

            except (json.JSONDecodeError, ValueError) as e:
                self.logger.warning(f"[Attempt {attempt}/{max_retries}] Lỗi trích xuất JSON: {e}")
                if attempt == max_retries:
                    self.logger.error(f"Đã thử {max_retries} lần nhưng vẫn lỗi. Đành trả về dict rỗng.")
                    return {}
                # Nghỉ nửa giây trước khi thử lại để tránh rate limit
                await asyncio.sleep(0.5)

            except Exception as e:
                self._log_error(f"Lỗi API trong lúc sinh JSON (Lần {attempt})", e)
                return {}

        return {}


class WorldGenerateAgent(BaseCloudAgent):
    """Agent thiết kế 'Kinh thánh Thế giới' (World Bible) tổng quan dựa trên ý tưởng của người chơi."""

    async def generate_bible(self, player_idea: str) -> dict:
        """
        Sinh dữ liệu World Bible dựa trên chủ đề (theme) mong muốn.

        Args:
            player_idea (str): Ý tưởng ban đầu do người chơi nhập vào (VD: "Cyberpunk phép thuật").

        Returns:
            dict: JSON chứa toàn bộ bối cảnh, luật lệ và hệ thống thuật ngữ của thế giới.
        """
        system_prompt = self.pm.get_prompt('WorldGenerateAgent', 'system')
        user_prompt = self.pm.get_prompt('WorldGenerateAgent', 'user', user_input=player_idea)

        return await self._generate_json_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            required_keys=[],
            temperature=0.4 # Temperature thấp để đảm bảo thế giới logic, nhất quán
        )


class NPCAgent(BaseCloudAgent):
    """Agent phụ trách thiết kế, khởi tạo và cập nhật trạng thái/tiểu sử của các NPC (Non-Player Characters)."""

    async def generate_npcs(self, npc_names: list, context: str) -> List[NPC]:
        """
        Sinh thông tin cho các NPC xuất hiện trong lượt hiện tại dựa trên tên được Router gửi xuống.

        Args:
            npc_names (list): Danh sách tên các NPC cần sinh (sinh ra ngẫu nhiên hoặc có chủ đích).
            context (str): Ngữ cảnh cốt truyện hiện tại để NPC được sinh ra phù hợp bối cảnh.

        Returns:
            List[dict]: Danh sách chứa dictionary thông tin chi tiết của từng NPC.
        """
        sys_prompt = self.pm.get_prompt('NPCAgent', 'system')
        names_str = ", ".join(npc_names)
        user_prompt = self.pm.get_prompt('NPCAgent', 'user', context=context, npc_names=names_str)

        return await self._generate_npcs(sys_prompt=sys_prompt, user_prompt=user_prompt, fallback_names=npc_names)

    async def initialize_npcs(self, world_state: WorldState) -> dict:
        """
        Sinh thông tin cho (các) NPC đầu tiên khi vừa khởi tạo thế giới mới (Prologue).

        Args:
            world_state (WorldState): Thông tin thế giới

        Returns:
            dict: Danh sách dictionary chứa thông tin chi tiết của (các) NPC khởi đầu.
        """
        world_name = world_state.world_name
        world_type = world_state.world_type
        world_theme = world_state.theme_and_tone
        world_conflict = world_state.core_conflict
        world_mission = world_state.world_mission

        sys_init = self.pm.get_prompt('NPCAgent', 'systemInit')
        user_init = self.pm.get_prompt('NPCAgent', 'userInit',
                                       world_name=world_name,
                                       world_type=world_type,
                                       world_theme=world_theme,
                                       world_conflict=world_conflict,
                                       world_mission=world_mission)

        return await self._generate_npcs(sys_prompt=sys_init, user_prompt=user_init, fallback_names=["Nhân vật bí ẩn"])

    async def _generate_npcs(self, sys_prompt: str, user_prompt: str, fallback_names: list, default_location: str = "Không rõ") -> List[NPC]:
        """
        Hàm nội bộ để sinh NPC JSON và trực tiếp ép kiểu thành object NPC.

        Args:
            sys_prompt (str): Prompt hệ thống điều khiển AI sinh NPC.
            user_prompt (str): Prompt chứa ngữ cảnh người dùng.
            fallback_names (list): Danh sách tên sử dụng làm mỏ neo nếu LLM lỗi.
            default_location (str): Dùng để điền vào vị trí của NPC nếu JSON không có.

        Returns:
            List[NPC]: Danh sách các thực thể NPC hoàn chỉnh.
        """
        required_keys = ["npcs"]
        result = await self._generate_json_with_retry(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.8
        )

        npc_list = []

        # Rào chắn an toàn: Nếu lỗi JSON, tạo NPC rỗng nhưng vẫn là Object chuẩn để game không crash
        if not result or "npcs" not in result:
            for name in fallback_names:
                npc_obj = NPC(
                    id=None,
                    name=name,
                    personality="Bí ẩn",
                    description="Một bóng người không rõ mặt",
                    affectionate=0,
                    location=default_location,
                    status="Bình thường"
                )
                npc_list.append(npc_obj)
            return npc_list

        # Ép kiểu dữ liệu từ JSON sang danh sách Object NPC
        for npc_data in result.get("npcs", []):
            npc_obj = NPC(
                id=None,
                name=npc_data.get("name", "Vô danh"),
                personality=npc_data.get("personality", "Bí ẩn"),
                description=npc_data.get("description", "Không rõ"),
                affectionate=npc_data.get("affectionate", 0),
                location=npc_data.get("location", default_location),
                status=npc_data.get("status", "Bình thường")
            )
            npc_list.append(npc_obj)

        return npc_list


class LocationAgent(BaseCloudAgent):
    """Agent chịu trách nhiệm miêu tả bối cảnh, bầu không khí và tạo ra các địa điểm mới trong game."""

    async def initialize_location(self, world_state: WorldState) -> Location:
        """
        Tạo địa điểm xuất phát (Starting Area) đầu tiên dựa trên World Bible.

        Args:
            world_state(WorldState): Thông tin thế giới

        Returns:
            Location: Object Location chứa tên, mô tả và bầu không khí của khu vực bắt đầu.
        """
        world_name = world_state.world_name
        world_type = world_state.world_type
        world_theme = world_state.theme_and_tone

        sys_init = self.pm.get_prompt('LocationAgent', 'systemInit')
        user_init = self.pm.get_prompt('LocationAgent', 'userInit', world_name=world_name, world_type=world_type,
                                       theme_and_tone=world_theme)
        return await self._generate_location(sys_init, user_init)

    async def generate_location(self, current_location: str, target_location: str, context: str) -> Location:
        """
        Tạo địa điểm mới khi người chơi di chuyển hoặc sự kiện thay đổi bối cảnh đột ngột.

        Args:
            current_location (str): Tên khu vực hiện tại người chơi đang đứng.
            target_location (str): Tên khu vực người chơi muốn đến (được trích xuất từ ý định).
            context (str): Ngữ cảnh hoặc lý do di chuyển.

        Returns:
            Location: Object Location mới do AI sáng tạo ra cho điểm đến.
        """
        sys_prompt = self.pm.get_prompt('LocationAgent', 'system')
        user_prompt = self.pm.get_prompt('LocationAgent', 'user', current_location=current_location,
                                         target_location_from_router=target_location, context=context)
        return await self._generate_location(sys_prompt, user_prompt)

    async def _generate_location(self, system_prompt: str, user_prompt: str) -> Location:
        """
        Hàm nội bộ để sinh Location object từ kết quả trả về bằng JSON của LLM.

        Args:
            system_prompt (str): Prompt hệ thống.
            user_prompt (str): Prompt dữ liệu người dùng.

        Returns:
            Location: Đối tượng bản đồ hoàn chỉnh. Cung cấp map vô danh nếu lỗi.
        """
        required_keys = ["location_name", "description", "atmosphere"]

        location_data = await self._generate_json_with_retry(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.8
        )

        # Fallback an toàn bảo vệ tiến trình game
        if not location_data:
            return Location(id=0, name="Vùng Đất Vô Danh", description="Mọi thứ mờ mịt...", atmosphere="bình thường")

        return Location(id=0, name=location_data['location_name'], description=location_data['description'],
                        atmosphere=location_data['atmosphere'])


class ChoiceAgent(BaseCloudAgent):
    """Agent phân tích tình huống hiện tại để gợi ý các hành động (menu options) khả thi cho người chơi."""

    async def generate_choices(self, current_location: str,
                               npc_name: str,
                               recent_story_summary: str,
                               active_quest_context: str,
                               quest_items: str) -> Dict[str, Any]:
        """
        Sinh ra danh sách các lựa chọn tình huống đa dạng, kích thích tương tác.

        Args:
            current_location (str): Tên địa điểm hiện tại.
            npc_name (str): Tên (các) NPC đang tương tác hoặc có mặt.
            recent_story_summary (str): Tóm tắt nội dung cốt truyện gần nhất.
            active_quest_context (str): Tóm tắt nhiệm vụ hiện tại đang theo dõi.
            quest_items (str): Các item liên quan trực tiếp đến nhiệm vụ đang theo.

        Returns:
            Dict[str, Any]: JSON chứa danh sách các lựa chọn (choices). Mỗi lựa chọn gồm id, action_text, style.
        """
        sys_prompt = self.pm.get_prompt('ChoiceAgent', 'system')
        user_prompt = self.pm.get_prompt('ChoiceAgent', 'user',
                                         current_location=current_location,
                                         npc_name=npc_name,
                                         recent_story_summary=recent_story_summary,
                                         active_quest_context=active_quest_context,
                                         quest_items=quest_items)

        required_keys = ["choices"]

        result = await self._generate_json_with_retry(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            required_keys=required_keys,
            temperature=0.7
        )

        # Tùy chọn cơ bản phòng hờ lỗi sinh JSON
        if not result:
            return {"choices": [{"id": 1, "action_text": "Tiếp tục quan sát xung quanh", "style": "Thận trọng"}]}
        return result


class StoryAgent(BaseCloudAgent):
    """Agent đóng vai trò Game Master (GM): Kể chuyện, phản hồi hành động và dẫn dắt luồng game dạng Streaming."""

    async def initialize_story(self, name: str, theme: str, core_conflict: str, mission: str, vocab: dict,
                               location_name: str, location_atmosphere: str,
                               location_description: str) -> AsyncGenerator[str, None]:
        """
        Sinh đoạn văn bản mở màn (Prologue) dạng luồng (stream) khi game mới bắt đầu.

        Args:
            name (str): Tên thế giới.
            theme (str): Tông màu thế giới.
            core_conflict (str): Xung đột chính.
            mission (str): Mục tiêu toàn cục.
            vocab (dict): Bộ từ vựng/thuật ngữ tùy chỉnh của thế giới.
            location_name (str): Tên địa điểm xuất phát.
            location_atmosphere (str): Bầu không khí tại điểm xuất phát.
            location_description (str): Mô tả chi tiết địa điểm.

        Yields:
            str: Từng cụm từ (chunk) của đoạn mở đầu để in ra giao diện real-time.
        """
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
                             current_location: str, npc_context: str, rag_context: str,
                             system_directive: str, user_input: str,
                             active_quest_context: str, quest_items: str) -> AsyncGenerator[str, None]:
        """
        Sinh diễn biến cốt truyện tiếp theo (Streaming) dựa trên hành động của người chơi và ngữ cảnh RAG.

        Args:
            world_theme (str): Tông màu bối cảnh thế giới.
            world_conflict (str): Xung đột chính.
            world_vocabulary (dict): Từ vựng thế giới.
            current_location (str): Nơi đang đứng.
            npc_context (str): Các NPC xung quanh.
            rag_context (str): Ký ức truy xuất được từ VectorDB.
            system_directive (str): Các chỉ thị bắt buộc từ hệ thống (VD: dùng đồ thất bại, ép chuyển map).
            user_input (str): Lệnh/Câu thoại của người chơi.
            active_quest_context (str): Context về nhiệm vụ.
            quest_items (str): Đồ vật phục vụ quest.

        Yields:
            str: Từng mảnh văn bản của GM.
        """
        sys_prompt = self.pm.get_prompt(
            'StoryAgent', 'system',
            world_theme=world_theme, world_conflict=world_conflict, world_vocabulary=world_vocabulary,
            current_location=current_location, npc_context=npc_context,
            rag_context=rag_context, valid_paths_from_sql=None, system_directive=system_directive,
            active_quest_context=active_quest_context, quest_items=quest_items
        )
        user_prompt = self.pm.get_prompt('StoryAgent', 'user', user_input=user_input)

        async for chunk in self._generate_stream(system_prompt=sys_prompt, user_prompt=user_prompt):
            yield chunk

    async def _generate_stream(self, system_prompt: str, user_prompt: str) -> AsyncGenerator[str, None]:
        """
        Hàm nội bộ để gọi API Groq và yield dữ liệu trả về liên tục (streaming) cho giao diện người dùng.

        Args:
            system_prompt (str): Lệnh hệ thống.
            user_prompt (str): Lệnh người dùng.

        Yields:
            str: Từng phần text do LLM trả về.
        """
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            # Gọi chat completions với chế độ stream=True
            stream = await self._chat(messages=messages, temperature=0.9, stream=True)

            async for chunk in stream:
                # Xử lý nội dung văn bản (delta)
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content

                # Groq trả về thống kê usage ở chunk cuối cùng, ta cần bắt lấy nó để tính token
                if hasattr(chunk, 'x_groq') and chunk.x_groq is not None:
                    if hasattr(chunk.x_groq, 'usage') and chunk.x_groq.usage:
                        usage = chunk.x_groq.usage
                        agent_name = self.__class__.__name__
                        BaseCloudAgent._turn_token_registry[agent_name] += usage.total_tokens

        except Exception as e:
            self._log_error("generate_stream", e)
            yield "Có một sự xáo trộn trong không gian... (Lỗi kết nối cốt truyện)"


class QueryAgent(BaseCloudAgent):
    """Agent phụ trách việc tóm tắt ngữ cảnh hiện tại thành câu truy vấn (Query) tối ưu để tìm kiếm RAG trong VectorDB."""

    async def generate_query(self, current_location: str, npc_names: list, context: str) -> str:
        """
        Tổng hợp câu lệnh tìm kiếm ngữ nghĩa từ trạng thái hiện hành, tối ưu hóa từ khóa cho FAISS.

        Args:
            current_location (str): Địa điểm hiện hành.
            npc_names (list): Danh sách NPC liên quan đang có trong bối cảnh.
            context (str): Cửa sổ ngữ cảnh (Short term memory) vài lượt gần nhất.

        Returns:
            str: Câu truy vấn để nạp vào cơ chế VectorDB (FAISS).
        """
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
            # Sinh ra câu query ngắn gọn nên để temperature thấp, stream=False
            response = await self._chat(messages=messages, temperature=0.2, stream=False)

            # Cắt bỏ các ký tự thừa như dấu ngoặc kép bọc ngoài
            return response.choices[0].message.content.strip().strip('"\'')
        except Exception as e:
            self._log_error("generate_query", e)
            return ""


class CombatAgent(BaseCloudAgent):
    async def extract_combat(self, story_response: str) -> dict:
        sys_prompt = self.pm.get_prompt('CombatAgent', 'system')
        user_prompt = self.pm.get_prompt('CombatAgent', 'user', story_response=story_response)
        required_keys = ["taken_damage"]
        result = await self._generate_json_with_retry(system_prompt = sys_prompt, user_prompt = user_prompt, required_keys = required_keys)
        return result if result else {"taken_damage": 0}