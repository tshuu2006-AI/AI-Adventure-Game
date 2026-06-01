from dataclasses import dataclass, field
from typing import Optional
import time

class BaseEntity:
    def __init__(self, id, name, type, description):
        self.id = id
        self.name = name
        self.type = type
        self.description = description


class Item(BaseEntity):
    def __init__(self, id, name, description, item_type="generic", effect=None, image_path=None, quest_id=None):
        super().__init__(id, name, "item", description)
        self.item_type = item_type
        self.effect = effect if effect is not None else {}
        self.image_path = image_path
        self.quest_id = quest_id


class ConsumableItem(Item):
    def __init__(self, id, name, description, effect, image_path=None, quest_id=None):
        super().__init__(
            id=id,
            name=name,
            description=description,
            item_type="ConsumableItem",
            effect=effect,
            image_path=image_path,
            quest_id=quest_id,
        )


class WeaponItem(Item):
    def __init__(self, id, name, description, damage=0, rarity="common", image_path=None, quest_id=None):
        super().__init__(
            id=id,
            name=name,
            description=description,
            item_type="WeaponItem",
            effect={"damage": damage, "rarity": rarity},
            image_path=image_path,
            quest_id=quest_id,
        )
        self.damage = damage
        self.rarity = rarity


class QuestItem(Item):
    def __init__(self, id, name, description, image_path=None, quest_id=None):
        super().__init__(
            id=id,
            name=name,
            description=description,
            item_type="QuestItem",
            effect={},
            image_path=image_path,
            quest_id=quest_id,
        )


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


@dataclass
class Quest:
    id: Optional[int] = None
    title: str = ""
    description: str = ""
    objectives: list[str] = field(default_factory=list)
    status: str = "available"
    reward_type: str = "ConsumableItem"
    reward_data: dict = field(default_factory=dict)
    linked_npc_names: list[str] = field(default_factory=list)
    linked_location: Optional[str] = None
    progress_notes: list[str] = field(default_factory=list)
    completion_hint: str = ""
    reward_claimed: bool = False
    turn_created: int = 0
    turn_completed: Optional[int] = None
    branch_id: Optional[int] = None
    branch_state: str = "available"
    branch_checkpoint: dict = field(default_factory=dict)
    branch_start_turn: Optional[int] = None
    branch_end_turn: Optional[int] = None
    branch_origin_location: Optional[str] = None
    branch_origin_npcs: list[str] = field(default_factory=list)
    branch_story_snapshot: str = ""
    return_transition: str = ""

    def lifecycle_state(self) -> str:
        if self.reward_claimed and self.turn_completed is not None:
            return "rewarded"
        if self.branch_state in {"completed", "rewarded", "abandoned", "paused", "active", "available"}:
            return self.branch_state
        if self.status == "completed":
            return "completed"
        return self.status


