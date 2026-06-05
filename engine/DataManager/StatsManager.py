class StatsManager:
    def __init__(self, base_hp=100, base_str=10, base_agi=10, base_int=10):
        # 1. Máu
        self.max_hp = base_hp
        self.current_hp = base_hp

        # 2. Chỉ số gốc (Nội tại cơ thể - chỉ tăng vĩnh viễn)
        self.base_stats = {
            "strength": base_str,
            "agility": base_agi,
            "intelligence": base_int,
            "defense": 5
        }

        # 3. Chỉ số cộng thêm (Từ 1 món vũ khí/trang bị duy nhất)
        self.bonus_stats = {
            "strength": 0, "agility": 0, "intelligence": 0, "defense": 0
        }

    @property
    def total_stats(self):
        """Tự động tính tổng chỉ số (Gốc + Buff) mỗi khi được gọi"""
        return {
            k: self.base_stats.get(k, 0) + self.bonus_stats.get(k, 0)
            for k in self.base_stats.keys()
        }

    def apply_equipment(self, modifiers: dict):
        """Cập nhật chỉ số khi mặc/tháo trang bị"""
        # Xóa buff cũ
        self.bonus_stats = {"strength": 0, "agility": 0, "intelligence": 0, "defense": 0}

        # Gán buff mới
        if modifiers:
            for k, v in modifiers.items():
                if k in self.bonus_stats:
                    self.bonus_stats[k] = v

    def heal(self, amount):
        """Hồi máu an toàn"""
        self.current_hp = min(self.max_hp, self.current_hp + amount)

    def take_damage(self, amount) -> int:
        """
        Hàm chịu sát thương có tính toán giảm trừ dựa trên Defense.
        Trả về lượng sát thương thực tế phải chịu.
        """
        # Lấy tổng điểm phòng thủ hiện tại (Gốc + Trang bị đang mặc)
        total_def = self.total_stats["defense"]

        # Sát thương thực = Sát thương gánh chịu - Giáp
        # Giới hạn mức sát thương tối thiểu là 1 để tránh việc "đánh không lủng giáp" gây kẹt game
        actual_damage = max(1, amount - 0.5 * total_def)

        # Trừ máu
        self.current_hp = round(max(0, self.current_hp - actual_damage))

        # Trả về sát thương thực tế để bạn có th    ể in ra log hoặc gửi cho LLM miêu tả
        return actual_damage

    def to_string(self):
        """Xuất chuỗi để gửi cho LLM kể chuyện"""
        t = self.total_stats
        return f"HP: {self.current_hp}/{self.max_hp} | STR: {t['strength']} | AGI: {t['agility']} | INT: {t['intelligence']} | DEF: {t['defense']}"