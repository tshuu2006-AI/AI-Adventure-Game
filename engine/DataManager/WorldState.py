class WorldState:
    """Đối tượng lưu trữ các quy tắc bối cảnh (World Bible) đang áp dụng cho phiên chơi hiện tại."""

    def __init__(self):
        self.world_name = None
        self.world_type = None
        self.theme_and_tone = None
        self.core_conflict = None
        self.world_mission = None

        self.dynamic_lore = {}
        self.dynamic_vocabulary = {}


    def to_dict(self) -> dict:
        return {
            "name": self.world_name,
            "type": self.world_type,
            "theme_and_tone": self.theme_and_tone,
            "core_conflict": self.core_conflict,
            "mission": self.world_mission,
            "dynamic_vocabulary": self.dynamic_vocabulary
        }

    def load_state(self, data: dict):
        self.world_name = data.get("world_name", "Vùng đất vô danh")
        self.world_type = data.get("world_type", "Fantasy")
        self.theme_and_tone = data.get("theme_and_tone", "Tối tăm")
        self.core_conflict = data.get("core_conflict", "Sinh tồn")
        self.world_mission = data.get("world_mission", "Sống sót")
        self.dynamic_vocabulary = data.get("dynamic_vocabulary", {})