class WorldState:
    """Đối tượng lưu trữ các quy tắc bối cảnh (World Bible) đang áp dụng cho phiên chơi hiện tại."""

    def __init__(self):
        self.name = None
        self.type = None
        self.theme_and_tone = None
        self.core_conflict = None
        self.world_mission = None

        self.dynamic_lore = {}
        self.dynamic_vocabulary = {}


    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.type,
            "theme_and_tone": self.theme_and_tone,
            "core_conflict": self.core_conflict,
            "mission": self.world_mission,
            "dynamic_vocabulary": self.dynamic_vocabulary
        }

    def load_state(self, data: dict):
        self.name = data.get("name")
        self.type = data.get("type")
        self.theme_and_tone = data.get("theme_and_tone")
        self.core_conflict = data.get("core_conflict")
        self.world_mission = data.get("mission")
        self.dynamic_vocabulary = data.get("dynamic_vocabulary", {})