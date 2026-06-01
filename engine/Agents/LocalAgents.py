import json
import re
import logging
from typing import Dict, Any

# Sử dụng SDK mới của Google
from google import genai
from google.genai import types

from engine.Utils.PromptManager import PromptManager
from engine.Utils.logger import game_logger
from world.Entity import Item, ConsumableItem, WeaponItem, QuestItem


class BaseLocalAgent:
    """
    Class Cha (Base Class) chịu trách nhiệm gọi Google Gemini API SDK MỚI.
    """

    def __init__(self, pm: PromptManager, model_name: str = "gemini-3.1-flash-lite", gemini_api_key: str = None, **kwargs):
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

    # Giữ nguyên tham số max_tokens để tương thích ngược, dù Gemini có thể tự linh hoạt
    async def _generate_json(self, system_prompt: str, user_prompt: str, max_tokens: int = 200) -> Dict[str, Any]:
        """
        Hàm dùng chung để ép LLM trả về JSON chuẩn xác bằng Gemini SDK mới.
        """
        if not self.client:
            self.logger.error("[Gemini] Client chưa được khởi tạo. Không thể sinh nội dung.")
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
                return json.loads(match.group(0).replace('\n', ' ').replace('\r', ''))
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
        inventory_str = ", ".join([item.name for item in player_state.inventory]) if player_state.inventory else "Trống rỗng"
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
                "scene_emotion": "bình thường",
                "affection_changes": []
            }

        return result


class MemoryExtractor(BaseLocalAgent):
    """
    Agent Phân tích Ký ức: Bóc tách các sự kiện quan trọng.
    """

    async def extract_memory(self, player_input: str, story_response: str) -> dict:
        # 1. Lấy thẳng System Prompt (Đã bao gồm sẵn luật và ví dụ trong file yaml)
        sys_prompt = self.pm.get_prompt("MemoryExtractor", 'system')

        # 2. Lấy User Prompt
        user_prompt = self.pm.get_prompt(
            'MemoryExtractor',
            'user',
            player_input=player_input,
            story_response=story_response
        )

        # 3. Gọi API Gemini
        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=200
        )

        # 4. Trả về an toàn
        if not result or "atomic_memories" not in result:
            self.logger.warning("[MemoryExtractor] Trả về cấu trúc trống hoặc thiếu key 'atomic_memories'.")
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


class ItemAgent(BaseLocalAgent):
    """Agent phan loai va chuan hoa item thanh cac loai vat pham game."""

    def _fallback_item_spec(self, item_name: str, context: str = "") -> Dict[str, Any]:
        full_text = f"{item_name} {context}".lower()

        if any(keyword in full_text for keyword in ["kiếm", "dao", "súng", "rìu", "cung", "kiem", "weapon", "blade"]):
            return {
                "name": item_name,
                "item_type": "WeaponItem",
                "description": f"Một vũ khí tên {item_name}.",
                "damage": 5,
                "rarity": "common"
            }

        if any(keyword in full_text for keyword in ["thuốc", "nước", "bình", "kẹo", "tăng lực", "potion", "elixir", "medkit"]):
            return {
                "name": item_name,
                "item_type": "ConsumableItem",
                "description": f"Vật phẩm sử dụng được mang tên {item_name}.",
                "effect": {"kind": "heal", "value": 10, "duration_turns": 0, "target": "player"}
            }

        return {
            "name": item_name,
            "item_type": "QuestItem",
            "description": f"Vật phẩm cốt truyện mang tên {item_name}."
        }

    async def classify_item(self, item_name: str, context: str = "") -> Dict[str, Any]:
        sys_prompt = self.pm.get_prompt("ItemAgent", "system")
        user_prompt = self.pm.get_prompt("ItemAgent", "user", item_name=item_name, context=context)

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=220
        )

        if not result:
            return self._fallback_item_spec(item_name, context)

        item_type = str(result.get("item_type", "")).strip()
        if item_type not in {"ConsumableItem", "WeaponItem", "QuestItem"}:
            return self._fallback_item_spec(item_name, context)

        result.setdefault("name", item_name)
        result.setdefault("description", f"Vật phẩm {item_name}.")

        if item_type == "ConsumableItem":
            result.setdefault(
                "effect",
                {"kind": "heal", "value": 10, "duration_turns": 0, "target": "player"}
            )
        elif item_type == "WeaponItem":
            result.setdefault("damage", 0)
            result.setdefault("rarity", "common")

        return result

    def build_item_object(self, item_data: Dict[str, Any], fallback_name: str = "Vật phẩm"):
        item_name = item_data.get("name") or fallback_name
        description = item_data.get("description") or f"Vật phẩm {item_name}."
        item_type = str(item_data.get("item_type", "QuestItem")).strip()

        if item_type == "ConsumableItem":
            effect = item_data.get("effect") or {"kind": "heal", "value": 10, "duration_turns": 0, "target": "player"}
            item = ConsumableItem(
                id=None,
                name=item_name,
                description=description,
                effect=effect,
                quest_id=item_data.get("quest_id")
            )
        elif item_type == "WeaponItem":
            item = WeaponItem(
                id=None,
                name=item_name,
                description=description,
                damage=int(item_data.get("damage") or 0),
                rarity=str(item_data.get("rarity") or "common"),
                quest_id=item_data.get("quest_id")
            )
        elif item_type == "QuestItem":
            item = QuestItem(
                id=None,
                name=item_name,
                description=description,
                quest_id=item_data.get("quest_id")
            )
        else:
            item = Item(
                id=None,
                name=item_name,
                description=description,
                item_type=item_type,
                effect=item_data.get("effect", {}),
                quest_id=item_data.get("quest_id")
            )

        if item_data.get("image_path"):
            item.image_path = item_data["image_path"]

        if item_data.get("quote"):
            item.quote = item_data["quote"]

        return item


class QuestAgent(BaseLocalAgent):
    """Agent tao va kiem tra quest phu theo boi canh hien tai."""

    def _fallback_reward(self, quest_data: Dict[str, Any]) -> Dict[str, Any]:
        difficulty = str(quest_data.get("difficulty", "easy")).lower()
        if difficulty in {"medium", "hard"}:
            return {
                "item_type": "WeaponItem",
                "name": f"Thưởng từ {quest_data.get('title', 'nhiệm vụ')}",
                "description": "Một phần thưởng dạng vũ khí.",
                "damage": 5,
                "rarity": "common"
            }

        return {
            "item_type": "ConsumableItem",
            "name": f"Thưởng từ {quest_data.get('title', 'nhiệm vụ')}",
            "description": "Một phần thưởng dùng được ngay.",
            "effect": {"kind": "heal", "value": 15, "duration_turns": 0, "target": "player"}
        }

    def _fallback_quest(self, current_location: str, current_npcs: str, inventory: str) -> Dict[str, Any]:
        return {
            "title": f"Nhiệm vụ phụ ở {current_location}",
            "description": "Làm một việc nhỏ để đổi lấy phần thưởng.",
            "objectives": ["Quan sát khu vực", "Nói chuyện với người liên quan"],
            "linked_npc_names": [name.strip() for name in current_npcs.split(",") if name.strip() and current_npcs != "Không có ai"],
            "linked_location": current_location,
            "difficulty": "easy",
            "reward": self._fallback_reward({"title": f"Nhiệm vụ phụ ở {current_location}", "difficulty": "easy"})
        }

    async def generate_side_quest(self, story_response: str, current_location: str, current_npcs: str, inventory: str) -> Dict[str, Any]:
        sys_prompt = self.pm.get_prompt("QuestAgent", "systemGenerate")
        user_prompt = self.pm.get_prompt(
            "QuestAgent",
            "userGenerate",
            story_response=story_response,
            current_location=current_location,
            current_npcs=current_npcs,
            inventory=inventory,
        )

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=280
        )

        if not result or "title" not in result:
            return self._fallback_quest(current_location, current_npcs, inventory)

        result.setdefault("description", "")
        result.setdefault("objectives", [])
        result.setdefault("linked_npc_names", [])
        result.setdefault("linked_location", current_location)
        result.setdefault("difficulty", "easy")
        result.setdefault("reward", self._fallback_reward(result))

        reward = result.get("reward") or self._fallback_reward(result)
        if reward.get("item_type") not in {"ConsumableItem", "WeaponItem"}:
            reward = self._fallback_reward(result)
        result["reward"] = reward

        return result

    async def evaluate_quest(
        self,
        quest_data: Dict[str, Any],
        story_response: str,
        current_location: str,
        current_npcs: str,
        inventory: str,
    ) -> Dict[str, Any]:
        sys_prompt = self.pm.get_prompt("QuestAgent", "systemEvaluate")
        user_prompt = self.pm.get_prompt(
            "QuestAgent",
            "userEvaluate",
            quest_json=json.dumps(quest_data, ensure_ascii=False),
            story_response=story_response,
            current_location=current_location,
            current_npcs=current_npcs,
            inventory=inventory,
        )

        result = await self._generate_json(
            system_prompt=sys_prompt,
            user_prompt=user_prompt,
            max_tokens=260
        )

        if not result:
            return {
                "is_completed": False,
                "progress_notes": "",
                "matched_objectives": [],
                "missing_objectives": quest_data.get("objectives", []),
                "reward": None,
            }

        result.setdefault("is_completed", False)
        result.setdefault("progress_notes", "")
        result.setdefault("matched_objectives", [])
        result.setdefault("missing_objectives", quest_data.get("objectives", []))
        result.setdefault("reward", None)

        if result.get("is_completed") and not result.get("reward"):
            result["reward"] = self._fallback_reward(quest_data)

        reward = result.get("reward")
        if reward and reward.get("item_type") not in {"ConsumableItem", "WeaponItem"}:
            result["reward"] = self._fallback_reward(quest_data)

        return result