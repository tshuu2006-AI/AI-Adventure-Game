"""
lưu trữ và quản lý trạng thái tổng thể của người chơi
"""


from engine.DataManager.InventoryManager import InventoryManager
from engine.DataManager.StatsManager import StatsManager
from world.Entity import BaseItem, Quest, WeaponItem, ConsumableItem, Location, NPC


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
        self.stats = StatsManager()

        self.last_intent = None
        self.is_safe_zone = False
        self.active_quest = None
        self.main_quest = None
        self.quests = []
        self.quest_items = []


    def clear(self):
        """
        Làm sạch toàn bộ trạng thái hiện tại của người chơi, đưa về mốc mặc định (Reset).
        Thường được gọi khi bắt đầu một phiên New Game mới.
        """
        self.currentLocation = None
        self.currentTurn = 0
        self.currentNPCs = []

        # Khởi tạo lại Túi đồ và Chỉ số (Stats) mới hoàn toàn để xóa dữ liệu cũ
        self.inventory_manager.clear()
        self.stats.clear()

        self.is_safe_zone = False
        self.active_quest = None
        self.main_quest = None
        self.quests = []
        self.quest_items = []


    def is_dead(self):
        if self.stats.current_hp <= 0:
            return True
        return False


    def change_weapon(self, weapon: WeaponItem):
        """Hàm đổi vũ khí"""
        self.inventory_manager.change_weapon(weapon)
        self.stats.apply_equipment(weapon.modifiers)


    def use_consumables(self, consumable_item: ConsumableItem):
        if self.inventory_manager.search(consumable_item):
            self.stats.apply_effect(consumable_item.effect)
            self.inventory_manager.remove_item(item=consumable_item)
        return


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


    def remove_item(self, item: BaseItem):
        """
        Xóa vật phẩm khỏi túi đồ.
        """
        self.inventory_manager.remove_item(item)


    def save_snapshot(self, snapshot: dict):
      self.active_quest.snapshot = snapshot

    # ==========================================
    # CÁC HÀM LƯU TRỮ VÀ PHỤC HỒI TRẠNG THÁI
    # ==========================================
    def to_dict(self) -> dict:
        """
        Đóng gói dữ liệu của người chơi thành Dictionary để chuẩn bị lưu game.
        """
        # Hàm phụ trợ để đóng gói riêng lẻ từng Nhiệm vụ
        def serialize_quest(q: Quest):
            snap_dict = {}
            if getattr(q, 'snapshot', None):
                snap_loc = q.snapshot.get("location")
                snap_npcs = q.snapshot.get("npcs", [])
                snap_dict = {
                    "location_name": snap_loc.name if snap_loc else None,
                    "npc_names": [n.name for n in snap_npcs] if snap_npcs else [],
                    "last_story": q.snapshot.get("last_story", ""),
                    "last_choices": q.snapshot.get("last_choices", [])
                }
            return {
                "id": q.id,
                "name": q.name,
                "description": q.description,
                "objectives": q.objectives,
                "is_finished": getattr(q, 'is_finished', [0]*len(q.objectives)),
                "give_by": getattr(q, 'give_by', ''),
                "rewards": getattr(q, 'rewards', []),
                "status": getattr(q, 'status', 'available'),
                "snapshot": snap_dict
            }

        return {
            "current_turn": self.currentTurn,
            "current_location_name": self.currentLocation.name if self.currentLocation else None,
            "current_npc_names": [npc.name for npc in self.currentNPCs],
            "inventory_data": self.inventory_manager.to_dict(),
            
            # 🌟 BỔ SUNG LƯU TRỮ NHIỆM VỤ VÀ CON TRỞ NHIỆM VỤ CHÍNH/ĐANG LÀM
            "quests": [serialize_quest(q) for q in self.quests],
            "active_quest_id": self.active_quest.id if getattr(self, 'active_quest', None) else None,
            "main_quest_id": self.main_quest.id if getattr(self, 'main_quest', None) else None,
            "stats_data": self.stats.to_dict()
        }

    async def load_state(self, data: dict, db_manager, image_manager):
        """
        Khôi phục trạng thái người chơi từ dữ liệu file save (Deserialization).
        """
        self.currentTurn = data.get("current_turn", 0)

        # Lấy trước toàn bộ Loc và NPC từ DB để tái tạo Ký ức (Snapshot)
        all_locs = await db_manager.location_manager.get_all()
        all_npcs = await db_manager.npc_manager.get_all()

        # 1. Phục hồi Location hiện tại
        loc_name = data.get("current_location_name")
        if loc_name:
            self.currentLocation = next((l for l in all_locs if l.name == loc_name), None)

        # 2. Phục hồi NPCs hiện tại
        npc_names = data.get("current_npc_names", [])
        if npc_names:
            self.currentNPCs = [n for n in all_npcs if n.name in npc_names]
        else:
            self.currentNPCs = []

        # 3. Phục hồi Túi đồ
        self.inventory_manager.load_state(data.get("inventory_data", {}), image_manager)
        self.stats.load_state(data.get("stats_data", {}))

        # ==========================================
        # 🌟 4. PHỤC HỒI SỔ TAY NHIỆM VỤ (QUESTS)
        # ==========================================
        self.quests = []
        for q_data in data.get("quests", []):
            quest = Quest(
                id=q_data.get("id"),
                name=q_data.get("name"),
                description=q_data.get("description"),
                objectives=q_data.get("objectives", []),
                give_by=q_data.get("give_by", ""),
                rewards=q_data.get("rewards", [])
            )
            quest.is_finished = q_data.get("is_finished", [0] * len(quest.objectives))
            quest.status = q_data.get("status", "available")
            
            # Phục hồi Bối cảnh lưu trữ (Snapshot) của từng quest
            snap_data = q_data.get("snapshot", {})
            if snap_data:
                snap_loc_name = snap_data.get("location_name")
                snap_loc = next((l for l in all_locs if l.name == snap_loc_name), None) if snap_loc_name else None
                
                snap_npc_names = snap_data.get("npc_names", [])
                snap_npcs = [n for n in all_npcs if n.name in snap_npc_names] if snap_npc_names else []
                
                quest.snapshot = {
                    "location": snap_loc,
                    "npcs": snap_npcs,
                    "last_story": snap_data.get("last_story", ""),
                    "last_choices": snap_data.get("last_choices", [])
                }
            self.quests.append(quest)
            
        # 5. Phục hồi con trỏ Nhiệm vụ đang làm & Nhiệm vụ chính
        active_id = data.get("active_quest_id")
        self.active_quest = next((q for q in self.quests if q.id == active_id), None)
        
        main_id = data.get("main_quest_id")
        self.main_quest = next((q for q in self.quests if q.id == main_id), None)
        
        # Cập nhật lại list item móc với nhiệm vụ
        self.update_quest_items()


#==========================================================
#=                     GETTER                             =
#==========================================================
    def get_all_items(self):
        return self.inventory_manager.get_all_items()

    def get_current_location(self):
        return self.currentLocation

    def get_all_item_names(self):
        """
        Trích xuất chuỗi danh sách tên vật phẩm đang sở hữu.
        """
        return self.inventory_manager.get_all_item_names()

    def get_item(self, item_name: str):
        """Hàm ủy quyền lấy vật phẩm"""
        return self.inventory_manager.get_item_by_name(item_name)

    def get_current_location_name(self) -> str:
        """Che giấu việc truy cập thuộc tính .name"""
        return self.currentLocation.name if self.currentLocation else "Vùng đất vô danh"

    def get_current_npcs(self):
        return self.currentNPCs


    def get_item_by_name(self, item_name: str):
        """
        Tìm kiếm vật phẩm trong túi đồ theo tên.
        """
        return self.inventory_manager.get_item_by_name(item_name)

    def get_quest_items(self):
        return self.inventory_manager.get_quest_items(quest=self.active_quest)

    def get_current_hp(self):
        return self.stats.get_current_hp()

    def get_max_hp(self):
        return self.stats.get_max_hp()

    def get_equipped_weapon(self):
        return self.inventory_manager.get_equipped_weapon()

    def get_active_quest(self):
        return self.active_quest

    def get_all_quests(self):
        return self.quests




#==========================================================
#=                     SETTER                             =
#==========================================================
    def update_quest_items(self):
        self.quest_items = []
        if not self.active_quest:
            return  # 🌟 Thêm dòng này bảo vệ an toàn nếu load file mà không có Quest nào

        for item in self.inventory_manager.quest_item_inventory:
            # 🌟 Xử lý an toàn: Khi load json, 'item.quest' có thể bị biến thành số(int/string) thay vì object
            item_quest_id = item.quest.id if hasattr(item.quest, 'id') else (
                item.quest.get("id") if isinstance(item.quest, dict) else item.quest)
            if item_quest_id == self.active_quest.id:
                self.quest_items.append(item)

    def add_quest(self, quest: Quest):
        self.quests.append(quest)


    def add_item(self, item: BaseItem):
        """
        Thêm vật phẩm vào túi đồ (Tự động phân loại).
        """
        self.inventory_manager.add_item(item)

    def set_location(self, location: Location):
        self.currentLocation = location

    def set_main_quest(self, main_quest: Quest):
        self.active_quest = main_quest
        self.main_quest = main_quest

    def add_npc(self, npc: NPC):
        self.currentNPCs.append(npc)

    def equip_weapon(self, weapon: WeaponItem):
        """Hàm sử dụng vũ khí"""
        self.inventory_manager.equip_weapon(weapon=weapon)
        self.stats.apply_equipment(weapon.modifiers)


    def unequip_weapon(self):
        """Hàm bỏ vũ khí"""
        self.inventory_manager.unequip_weapon()
        self.stats.apply_equipment(None)

    def set_intent(self, intent: str):
        self.last_intent = intent