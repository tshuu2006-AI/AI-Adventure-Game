"""Manage the data flow of inventory"""
from world.Entity import BaseItem, ConsumableItem, QuestItem, MiscellaneousItem, WeaponItem
from engine.DataManager.ImageManager import ImageManager
import os
from typing import List

class InventoryManager:
    """
    Quản lý toàn bộ túi đồ, trang bị và vật phẩm của người chơi.
    Hỗ trợ phân loại tự động, thao tác sử dụng/trang bị và đồng bộ trạng thái lưu trữ.
    """

    def __init__(self):
        """
        Khởi tạo hệ thống quản lý túi đồ với các ngăn chứa riêng biệt cho từng loại vật phẩm.
        """
        self.quest_item_inventory = []
        self.weapon_item_inventory = []
        self.consumable_item_inventory = []
        self.interactive_item_inventory = []

        self.equipped_weapon = None


    def clear(self):
        self.quest_item_inventory = []
        self.weapon_item_inventory = []
        self.consumable_item_inventory = []
        self.interactive_item_inventory = []

        self.equipped_weapon = None

    # ==========================================
    # NHÓM 1: CÁC HÀM THÊM/XÓA (CRUD)
    # ==========================================
    def add_item(self, item):
        """
        Tự động phân loại và thêm vật phẩm vào đúng ngăn chứa dựa trên `item_type`.

        Args:
            item (BaseItem): Đối tượng vật phẩm cần thêm vào túi đồ.
        """
        if item.item_type == "quest":
            self.quest_item_inventory.append(item)
        elif item.item_type == "weapon":
            self.weapon_item_inventory.append(item)
        elif item.item_type == "consumable":
            self.consumable_item_inventory.append(item)
        elif item.item_type == "miscellaneous":
            self.interactive_item_inventory.append(item)


    def search(self, item) -> bool:
        for i in (self.quest_item_inventory + self.interactive_item_inventory + self.consumable_item_inventory + self.weapon_item_inventory):
            if item == i:
                return True
        return False


    def remove_item(self, item):
        """
        Xóa vật phẩm khỏi túi đồ. Tự động tháo trang bị nếu vật phẩm đó đang được sử dụng.

        Args:
            item (BaseItem): Đối tượng vật phẩm cần xóa.
        """
        if item in self.quest_item_inventory:
            self.quest_item_inventory.remove(item)
        elif item in self.weapon_item_inventory:
            self.weapon_item_inventory.remove(item)
            if self.equipped_weapon == item:
                self.equipped_weapon = None
        elif item in self.consumable_item_inventory:
            self.consumable_item_inventory.remove(item)
        elif item in self.interactive_item_inventory:
            self.interactive_item_inventory.remove(item)

    # ==========================================
    # NHÓM 2: CÁC HÀM TRUY XUẤT VÀ TÌM KIẾM
    # ==========================================
    def _search_list(self, item_list, target):
        for item in item_list:
            if target in item.name.lower():
                return item
        return None

    # ==========================================
    # NHÓM 3: CÁC HÀM THỰC THI LOGIC GAME
    # ==========================================
    def equip_weapon(self, weapon: WeaponItem):
        """Hàm sử dụng vũ khí"""
        self.equipped_weapon = weapon

    def unequip_weapon(self):
        """Hàm bỏ vũ khí"""
        self.equipped_weapon = None

    def change_weapon(self, weapon: WeaponItem):
        """Hàm đổi vũ khí"""
        self.unequip_weapon()
        self.equip_weapon(weapon=weapon)

    def use_consumable(self, item_name: str, player_state) -> str:
        """
        Sử dụng vật phẩm tiêu hao và áp dụng hiệu ứng lên người chơi.

        Args:
            item_name (str): Tên vật phẩm cần dùng.
            player_state (PlayerState): Trạng thái của người chơi để áp dụng hiệu ứng.

        Returns:
            str: Thông báo kết quả sử dụng vật phẩm.
        """
        item = self.get_item_by_name(item_name)

        if not item or item not in self.consumable_item_inventory:
            return "Vật phẩm này không tồn tại hoặc không thể tiêu thụ."

        result_msg = player_state.use_consumables(item)
        self.remove_item(item)
        return result_msg



    # ==========================================
    # NHÓM 4: CÁC HÀM HỖ TRỢ LƯU TRỮ
    # ==========================================
    def to_dict(self) -> dict:
        """
        Chuyển đổi toàn bộ dữ liệu túi đồ thành dictionary để phục vụ việc lưu trạng thái game (Serialization).

        Returns:
            dict: Dữ liệu JSON chứa thông tin các vật phẩm và vũ khí đang trang bị.
        """
        all_items = (self.quest_item_inventory +
                     self.weapon_item_inventory +
                     self.consumable_item_inventory +
                     self.interactive_item_inventory)

        return {
            "items": [vars(item).copy() for item in all_items],
            "equipped_weapon": self.equipped_weapon.name if self.equipped_weapon else None
        }

    def load_state(self, data: dict, image_manager: ImageManager):
        """
        Khôi phục trạng thái túi đồ từ dữ liệu file save (Deserialization).

        Args:
            data (dict): Dữ liệu túi đồ từ file JSON.
            image_manager (ImageManager): Trình quản lý hình ảnh để khôi phục lại đường dẫn ảnh vật phẩm.
        """
        self.quest_item_inventory.clear()
        self.weapon_item_inventory.clear()
        self.consumable_item_inventory.clear()
        self.interactive_item_inventory.clear()
        self.equipped_weapon = None

        equipped_name = data.get("equipped_weapon")

        for item_data in data.get("items", []):
            item_type = item_data.get("item_type", "miscellaneous")
            item_id = item_data.get("id")
            item_name = item_data.get("name", "Vô danh")
            item_desc = item_data.get("description", "Ký ức mơ hồ...")

            if item_type == "weapon":
                restored_item = WeaponItem(
                    id=item_id, name=item_name, description=item_desc,
                    base_damage=item_data.get("base_damage", 0),
                    modifiers=item_data.get("modifiers", {}),
                    status_effect=item_data.get("status_effect"),
                    proc_chance=item_data.get("proc_chance", 0.0)
                )

                if item_name == equipped_name:
                    self.equip_weapon(restored_item)

            elif item_type == "consumable":
                restored_item = ConsumableItem(
                    id=item_id, name=item_name, description=item_desc,
                    effect=item_data.get("effect", {})
                )
            elif item_type == "quest":
                restored_item = QuestItem(
                    id=item_id, name=item_name, description=item_desc,
                    quest=item_data.get("quest")
                )
            else:
                restored_item = MiscellaneousItem(id=item_id, name=item_name, description=item_desc)

            img_filename = image_manager.get_safe_filename(f"item_{item_name}")
            full_img_path = os.path.join(image_manager.item_folder, img_filename)
            restored_item.image_path = full_img_path if os.path.exists(full_img_path) else item_data.get("image_path")

            self.add_item(restored_item)


    #=========================================================
    #=                       GETTER                          =
    #=========================================================
    def get_quest_items(self, quest):
        quest_items = []
        for item in self.quest_item_inventory:
            if item.quest == quest:
                quest_items.append(item)

        return quest_items


    def get_item_by_name(self, item_name: str):
        """
        Tìm kiếm vật phẩm theo tên (không phân biệt hoa/thường) trên tất cả các ngăn chứa.

        Args:
            item_name (str): Tên vật phẩm cần tìm.

        Returns:
            BaseItem hoặc None: Đối tượng vật phẩm nếu tìm thấy, ngược lại trả về None.
        """
        target = item_name.lower()

        return (self._search_list(self.consumable_item_inventory, target=target) or
                self._search_list(self.weapon_item_inventory, target=target) or
                self._search_list(self.interactive_item_inventory, target=target) or
                self._search_list(self.quest_item_inventory, target=target))

    def get_all_item_names(self) -> str:
        """
        Lấy danh sách tên của tất cả vật phẩm hiện có trong túi đồ.

        Returns:
            str: Chuỗi chứa tên các vật phẩm cách nhau bằng dấu phẩy, hoặc thông báo nếu túi đồ trống.
        """
        all_items = (self.quest_item_inventory +
                     self.weapon_item_inventory +
                     self.consumable_item_inventory +
                     self.interactive_item_inventory)

        if not all_items: return []
        return all_items


    def get_all_items(self) -> List[BaseItem]:
        """
        Lấy toàn bộ đối tượng vật phẩm hiện có trong túi đồ.

        Returns:
            List[BaseItem]: Danh sách gộp của tất cả vật phẩm.
        """
        all_items = (self.quest_item_inventory +
                     self.weapon_item_inventory +
                     self.consumable_item_inventory +
                     self.interactive_item_inventory)

        return all_items


    def get_equipped_weapon(self):
        return self.equipped_weapon

