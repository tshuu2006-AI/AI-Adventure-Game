from dataclasses import dataclass
from typing import Optional

class BaseEntity:
    def __init__(self, id, name, type, description):
        self.id = id
        self.name = name
        self.type = type
        self.description = description


class BaseItem(BaseEntity):
    def __init__(self, id, name, description, item_type):
        super().__init__(id, name, 'item', description)
        self.item_type = item_type


class ConsumableItem(BaseItem):
    def __init__(self, id, name, description, effect):
        super().__init__(id, name, description, 'consumable')
        self.effect = effect

    def apply_effect(self, player_state) -> str:
        """Hàm thực thi logic hồi máu/năng lượng"""
        player_state.hp += self.effect
        if player_state.hp > player_state.max_hp:
            player_state.hp = player_state.max_hp

        return f"Đã sử dụng {self.name}. HP hồi phục {self.effect} điểm. (HP hiện tại: {player_state.hp}/{player_state.max_hp})"

class WeaponItem(BaseItem):
    def __init__(self, id, name, description,
                 base_damage=0,  # Base Stat
                 modifiers=None,  # Modifiers (Ví dụ: {"str": 5, "agi": -2})
                 status_effect=None,  # Status Effect (Ví dụ: "burn")
                 proc_chance=0.0):  # Tỷ lệ kích hoạt hiệu ứng (Ví dụ: 0.2 cho 20%)

        super().__init__(id, name, description, 'weapon')
        self.base_damage = base_damage
        self.modifiers = modifiers or {}
        self.status_effect = status_effect
        self.proc_chance = proc_chance


class QuestItem(BaseItem):
    def __init__(self, id, name, description, quest):
        super().__init__(id, name, description, 'quest')
        self.quest = quest


class MiscellaneousItem(BaseItem):
    def __init__(self, id, name, description):
        super().__init__(id, name, description, 'miscellaneous')


class Quest(BaseEntity):
    def __init__(self, id, name, description):
        super().__init__(id, name, 'quest', description)


class Location(BaseEntity):
    def __init__(self, id, name, description, atmosphere, image_path = None):
        super().__init__(id, name, "location", description)
        self.atmosphere = atmosphere
        self.image_path = image_path


class NPC(BaseEntity):
    def __init__(self, id, name, personality, description, affectionate, location, status, image_path = None):
        super().__init__(id, name, 'npc', description)
        self.status = status
        self.personality = personality
        self.affectionate = affectionate
        self.location = location
        self.image_path = image_path


@dataclass
class Memory:
    """
    Thực thể đại diện cho một Ký ức/Sự kiện trong game.
    """
    location: str
    text: str
    id: Optional[int] = None
    game_turn: int = None


