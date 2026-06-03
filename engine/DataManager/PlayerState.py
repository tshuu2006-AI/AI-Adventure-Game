"""
lưu trữ và quản lý trạng thái tổng thể của người chơi
"""


from engine.DataManager.InventoryManager import InventoryManager
from world.Entity import BaseItem, Quest


class PlayerState:
    """
    Đối tượng lưu trữ và quản lý trạng thái tổng thể của người chơi theo thời gian thực.
    Bao gồm vị trí, chỉ số sinh tồn (HP, Stats), hệ thống túi đồ và tiến trình nhiệm vụ.
    """

    def __init__(self, name: str = "Player"):
        """
        Khởi tạo trạng thái mặc định của người chơi khi bắt đầu game mới.
        """
        self.name = name
        self.currentLocation = None
        self.currentTurn = 0
        self.currentNPCs = []

        # Khởi tạo trình quản lý túi đồ độc lập (Composition)
        self.inventory_manager = InventoryManager()

        # Chỉ số cơ bản
        self.hp = 100
        self.max_hp = 100
        self.base_stats = {
            "STR": 10,  # Sức mạnh: Tác động đến sát thương vật lý
            "AGI": 10,  # Nhanh nhẹn: Tác động đến tốc độ, né tránh
            "INT": 10  # Trí tuệ: Tác động đến phép thuật, giải mã
        }

        self.is_safe_zone = False
        self.active_quest = None
        self.main_quest = None
        self.quests = []
        self.quest_items = []


    def back_to_main_quest(self) -> bool:
        """
        Khôi phục lại không gian và trạng thái từ main_snapshot khi kết thúc nhiệm vụ.
        """

        snapshot = self.main_quest.snapshot

        # 1. Khôi phục không gian mạch chính
        self.currentLocation = snapshot.get("location")
        self.currentNPCs = snapshot.get("npcs", []).copy()

        # 2. Xóa quest đang làm
        self.active_quest = self.main_quest

        # 3. Thông báo cho hệ thống rằng đã về mạch chính
        return True

    # ==========================================
    # CÁC HÀM GIAO TIẾP VỚI TÚI ĐỒ (Wrapper Methods)
    # ==========================================
    def get_all_item_names(self):
        """
        Trích xuất chuỗi danh sách tên vật phẩm đang sở hữu.
        """
        return self.inventory_manager.get_all_item_names()

    def add_item(self, item: BaseItem):
        """
        Thêm vật phẩm vào túi đồ (Tự động phân loại).
        """
        self.inventory_manager.add_item(item)

    def remove_item(self, item: BaseItem):
        """
        Xóa vật phẩm khỏi túi đồ.
        """
        self.inventory_manager.remove_item(item)

    def get_item_by_name(self, item_name: str):
        """
        Tìm kiếm vật phẩm trong túi đồ theo tên.
        """
        return self.inventory_manager.get_item_by_name(item_name)


    def get_quest_items(self):
        return self.inventory_manager.get_quest_items(quest=self.active_quest)


    def save_snapshot(self, snapshot: dict):
      self.active_quest.snapshot = snapshot

    # ==========================================
    # CÁC HÀM LƯU TRỮ VÀ PHỤC HỒI TRẠNG THÁI
    # ==========================================
    def to_dict(self) -> dict:
        """
        Đóng gói dữ liệu của người chơi thành Dictionary để chuẩn bị lưu game.

        Returns:
            dict: Dữ liệu JSON chứa thông tin trạng thái người chơi và túi đồ.
        """
        return {
            "current_turn": self.currentTurn,
            "current_location_name": self.currentLocation.name if self.currentLocation else None,
            "current_npc_names": [npc.name for npc in self.currentNPCs],
            "inventory_data": self.inventory_manager.to_dict()
        }

    async def load_state(self, data: dict, db_manager, image_manager):
        """
        Khôi phục trạng thái người chơi từ dữ liệu file save (Deserialization).

        Args:
            data (dict): Dữ liệu trạng thái người chơi từ file JSON.
            db_manager: Trình quản lý CSDL để truy vấn lại đối tượng Location và NPC.
            image_manager: Trình quản lý ảnh để phục hồi đường dẫn ảnh cho vật phẩm trong túi.
        """
        self.currentTurn = data.get("current_turn", 0)

        # 1. Phục hồi Location từ CSDL
        loc_name = data.get("current_location_name")
        if loc_name:
            all_locs = await db_manager.location_manager.get_all()
            self.currentLocation = next((l for l in all_locs if l.name == loc_name), None)

        # 2. Phục hồi NPCs từ CSDL
        npc_names = data.get("current_npc_names", [])
        if npc_names:
            all_npcs = await db_manager.npc_manager.get_all()
            self.currentNPCs = [n for n in all_npcs if n.name in npc_names]
        else:
            self.currentNPCs = []

        # 3. Yêu cầu túi đồ tự khôi phục dữ liệu vật phẩm
        self.inventory_manager.load_state(data.get("inventory_data", {}), image_manager)


    def update_quest_items(self):
        self.quest_items = []
        for item in self.inventory_manager.quest_item_inventory:
            if item.quest.id == self.active_quest.id:
                self.quest_items.append(item)


    def add_quest(self, quest: Quest):
        self.quests.append(quest)
