"""
Contains all entities of the game
"""
from dataclasses import dataclass
from typing import Optional


class BaseEntity:
    """
    Lớp cơ sở (Base Class) cho tất cả các thực thể tồn tại trong thế giới game.
    Cung cấp các thuộc tính cốt lõi mà mọi đối tượng (vật phẩm, địa điểm, NPC...) đều phải có.
    """

    def __init__(self, id, name, type, description):
        """
        Khởi tạo một thực thể cơ bản.

        Args:
            id (int/str): Định danh duy nhất của thực thể trong CSDL.
            name (str): Tên hiển thị của thực thể.
            type (str): Phân loại thực thể (VD: 'item', 'location', 'npc').
            description (str): Đoạn văn bản mô tả chi tiết về thực thể.
        """
        self.id = id
        self.name = name
        self.type = type
        self.description = description


class BaseItem(BaseEntity):
    """
    Lớp cơ sở cho tất cả các loại vật phẩm có thể lưu trữ trong túi đồ.
    Kế thừa từ BaseEntity và gán cứng `type` là 'item'.
    """

    def __init__(self, id, name, description, item_type):
        """
        Khởi tạo vật phẩm cơ bản.

        Args:
            item_type (str): Phân loại vật phẩm chi tiết (VD: 'weapon', 'consumable', 'quest').
        """
        # Gọi hàm khởi tạo của class cha (BaseEntity)
        super().__init__(id, name, 'item', description)
        self.item_type = item_type


class ConsumableItem(BaseItem):
    """
    Lớp đại diện cho vật phẩm tiêu hao (thức ăn, bình máu, thuốc giải...).
    Sẽ bị mất đi hoặc giảm số lượng sau khi sử dụng.
    """

    def __init__(self, id, name, description, effect):
        """
        Khởi tạo vật phẩm tiêu hao.

        Args:
            effect (int): Giá trị tác dụng (Ví dụ: số lượng HP được hồi phục).
        """
        super().__init__(id, name, description, 'consumable')
        self.effect = effect


    def apply_effect(self, player_state) -> str:
        """
        Hàm thực thi logic hồi máu/năng lượng khi người chơi sử dụng vật phẩm.

        Args:
            player_state (PlayerState): Đối tượng chứa trạng thái hiện tại của người chơi.

        Returns:
            str: Chuỗi thông báo kết quả sau khi sử dụng vật phẩm.
        """
        # Cộng thêm chỉ số HP dựa trên giá trị effect của vật phẩm
        player_state.hp += self.effect

        # Đảm bảo HP không vượt quá mức tối đa cho phép
        if player_state.hp > player_state.max_hp:
            player_state.hp = player_state.max_hp

        return f"Đã sử dụng {self.name}. HP hồi phục {self.effect} điểm. (HP hiện tại: {player_state.hp}/{player_state.max_hp})"


class WeaponItem(BaseItem):
    """
    Lớp đại diện cho vật phẩm dạng vũ khí, trang bị để tăng cường chỉ số chiến đấu.
    """

    def __init__(self, id, name, description,
                 base_damage=0,  # Base Stat: Sát thương vật lý/phép thuật cơ bản
                 modifiers=None,  # Modifiers: Chỉ số cộng thêm (Ví dụ: {"str": 5, "agi": -2})
                 status_effect=None,  # Status Effect: Hiệu ứng đính kèm (Ví dụ: "burn", "poison")
                 proc_chance=0.0):  # Tỷ lệ kích hoạt hiệu ứng (Ví dụ: 0.2 tương đương 20%)
        """
        Khởi tạo vũ khí chiến đấu.
        """
        super().__init__(id, name, description, 'weapon')
        self.base_damage = base_damage
        # Đảm bảo modifiers luôn là một dictionary (nếu không truyền vào sẽ là dict rỗng)
        self.modifiers = modifiers or {}
        self.status_effect = status_effect
        self.proc_chance = proc_chance


class QuestItem(BaseItem):
    """
    Lớp đại diện cho vật phẩm nhiệm vụ.
    Thường không thể sử dụng hay vứt bỏ theo cách thông thường, dùng để kích hoạt hoặc hoàn thành Quest.
    """

    def __init__(self, id, name, description, quest):
        """
        Khởi tạo vật phẩm nhiệm vụ.

        Args:
            quest (str/Quest): Tên hoặc ID của nhiệm vụ liên quan đến vật phẩm này.
        """
        super().__init__(id, name, description, 'quest')
        self.quest = quest


class MiscellaneousItem(BaseItem):
    """
    Lớp đại diện cho các vật phẩm linh tinh (tạp phẩm, vật liệu chế tạo, đồ sưu tầm...).
    """

    def __init__(self, id, name, description):
        """Khởi tạo vật phẩm linh tinh."""
        super().__init__(id, name, description, 'miscellaneous')



class Quest(BaseEntity):
    def __init__(self, id, name, description, objectives, give_by, rewards): # Thêm objective vào tham số
        super().__init__(id, name, 'quest', description)
        self.objectives = objectives # Lưu mục tiêu để AI chấm điểm
        self.is_finished = [0] * len(self.objectives)
        self.snapshot = {}
        self.give_by = give_by
        self.rewards = rewards
        self.status = 'available'


class Location(BaseEntity):
    """
    Thực thể đại diện cho một địa điểm, bối cảnh không gian mà người chơi có thể di chuyển tới.
    """

    def __init__(self, id, name, description, atmosphere, image_path=None):
        """
        Khởi tạo một địa điểm.

        Args:
            atmosphere (str): Bầu không khí chủ đạo của khu vực (VD: "U ám", "Thanh bình").
            image_path (str, optional): Đường dẫn đến file ảnh nền của khu vực.
        """
        super().__init__(id, name, "location", description)
        self.atmosphere = atmosphere
        self.image_path = image_path


class NPC(BaseEntity):
    """
    Thực thể đại diện cho một nhân vật không phải người chơi (Non-Player Character).
    """

    def __init__(self, id, name, personality, description, affectionate, location, status, image_path=None):
        """
        Khởi tạo NPC.

        Args:
            personality (str): Tính cách đặc trưng của NPC, dùng để định hướng cho LLM nhập vai.
            affectionate (int): Điểm thiện cảm của NPC đối với người chơi.
            location (str): Vị trí hiện tại của NPC.
            status (str): Thể trạng hoặc tình trạng hiện tại (VD: "Khỏe mạnh", "Bị thương").
            image_path (str, optional): Đường dẫn đến file ảnh chân dung của NPC.
        """
        super().__init__(id, name, 'npc', description)
        self.status = status
        self.personality = personality
        self.affectionate = affectionate
        self.location = location
        self.image_path = image_path


@dataclass
class Memory:
    """
    Thực thể đại diện cho một Ký ức/Sự kiện (Memory) trong game.
    Sử dụng dataclass để tinh gọn mã nguồn cho các đối tượng chuyên chứa dữ liệu.
    Dùng để lưu trữ vào VectorDB phục vụ hệ thống RAG.

    Attributes:
        location (str): Tên địa điểm nơi diễn ra ký ức.
        text (str): Nội dung chi tiết của ký ức (hành động + kết quả).
        id (Optional[int]): ID của ký ức trong CSDL (mặc định None nếu chưa lưu).
        game_turn (int): Lượt chơi (turn) mà ký ức này được ghi nhận.
    """
    location: str
    text: str
    id: Optional[int] = None
    game_turn: int = None