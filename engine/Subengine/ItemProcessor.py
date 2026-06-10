from engine.DataManager.PlayerState import PlayerState
from engine.DataManager.ImageManager import ImageManager
from engine.Utils.PromptManager import PromptManager
from world.Entity import BaseItem
from typing import Dict, Any, List, Tuple
from world.Entity import WeaponItem, ConsumableItem, MiscellaneousItem
from engine.Utils.logger import game_logger
from engine.Agents.LocalAgents import ItemAgent


class ItemProcessor:
    """
    Xử lý toàn bộ logic liên quan đến tương tác vật phẩm (Tiêu chuẩn & Sáng tạo).
    Đóng vai trò là cầu nối giữa hành động của người chơi (Craft/Use), dữ liệu túi đồ (Inventory)
    và bộ não đánh giá logic vật lý/phép thuật (ItemAgent - LLM).
    """

    def __init__(self, player_state: PlayerState, provider: str, local_api_key: str, pm: PromptManager):
        """
        Khởi tạo bộ xử lý vật phẩm.

        Args:
            player_state (PlayerState): Trạng thái hiện tại của người chơi (để truy xuất túi đồ).
            local_api_key (str): Khóa API để khởi tạo Local Agent (Gemini) làm trọng tài logic.
            pm (PromptManager): Trình quản lý prompt để lấy các kịch bản nạp cho LLM.
        """
        # Cần local_agents (Gemini) để gọi AI check logic vật lý khi dùng đồ sáng tạo
        self.item_agent = ItemAgent(pm=pm,
                                    provider=provider,
                                    api_key=local_api_key)
        self.player_state = player_state


    def _validate_items(self, item_list: List[BaseItem], action_name: str) -> Tuple[bool, Any]:
        """
        Kiểm tra danh sách vật phẩm người chơi muốn tương tác có hợp lệ và tồn tại hay không.
        Đồng thời chặn việc người chơi tự ý tiêu hủy/chế tạo vật phẩm nhiệm vụ (Quest Item).

        Args:
            item_list (List[BaseItem]): Danh sách các đối tượng vật phẩm truyền vào.
            action_name (str): Tên hành động (VD: 'chế tạo', 'sử dụng') để in ra thông báo lỗi cho mượt.

        Returns:
            Tuple[bool, Any]:
                - (True, List[BaseItem]): Nếu tất cả vật phẩm đều hợp lệ và có trong túi đồ.
                - (False, str): Nếu thiếu đồ hoặc dùng sai đồ nhiệm vụ, kèm chuỗi thông báo lỗi.
        """
        valid_items = []
        item_names = [item.name for item in item_list]

        for name in item_names:
            item = self.player_state.get_item_by_name(name)
            if not item:
                return False, f"[HỆ THỐNG]: Bạn không có vật phẩm '{name}' trong túi đồ."
            if item.item_type == "quest":
                return False, f"[HỆ THỐNG]: Không thể {action_name} vật phẩm nhiệm vụ '{name}'."
            valid_items.append(item)

        if not valid_items:
            return False, f"[HỆ THỐNG]: Không có vật phẩm để {action_name}."

        return True, valid_items


    def _convert_to_string(self, item_list: List[BaseItem]) -> str:
        """
        Chuyển đổi danh sách các object vật phẩm thành một chuỗi văn bản (String)
        chứa đầy đủ thuộc tính để nạp làm context cho Prompt của LLM.

        Args:
            item_list (List[BaseItem]): Danh sách các vật phẩm cần chuyển đổi.

        Returns:
            str: Chuỗi văn bản chứa thông tin vật phẩm (VD: "name: X - description: Y...").
        """
        items = []
        for item in item_list:
            # Quét tất cả thuộc tính (key) và giá trị (value) của object hiện tại
            attrs = [f"{key}: {value}" for key, value in vars(item).items() if key != 'id']

            # Ghép các thuộc tính của 1 vật phẩm lại, ngăn cách bằng dấu '-'
            items.append(" - ".join(attrs))

        items_str = "\n".join(items)
        return items_str


    def _parse_craft_result(self, json_data: dict) -> Dict[str, Any]:
        """
        Xử lý chuỗi JSON kết quả trả về từ LLM sau hành động chế tạo (Craft)
        và ép kiểu để khởi tạo trực tiếp thành các Object Vật phẩm tương ứng (Weapon, Consumable...).

        Args:
            json_data (dict): Dữ liệu từ thông điệp JSON do AI Agent sinh ra.

        Returns:
            Dict[str, Any]: Từ điển chứa:
                - 'success' (bool): Logic chế tạo có thành công hay không.
                - 'reasoning' (str): Lời giải thích vật lý/phép thuật từ AI.
                - 'new_item' (BaseItem | None): Object vật phẩm mới được sinh ra (nếu thành công).
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
                effect = raw_new_item.get("effect", {})
            except (ValueError, TypeError):
                effect = {}

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
            "new_item": new_item_obj,
            "lost_items": json_data.get("lost_items", [])  # <--- THÊM DÒNG NÀY ĐỂ HỨNG DỮ LIỆU
        }


    async def craft(self, item_list: List[BaseItem], action_details: str, image_manager: ImageManager = None) -> str:
        """
        Thực thi quy trình chế tạo (Crafting) dựa trên sự đánh giá logic của AI.
        Chỉ tiêu hao/hủy bỏ những vật phẩm được AI chỉ định trong mảng 'lost_items'.
        """
        is_valid, items_to_craft = self._validate_items(item_list=item_list, action_name='chế tạo')
        if not is_valid:
            return items_to_craft

        items_str = self._convert_to_string(items_to_craft)
        evaluation_json = await self.item_agent.craft(action_details=action_details, items_str=items_str)
        evaluation = self._parse_craft_result(evaluation_json)

        lost_item_names = evaluation.get("lost_items", [])
        game_logger.info(f'[ITEMPROCESSOR]: LOẠI BỎ CÁC VẬT PHẨM {lost_item_names} SAU KHI CHẾ TẠO ')

        # ==========================================
        # BƯỚC 1: XÓA ĐỒ BỊ MẤT / TIÊU HAO (CỐT LÕI)
        # Chỉ xóa những món có tên trong danh sách lost_items
        # (Áp dụng chung cho cả trường hợp Thành công lẫn Thất bại)
        # ==========================================
        for old_item in items_to_craft:
            if old_item.name in lost_item_names:
                self.player_state.inventory_manager.remove_item(old_item)

        # ==========================================
        # BƯỚC 2: XỬ LÝ KHI CHẾ TẠO THẤT BẠI
        # ==========================================
        if not evaluation.get("success"):
            if lost_item_names:
                lost_str = ", ".join(lost_item_names)
                game_logger.info(f"[ITEM_MANAGER][CHẾ TẠO THẤT BẠI]: {evaluation.get('reasoning')} (Hậu quả: Bạn đã làm hỏng/mất {lost_str})")
                return f"[CHẾ TẠO THẤT BẠI]: {evaluation.get('reasoning')} (Hậu quả: Bạn đã làm hỏng/mất {lost_str})"

            game_logger.info(f"ITEM_MANAGER][CHẾ TẠO THẤT BẠI]: {evaluation.get('reasoning')} (May mắn là bạn chưa làm hỏng nguyên liệu nào)")
            return f"[CHẾ TẠO THẤT BẠI]: {evaluation.get('reasoning')} (May mắn là bạn chưa làm hỏng nguyên liệu nào)"

        # ==========================================
        # BƯỚC 3: XỬ LÝ KHI CHẾ TẠO THÀNH CÔNG
        # ==========================================
        new_item_obj = evaluation.get("new_item")

        if image_manager and new_item_obj:
            game_logger.info(f"[Crafting] Đang vẽ ảnh cho vật phẩm mới: {new_item_obj.name}...")
            img_path = await image_manager.get_or_create_item_image(new_item_obj.name)
            new_item_obj.image_path = img_path

        # Thêm vật phẩm mới tạo vào túi đồ
        self.player_state.inventory_manager.add_item(new_item_obj)

        # Tạo chuỗi thông báo
        crafted_names = ", ".join([item.name for item in items_to_craft])
        lost_str = ", ".join(lost_item_names) if lost_item_names else "Không tiêu hao gì"
        game_logger.info(f"ITEM_MANAGER][CHẾ TẠO THÀNH CÔNG]: Bạn đã dùng {crafted_names} để tạo ra [{new_item_obj.name}]. {evaluation.get('reasoning')} (Đã tiêu hao: {lost_str})")
        return f"[CHẾ TẠO THÀNH CÔNG]: Bạn đã dùng {crafted_names} để tạo ra [{new_item_obj.name}]. {evaluation.get('reasoning')} (Đã tiêu hao: {lost_str})"


    async def use(self, item_list: List[BaseItem], action_details: str) -> Tuple[bool, str]:
        """
        Đánh giá và thực thi hành động sử dụng (Use) vật phẩm của người chơi lên môi trường hoặc lên bản thân.

        Args:
            item_list (List[BaseItem]): Danh sách vật phẩm được mang ra sử dụng.
            action_details (str): Miêu tả chi tiết hành động (VD: "Ném bình máu vào vách đá", "Uống lọ thuốc giải").

        Returns:
            Tuple[bool, str]:
                - bool: True nếu hành động hợp lý về mặt vật lý/phép thuật, False nếu vô lý.
                - str: Lời giải thích/nhận xét từ AI (Reasoning) làm cơ sở cho StoryAgent kể chuyện.
        """
        is_valid, items_to_use = self._validate_items(item_list=item_list,
                                        action_name='sử dụng')
        if not is_valid:
            return False, items_to_use # items_to_use lúc này chứa chuỗi báo lỗi

        items_str = self._convert_to_string(item_list=items_to_use)
        loc_name = self.player_state.currentLocation.name if self.player_state.currentLocation else "Không rõ"
        env_context = f"Địa điểm hiện tại: {loc_name}"

        evaluation_json = await self.item_agent.use(action_details=action_details,
                                                    items_str=items_str,
                                                    context=env_context)

        success = evaluation_json.get('success', False)
        reasoning = evaluation_json.get("reasoning", "Không có chuyện gì xảy ra.")
        lost_item_names = evaluation_json.get("lost_items", [])

        game_logger.info(f'[ITEMPROCESSOR]: LOẠI BỎ CÁC VẬT PHẨM {lost_item_names} SAU KHI SỬ DỤNG')
        # XÓA CÁC VẬT PHẨM BỊ HỎNG / TIÊU HAO (Bất kể thành công hay thất bại)
        for item in items_to_use:
            if item.name in lost_item_names:
                self.player_state.inventory_manager.remove_item(item)

        return success, reasoning