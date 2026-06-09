"""
Chứa các Local Agent (Hỗ trợ cả Gemini API và Ollama Local)
"""
import json
import re
import logging
import httpx
from typing import Dict, Any, List

from google import genai
from google.genai import types
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from engine.Utils.logger import game_logger
from world.Entity import ConsumableItem, QuestItem, MiscellaneousItem, WeaponItem, BaseItem, Quest
from static.config import (GEMINI_INTENT_ROUTER_MODEL, GEMINI_ITEM_AGENT_MODEL, GEMINI_MEMORY_EXTRACTOR_MODEL,
                           GEMINI_QUEST_AGENT_MODEL, GEMINI_STATE_EXTRACTOR_MODEL,
                           OLLAMA_INTENT_ROUTER_MODEL, OLLAMA_ITEM_AGENT_MODEL, OLLAMA_MEMORY_EXTRACTOR_MODEL,
                           OLLAMA_QUEST_AGENT_MODEL, OLLAMA_STATE_EXTRACTOR_MODEL, GEMINI_MUSIC_CLASSIFIER,
                           OLLAMA_MUSIC_CLASSIFIER)


class BaseLocalAgent:
    """
    Lớp cơ sở (Base Class) quản lý việc giao tiếp với LLM.
    Hỗ trợ định tuyến luồng gọi API tới Google Gemini hoặc Ollama cục bộ.
    """

    def __init__(self, pm: PromptManager,
                 provider: str = "gemini",
                 api_key:str = None,
                 ollama_host: str = "http://localhost:11434"):

        self.pm = pm
        self.provider = provider.lower()
        self.logger = logging.getLogger(self.__class__.__name__)
        self.model_name = None

        # Cấu hình Gemini
        self.api_key = api_key
        self.gemini_client = None

        # Cấu hình Ollama
        self.ollama_host = ollama_host

        # Khởi tạo Client nếu dùng Gemini
        if self.provider == "gemini":
            try:
                if self.api_key:
                    self.gemini_client = genai.Client(api_key=self.api_key)
                else:
                    game_logger.error(f'[Gemini] Thiếu api key')
            except Exception as e:
                game_logger.warning(f"[Gemini] Lỗi khởi tạo Client: {e}")


    def _log_error(self, context: str, error: Exception):
        """Ghi log lỗi chi tiết kèm theo Stack Trace."""
        self.logger.error(f"Lỗi tại {context}: {str(error)}", exc_info=True)

    async def _generate_json(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """
        Gọi LLM (Gemini hoặc Ollama) và ép kiểu dữ liệu trả về dưới dạng JSON dictionary.
        """
        if self.provider == "gemini":
            return await self._generate_json_gemini(system_prompt, user_prompt)
        elif self.provider == "ollama":
            return await self._generate_json_ollama(system_prompt, user_prompt)
        else:
            self.logger.error(f"Provider không hợp lệ: {self.provider}")
            return {}

    async def _generate_json_gemini(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Xử lý luồng gọi Google Gemini API với cơ chế tự động thử lại (Retry) và bóc tách Regex."""
        if not self.gemini_client:
            self.logger.error("[Gemini] Client chưa được khởi tạo.")
            return {}

        import asyncio
        max_retries = 3
        
        for attempt in range(1, max_retries + 1):
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    temperature=0.0,
                )

                response = await self.gemini_client.aio.models.generate_content(
                    model=self.model_name,
                    contents=user_prompt,
                    config=config,
                )

                raw_content = response.text
                try:
                    return json.loads(raw_content)
                except json.JSONDecodeError:
                    data = self._parse_json_safely(raw_content)
                    if data:
                        return data
                    raise ValueError("JSON parsing failed")

            except Exception as e:
                self.logger.warning(f"[Gemini Attempt {attempt}/{max_retries}] Lỗi: {e}")
                
                if attempt < max_retries:
                    # Check for rate limit / quota exhaustion (HTTP 429)
                    if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                        import re
                        match = re.search(r'retry in ([0-9.]+)s', str(e), re.IGNORECASE)
                        if match:
                            sleep_time = float(match.group(1)) + 0.5
                            self.logger.info(f"[Gemini 429 Rate Limit] Đang chờ {sleep_time}s theo yêu cầu của API...")
                        else:
                            sleep_time = 2.0 * attempt
                            self.logger.info(f"[Gemini Rate Limit] Đang chờ {sleep_time}s trước khi thử lại...")
                        await asyncio.sleep(sleep_time)
                    else:
                        # For other exceptions, sleep a shorter time
                        await asyncio.sleep(0.5 * attempt)
                    
                    # Thử lại không dùng response_mime_type làm fallback phòng khi server/model từ chối cấu hình JSON
                    try:
                        config_fallback = types.GenerateContentConfig(
                            system_instruction=system_prompt,
                            temperature=0.0,
                        )
                        response = await self.gemini_client.aio.models.generate_content(
                            model=self.model_name,
                            contents=user_prompt,
                            config=config_fallback,
                        )
                        raw_content = response.text
                        data = self._parse_json_safely(raw_content)
                        if data:
                            self.logger.info(f"[Gemini Fallback] Khôi phục JSON thành công ở lượt thử {attempt}")
                            return data
                    except Exception as fallback_err:
                        self.logger.warning(f"[Gemini Fallback attempt {attempt}] Lỗi: {fallback_err}")
                else:
                    self._log_error("_generate_json_gemini thất bại sau nhiều lượt thử", e)

        return {}

    async def _generate_json_ollama(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Xử lý luồng gọi Ollama Local API."""
        payload = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "format": "json",      # Ép Ollama trả về chuẩn JSON
            "stream": False,
            "options": {
                "temperature": 0.0 # Đảm bảo tính nhất quán của output
            }
        }

        try:
            # Sử dụng httpx để gọi API bất đồng bộ. Đặt timeout cao vì Local LLM xử lý JSON có thể chậm.
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.ollama_host}/api/chat",
                    json=payload,
                    timeout=120.0
                )
                response.raise_for_status()

                data = response.json()
                raw_content = data.get("message", {}).get("content", "")

                try:
                    return json.loads(raw_content)
                except json.JSONDecodeError:
                    return self._parse_json_safely(raw_content)

        except httpx.RequestError as e:
            self._log_error(f"_generate_json_ollama (Không thể kết nối tới Ollama tại {self.ollama_host})", e)
            return {}
        except Exception as e:
            self._log_error("_generate_json_ollama", e)
            return {}

    def _parse_json_safely(self, text: str) -> dict:
        """Trích xuất khối JSON từ văn bản thô bằng Regex."""
        try:
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                return json.loads(match.group().replace('\n', ' ').replace('\r', ''))
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
    Agent phân tích cú pháp và phân loại ý định (intent) từ hành động của người chơi.
    """
    def __init__(self, pm: PromptManager,
                 provider: str = "gemini",
                 api_key: str = None,
                 ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_INTENT_ROUTER_MODEL
        else:
            self.model_name = OLLAMA_INTENT_ROUTER_MODEL

    async def parse_intent(self, player_input: str) -> Dict[str, Any]:
        """
        Phân loại hành động của người chơi thành các Intent chuẩn của hệ thống.

        Args:
            player_input (str): Câu lệnh đầu vào của người chơi.

        Returns:
            Dict[str, Any]: Chứa 'intent', 'target', và 'action_details'.
        """
        sys_prompt = self.pm.get_prompt('IntentRouter', 'system')
        user_prompt = self.pm.get_prompt('IntentRouter', 'user', user_input=player_input)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )

        if not result or "intent" not in result:
            return {"intent": "UNKNOWN", "target": None, "action_details": player_input}

        return result


class StateExtractor(BaseLocalAgent):
    """
    Agent theo dõi và trích xuất sự thay đổi trạng thái của game (Vật phẩm, NPC, Địa điểm).
    """
    def __init__(self, pm: PromptManager,
                 provider: str = "gemini",
                 api_key: str = None,
                 ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_STATE_EXTRACTOR_MODEL
        else:
            self.model_name = OLLAMA_STATE_EXTRACTOR_MODEL

    async def extract_state(self, player_input: str, story_response: str, player_state: PlayerState) -> Dict[str, Any]:
        """
        Phân tích cốt truyện vừa diễn ra để cập nhật các thay đổi vào CSDL.

        Args:
            player_input (str): Hành động của người chơi.
            story_response (str): Phản hồi cốt truyện từ Game Master.
            player_state (PlayerState): Trạng thái hiện tại của người chơi.

        Returns:
            Dict[str, Any]: Các thay đổi về items, npcs, location, emotion, v.v.
        """
        all_item_names = player_state.get_all_item_names()
        inventory_str = ", ".join([item for item in all_item_names]) if all_item_names else "Trống rỗng"
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
            user_prompt=user_prompt
        )

        if not result:
            self.logger.warning("[StateExtractor] Fallback kích hoạt do không nhận được JSON hợp lệ.")
            return {
                "items_added": [],
                "items_removed": [],
                "npcs_arrived": [],
                "npcs_left": [],
                "new_location_entered": None,
                "scene_emotion": "bình thường",
                "affection_changes": []
            }

        return result


class MemoryExtractor(BaseLocalAgent):
    """
    Agent bóc tách và tóm tắt các sự kiện cốt lõi để lưu vào Vector Database.
    """
    def __init__(self, pm: PromptManager,
                 provider: str = "gemini",
                 api_key: str = None,
                 ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_MEMORY_EXTRACTOR_MODEL
        else:
            self.model_name = OLLAMA_MEMORY_EXTRACTOR_MODEL

    async def extract_memory(self, player_input: str, story_response: str) -> dict:
        """
        Trích xuất các mảnh ký ức (atomic memories) từ lượt tương tác hiện tại.

        Args:
            player_input (str): Hành động của người chơi.
            story_response (str): Phản hồi từ hệ thống.

        Returns:
            dict: Danh sách các mảnh ký ức đã được chuẩn hóa.
        """
        sys_prompt = self.pm.get_prompt("MemoryExtractor", 'system')
        user_prompt = self.pm.get_prompt(
            'MemoryExtractor',
            'user',
            player_input=player_input,
            story_response=story_response
        )

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )

        if not result or "atomic_memories" not in result:
            self.logger.warning("[MemoryExtractor] Trả về cấu trúc trống hoặc thiếu key 'atomic_memories'.")
            return {"atomic_memories": []}

        return result


class MusicClassifier(BaseLocalAgent):
    """
    Agent phân tích sắc thái bối cảnh để điều phối nhạc nền của game.
    """
    def __init__(self, pm: PromptManager,
                 provider: str = "gemini",
                 api_key: str = None,
                 ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_MUSIC_CLASSIFIER
        else:
            self.model_name = OLLAMA_MUSIC_CLASSIFIER

    async def classify_emotion(self, atmosphere_text: str) -> str:
        """
        Xác định cảm xúc chủ đạo của một phân cảnh.

        Args:
            atmosphere_text (str): Đoạn văn bản mô tả bối cảnh hoặc không khí.

        Returns:
            str: Tên cảm xúc (VD: 'bình thường', 'căng thẳng', 'buồn'...).
        """
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

        result = await self._generate_json(sys_prompt, user_prompt)

        if result and "emotion" in result:
            emotion = str(result["emotion"]).lower().strip()
            valid_emotions = ["bình thường", "căng thẳng", "buồn", "vui", "sợ hãi"]

            if emotion in valid_emotions:
                return emotion

        return "bình thường"


class ItemAgent(BaseLocalAgent):
    """
    Agent phụ trách sinh chỉ số cho vật phẩm mới và thẩm định logic khi người chơi chế tạo đồ.
    """
    def __init__(self, pm: PromptManager,
             provider: str = "gemini",
             api_key: str = None,
             ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_ITEM_AGENT_MODEL
        else:
            self.model_name = OLLAMA_ITEM_AGENT_MODEL

    async def generate_item(self, context: str, item_name: str, item_type: str, quest=None) -> BaseItem:
        """
        Tạo đối tượng vật phẩm hoàn chỉnh với các chỉ số tương ứng dựa vào ngữ cảnh.

        Args:
            context (str): Ngữ cảnh hoặc lý do vật phẩm xuất hiện.
            item_name (str): Tên vật phẩm.
            item_type (str): Phân loại vật phẩm ('weapon', 'consumable', 'quest', 'miscellaneous').
            quest (optional): Thông tin nhiệm vụ đính kèm nếu là quest item.

        Returns:
            BaseItem: Đối tượng vật phẩm đã được khởi tạo theo đúng class tương ứng.
        """
        sys_prompt = self.pm.get_prompt('ItemAgent', 'systemGenerate')
        user_prompt = self.pm.get_prompt('ItemAgent', 'userGenerate',
                                         context=context, item_name=item_name, item_type=item_type)

        item_json = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )

        if item_type == 'weapon':
            new_item = WeaponItem(
                id=None,
                name=item_json.get("name", item_name),
                description=item_json.get("description", ""),
                base_damage=item_json.get("base_damage", 0),
                modifiers=item_json.get("modifiers", {}),
                status_effect=item_json.get("status_effect"),
                proc_chance=item_json.get("proc_chance", 0.0)
            )
        elif item_type == 'consumable':
            new_item = ConsumableItem(
                id=None,
                name=item_json.get("name", item_name),
                description=item_json.get("description", ""),
                effect=item_json.get("effect", 0)
            )

        elif item_type == 'quest':
            new_item = QuestItem(
                id=None,
                name=item_json.get("name", item_name),
                description=item_json.get("description", ""),
                quest=quest
            )

        else:
            new_item = MiscellaneousItem(
                id=None,
                name=item_json.get("name", item_name),
                description=item_json.get("description", 'a random item')
            )

        return new_item

    async def craft(self, action_details: str, items_str: str) -> dict:
        """
        Đánh giá tính logic và khả thi khi người chơi kết hợp nhiều vật phẩm với nhau

        Args:
            action_details (str): Ý định hoặc cách thức người chơi muốn kết hợp.
            items_str (str): Chuỗi mô tả các vật phẩm nguyên liệu.

        Returns:
            dict: Kết quả chế tạo (success, reasoning, và thông tin new_item nếu thành công).
        """
        sys_prompt = self.pm.get_prompt('ItemAgent', 'systemCraft')
        user_prompt = self.pm.get_prompt('ItemAgent', 'userCraft',
                                         action_details=action_details,
                                         items_list=items_str)

        return await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )


    async def use(self, action_details: str, items_str: str) -> dict:
        """
        Đánh giá tính logic và khả thi khi người chơi kết hợp nhiều vật phẩm với nhau

        Args:
            action_details (str): Ý định hoặc cách thức người chơi muốn kết hợp.
            items_str (str): Chuỗi mô tả các vật phẩm nguyên liệu.

        Returns:
            dict: Kết quả chế tạo (success, reasoning, và thông tin new_item nếu thành công).
        """
        sys_prompt = self.pm.get_prompt('ItemAgent', 'systemUse')
        user_prompt = self.pm.get_prompt('ItemAgent', 'userUse',
                                         action_details=action_details,
                                         items_list=items_str)

        return await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )


class QuestAgent(BaseLocalAgent):
    """
    Agent chuyên trách xử lý vòng đời của Nhiệm vụ (Sinh nhiệm vụ mới và Nghiệm thu).
    """
    def __init__(self, pm: PromptManager,
             provider: str = "gemini",
             api_key: str = None,
             ollama_host: str = "http://localhost:11434"):
        super().__init__(pm = pm, provider = provider, api_key = api_key, ollama_host = ollama_host)
        if provider == 'gemini':
            self.model_name = GEMINI_QUEST_AGENT_MODEL
        else:
            self.model_name = OLLAMA_QUEST_AGENT_MODEL

    async def initialize_main_quest(self, world_name: str,
                                    world_theme: str,
                                    world_conflict: str,
                                    world_mission: str,
                                    key_npcs: str) -> dict:
        """
        Khởi tạo Nhiệm vụ chính (Epic Campaign) dựa trên Kinh thánh thế giới và các NPC quan trọng.
        """
        sys_prompt = self.pm.get_prompt('QuestAgent', 'systemInit')
        user_prompt = self.pm.get_prompt('QuestAgent', 'userInit',
                                         world_name=world_name,
                                         world_theme=world_theme,
                                         world_conflict=world_conflict,
                                         world_mission=world_mission,
                                         key_npcs=key_npcs)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )

        return result

    
    async def generate_quests(self, location_name: str, npc_names: str, context: str) -> Quest:
        """
        Dựa vào bối cảnh, địa điểm và NPC hiện tại để sinh ra các nhiệm vụ phụ phù hợp.
        """
        sys_prompt = self.pm.get_prompt('QuestAgent', 'systemGenerate')
        user_prompt = self.pm.get_prompt('QuestAgent', 'userGenerate',
                                         location=location_name, npcs=npc_names, context=context)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt
        )
        while isinstance(result, list):
            result = result[0]
        quest = Quest(
            id = None,
            name=result.get("title", "không rõ"),
            description=result.get("description", "None"),
            objectives=result.get("objectives", []),
            give_by = result.get("give_by", "không rõ"),
            rewards=result.get("rewards", [])
        )

        return quest

    async def evaluate_quest_status(self, quest_title: str, objectives: List[str], player_input: str,
                                    story_response: str) -> Dict[str, Any]:
        """
        Đọc hành động của người chơi và phản hồi của cốt truyện để đánh giá xem
        mục tiêu nhiệm vụ đã được hoàn thành hay chưa.
        """
        objectives_str = ""
        for objective in objectives:
            objectives_str += f"- {objective}\n"
        sys_prompt = self.pm.get_prompt('QuestAgent', 'systemEvaluate')
        user_prompt = self.pm.get_prompt('QuestAgent', 'userEvaluate',
                                         quest_title=quest_title,
                                         objectives=objectives_str,
                                         player_input=player_input,
                                         story_response=story_response)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
        )

        # Đảm bảo có key mặc định nếu LLM lỗi
        if not result or "objectives_status" not in result or "is_new_quest_offered" not in result:
            return {"reasoning": "Không thể phân tích ngữ nghĩa.", "objective_status": [0] * len(objectives), "is_new_quest_offered": False}

        return result

    def _format_quest_info(self, quest:Quest) -> str:
        """Hàm phụ trợ để trích xuất thông tin Quest thành chuỗi cho LLM"""
        if not quest:
            return "- Mạch truyện chính (Tự do khám phá, không gò bó mục tiêu)"

        objectives_str = ""
        for objective in quest.objectives:
            objectives_str += f"- {objective}\n"

        info = f"- Tên nhiệm vụ: {quest.name}\n"
        info += f"- Mô tả: {quest.description}\n"
        info += f"- Mục tiêu\n: {objectives_str}"
        if hasattr(quest, 'status'):
            info += f"- Trạng thái hiện tại: {quest.status}\n"
        return info


    async def generate_transition_narrative(self, source_quest: Quest, target_quest: Quest, recent_story: str) -> str:
        """
        Sinh ra đoạn văn miêu tả sự chuyển hướng chú ý của người chơi.
        """
        # Bóc tách thông tin từ Object
        source_info = self._format_quest_info(source_quest)
        target_info = self._format_quest_info(target_quest)

        sys_prompt = self.pm.get_prompt('QuestAgent', 'systemTransitionNarrative')
        user_prompt = self.pm.get_prompt('QuestAgent', 'userTransitionNarrative',
                                         source_info=source_info,
                                         target_info=target_info,
                                         recent_story=recent_story)

        result = await self._generate_json(system_prompt=sys_prompt, user_prompt=user_prompt)

        # Mặc định nếu LLM lỗi
        fallback_name = target_quest.name if target_quest else "Mạch truyện chính"
        fallback_msg = f"Bạn quyết định chuyển hướng tập trung sang: {fallback_name}."

        if not result or "transition_text" not in result:
            return fallback_msg

        return result.get("transition_text", fallback_msg)