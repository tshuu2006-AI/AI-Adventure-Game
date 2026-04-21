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
    def __init__(self, id, name, description):
        super().__init__(id, name, "item", description)


class Location(BaseEntity):
    def __init__(self, id, name, description, state, image_path = None):
        super().__init__(id, name, "location", description)
        self.state = state
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
    npc: Optional[str] = None
    id: Optional[int] = None
    id_type: str = "memory"
    made_at: int = field(default_factory=lambda: int(time.time()))

@dataclass
class Quest:
    """
    Thực thể đại diện cho một Nhiệm vụ trong game.
    """
    id: str
    title: str
    description: str
    giver_npc: str
    target_item: Optional[str] = None
    reward_item: Optional[str] = None
    status: str = "active"