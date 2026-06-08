"""
Hệ thống quản lý chỉ số
"""
class StatsManager:
    """
    Quản lý hệ thống chỉ số của thực thể (người chơi, quái vật).
    Chịu trách nhiệm theo dõi máu (HP), các chỉ số gốc, chỉ số cộng thêm từ trang bị,
    và xử lý các logic tính toán sát thương, hồi phục.
    """

    def __init__(self, base_hp=100, base_str=10, base_agi=10, base_int=10):
        """
        Khởi tạo hệ thống chỉ số với các giá trị cơ sở mặc định.

        Args:
            base_hp (int): Lượng máu tối đa cơ bản.
            base_str (int): Chỉ số Sức mạnh gốc.
            base_agi (int): Chỉ số Nhanh nhẹn gốc.
            base_int (int): Chỉ số Trí lực gốc.
        """
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


    def clear(self, base_hp=100, base_str=10, base_agi=10, base_int=10):
        """
        Khôi phục sinh lực và chỉ số gốc về mức khởi điểm ban đầu (Reset).
        Xóa bỏ toàn bộ các chỉ số cộng thêm từ trang bị.
        """
        # 1. Reset Máu
        self.max_hp = base_hp
        self.current_hp = base_hp

        # 2. Reset Chỉ số gốc
        self.base_stats = {
            "strength": base_str,
            "agility": base_agi,
            "intelligence": base_int,
            "defense": 5
        }

        # 3. Xóa sạch buff từ vũ khí/trang bị cũ
        self.bonus_stats = {
            "strength": 0,
            "agility": 0,
            "intelligence": 0,
            "defense": 0
        }

    @property
    def total_stats(self):
        """
        Tự động tính tổng chỉ số (Gốc + Buff) mỗi khi được gọi.

        Returns:
            dict: Dictionary chứa tổng của từng chỉ số (ví dụ: sức mạnh, phòng thủ).
        """
        return {
            k: self.base_stats.get(k, 0) + self.bonus_stats.get(k, 0)
            for k in self.base_stats.keys()
        }

    def apply_effect(self, effect: dict):
        """
        Áp dụng các hiệu ứng vĩnh viễn hoặc hồi phục từ vật phẩm tiêu hao (Consumable).

        Args:
            effect (dict): Dictionary chứa các hiệu ứng cần áp dụng
                           (VD: {'hp': 50, 'strength': 2}).
        """
        if 'hp' in effect.keys():
            self.heal(effect['hp'])

        for k in self.base_stats:
            self.base_stats[k] += effect.get(k, 0)

    def apply_equipment(self, modifiers: dict):
        """
        Cập nhật chỉ số khi mặc hoặc tháo trang bị.
        Tự động xóa các chỉ số cộng thêm cũ trước khi áp dụng hệ số mới.

        Args:
            modifiers (dict): Dictionary chứa các chỉ số cộng thêm từ trang bị mới.
                              Truyền `None` hoặc `{}` nếu tháo trang bị.
        """
        # Xóa buff cũ
        self.bonus_stats = {"strength": 0, "agility": 0, "intelligence": 0, "defense": 0}

        # Gán buff mới
        if modifiers:
            # Bản đồ ánh xạ chuẩn hóa các key viết tắt từ LLM sang key chính thức
            normalization_map = {
                "str": "strength", "strength": "strength",
                "agi": "agility", "agility": "agility",
                "int": "intelligence", "intelligence": "intelligence",
                "def": "defense", "defense": "defense"
            }
            for k, v in modifiers.items():
                standard_key = normalization_map.get(k.lower().strip())
                if standard_key and standard_key in self.bonus_stats:
                    try:
                        self.bonus_stats[standard_key] = int(v)
                    except (ValueError, TypeError):
                        pass

    def heal(self, amount):
        """
        Hồi máu an toàn, đảm bảo lượng máu hiện tại không bao giờ vượt quá máu tối đa (max_hp).

        Args:
            amount (int/float): Lượng máu được hồi phục.
        """
        self.current_hp = min(self.max_hp, self.current_hp + amount)

    def take_damage(self, amount) -> int:
        """
        Tính toán và chịu lượng sát thương thực tế sau khi đã giảm trừ qua Giáp (Defense).
        Luôn đảm bảo sát thương nhận vào tối thiểu là 1 để tránh kẹt game.

        Args:
            amount (int/float): Lượng sát thương thô (đầu vào) trước khi giảm trừ.

        Returns:
            int: Lượng sát thương thực tế nhân vật phải gánh chịu (dùng để in ra log hoặc báo cho LLM).
        """
        # Lấy tổng điểm phòng thủ hiện tại (Gốc + Trang bị đang mặc)
        total_def = self.total_stats["defense"]

        # Sát thương thực = Sát thương gánh chịu - Giáp
        # Giới hạn mức sát thương tối thiểu là 1 để tránh việc "đánh không lủng giáp" gây kẹt game
        actual_damage = max(1, amount - 0.5 * total_def)

        # Trừ máu
        self.current_hp = round(max(0, self.current_hp - actual_damage))

        # Trả về sát thương thực tế để bạn có thể in ra log hoặc gửi cho LLM miêu tả
        return actual_damage

    def to_string(self):
        """
        Xuất chuỗi định dạng tóm tắt trạng thái chỉ số hiện tại.
        Được sử dụng để nạp vào Context/Prompt cho AI (StoryAgent) nắm bắt tình trạng nhân vật.

        Returns:
            str: Chuỗi thông tin tổng hợp (VD: "HP: 100/100 | STR: 15 | AGI: 10 | INT: 10 | DEF: 5").
        """
        t = self.total_stats
        return f"HP: {self.current_hp}/{self.max_hp} | STR: {t['strength']} | AGI: {t['agility']} | INT: {t['intelligence']} | DEF: {t['defense']}"

    def to_dict(self) -> dict:
        """Đóng gói chỉ số thành Dictionary để lưu game"""
        return {
            "max_hp": self.max_hp,
            "current_hp": self.current_hp,
            "base_stats": self.base_stats,
            "bonus_stats": self.bonus_stats
        }

    def load_state(self, data: dict):
        """Khôi phục chỉ số từ file save"""
        self.max_hp = data.get("max_hp", 100)
        self.current_hp = data.get("current_hp", 100)
        
        self.base_stats = data.get("base_stats", {
            "strength": 10, "agility": 10, "intelligence": 10, "defense": 5
        })
        self.bonus_stats = data.get("bonus_stats", {
            "strength": 0, "agility": 0, "intelligence": 0, "defense": 0
        })



    #==========================================================
    #=                     GETTER                             =
    #==========================================================
    def get_max_hp(self):
        return self.max_hp

    def get_current_hp(self):
        return self.current_hp