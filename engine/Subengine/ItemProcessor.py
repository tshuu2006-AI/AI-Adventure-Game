from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from world.Entity import BaseItem
from typing import Dict, Any, List, Tuple
from world.Entity import WeaponItem, ConsumableItem, MiscellaneousItem
from engine.Utils.logger import game_logger
from engine.Agents.LocalAgents import ItemAgent
from static.config import ITEM_AGENT_MODEL

class ItemProcessor:
    """Xử lý toàn bộ logic liên quan đến tương tác vật phẩm (Tiêu chuẩn & Sáng tạo)"""

    def __init__(self, player_state: PlayerState,
                 gemini_api_key: str,
                 pm: PromptManager):
        # Cần local_agents (Gemini) để gọi AI check logic vật lý khi dùng đồ sáng tạo
        self.item_agent = ItemAgent(pm = pm,
                                    model_name = ITEM_AGENT_MODEL,
                                    gemini_api_key= gemini_api_key)
        self.player_state = player_state

    def _parse_craft_result(self, json_data: dict) -> Dict[str, Any]:
        """
        Xử lý chuỗi JSON từ LLM và khởi tạo trực tiếp Object Vật phẩm.
        Trả về: dict chứa trạng thái thành công, lý do, và Object Vật phẩm thực tế.
        """

        success = bool(json_data.get("success", False))
        reasoning = str(json_data.get("reasoning", "Không rõ nguyên lý."))

        if not success:
            return {"success": False, "reasoning": reasoning, "new_item": None}

        raw_new_item = json_data.get("new_item", {})
        if not isinstance(raw_new_item, dict) or not raw_new_item:
            game_logger.warning("[ItemAgent] JSON thiếu node 'new_item'.")
            return {"success": False, "reasoning": "Vật phẩm bốc hơi trong quá trình chế tạo.", "new_item": None}

        # 3. Trích xuất Base Attributes
        item_name = str(raw_new_item.get("name", "Vật phẩm lạ"))
        item_desc = str(raw_new_item.get("description", "Sinh ra từ sự kết hợp dị thường."))
        item_type = str(raw_new_item.get("type", "miscellaneous")).strip().lower()

        if item_type == "weapon":
            # Lấy và ép kiểu an toàn cho các thuộc tính của vũ khí
            try:
                base_damage = int(raw_new_item.get("base_damage", 0))
            except (ValueError, TypeError):
                base_damage = 0

            modifiers = raw_new_item.get("modifiers", {})
            if not isinstance(modifiers, dict):
                modifiers = {}

            status = raw_new_item.get("status_effect")
            status_effect = str(status) if status else None

            try:
                proc_chance = float(raw_new_item.get("proc_chance", 0.0))
            except (ValueError, TypeError):
                proc_chance = 0.0

            new_item_obj = WeaponItem(
                id=None,
                name=item_name,
                description=item_desc,
                base_damage=base_damage,
                modifiers=modifiers,
                status_effect=status_effect,
                proc_chance=proc_chance
            )

        elif item_type == "consumable":
            # Đề phòng trường hợp trong tương lai LLM sinh ra đồ tiêu hao
            try:
                effect = int(raw_new_item.get("effect", 0))
            except (ValueError, TypeError):
                effect = 0

            new_item_obj = ConsumableItem(
                id=None,
                name=item_name,
                description=item_desc,
                effect=effect
            )

        else:
            # Fallback an toàn: Mọi thứ khác đều biến thành đồ linh tinh
            new_item_obj = MiscellaneousItem(
                id=None,
                name=item_name,
                description=item_desc
            )

        # 5. Trả về kết quả kèm Object thực tế
        return {
            "success": True,
            "reasoning": reasoning,
            "new_item": new_item_obj
        }


    async def craft(self, item_list: List[BaseItem], action_details: str, image_manager=None) -> str:

        # 1. Kiểm tra xem người chơi có thực sự sở hữu các món đồ này không
        items_to_craft = []
        item_names = [item.name for item in item_list]

        for name in item_names:
            item = self.player_state.get_item_by_name(name)
            if not item:
                return f"[HỆ THỐNG]: Bạn không có vật phẩm '{name}' trong túi đồ."
            if item.item_type == "quest":
                return f"[HỆ THỐNG]: Không thể dùng vật phẩm nhiệm vụ '{name}' để chế tạo."
            items_to_craft.append(item)

        if len(items_to_craft) == 0:
            return "[HỆ THỐNG]: Không có vật phẩm để chế tạo."

        items = []
        for item in items_to_craft:
            # Quét tất cả thuộc tính (key) và giá trị (value) của object hiện tại
            attrs = [f"{key}: {value}" for key, value in vars(item).items() if key != 'id']

            # Ghép các thuộc tính của 1 vật phẩm lại, ngăn cách bằng dấu '-'
            items.append(" - ".join(attrs))

        evaluation_json = await self.item_agent.interact(action_details=action_details,
                                                items_list=items)

        evaluation = self._parse_craft_result(evaluation_json)

        if not evaluation.get("success"):
            return f"[CHẾ TẠO THẤT BẠI]: {evaluation.get('reasoning', 'Sự kết hợp này hoàn toàn vô lý.')}"

        # 3. NẾU THÀNH CÔNG: Xóa đồ cũ, Sinh đồ mới
        for old_item in items_to_craft:
            self.player_state.remove_item(old_item)  # Hàm đã có sẵn trong InventoryManager
            # (Tùy chọn) Xóa ảnh cũ trên ổ cứng bằng ImageManager

        new_item_obj = evaluation.get("new_item")

        if image_manager and new_item_obj:
            game_logger.info(f"[Crafting] Đang vẽ ảnh cho vật phẩm mới: {new_item_obj.name}...")
            # Lệnh await này sẽ chặn lại, chờ Kaggle vẽ xong mới đi tiếp
            img_path = await image_manager.get_or_create_item_image(new_item_obj.name)
            new_item_obj.image_path = img_path

        self.player_state.add_item(new_item_obj)
        crafted_names = ", ".join([item.name for item in items_to_craft])

        return f"[CHẾ TẠO THÀNH CÔNG]: Bạn đã kết hợp {crafted_names} thành [{new_item_obj.name}]. {evaluation.get('reasoning')}"


    async def use(self, item_list: List[BaseItem], action_details) -> Tuple[bool, str]:
        items_to_use = []
        item_names = [item.name for item in item_list]

        for name in item_names:
            item = self.player_state.get_item_by_name(name)
            if not item:
                return False, f"[HỆ THỐNG]: Bạn không có vật phẩm '{name}' trong túi đồ."
            if item.item_type == "quest":
                return f"[HỆ THỐNG]: Không thể dùng vật phẩm nhiệm vụ '{name}'."
            items_to_use.append(item)

        if len(items_to_use) == 0:
            return "[HỆ THỐNG]: Không có vật phẩm để sử dụng."

        items = []
        for item in items_to_use:
            # Quét tất cả thuộc tính (key) và giá trị (value) của object hiện tại
            attrs = [f"{key}: {value}" for key, value in vars(item).items() if key != 'id']

            # Ghép các thuộc tính của 1 vật phẩm lại, ngăn cách bằng dấu '-'
            items.append(" - ".join(attrs))

        evaluation_json = await self.item_agent.use(action_details=action_details,
                                                         items_list=items)