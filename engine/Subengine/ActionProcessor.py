import random
import os
import yaml
from engine.Agents.LocalAgents import IntentRouter
from static.config import RNG_WEIGHTS, Success_rate
from engine.Utils.logger import game_logger
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from engine.DataManager.DatabaseManager import DatabaseManager


class ActionProcessor:
    """
    Xử lý hành động của người chơi, phân tích ý định (intent),
    kiểm tra tỷ lệ thành công (dice roll), và tạo ra các sự kiện ngẫu nhiên (RNG events).
    """

    def __init__(self, db: DatabaseManager,
                 player_state: PlayerState,
                 pm: PromptManager,
                 provider:str,
                 gemini_api_key: str,
                 yaml_path: str = "static/action_directives.yaml"):
        self.db = db
        self.player_state = player_state
        self.intent_parser = IntentRouter(pm=pm, provider = provider, api_key=gemini_api_key)
        self.yaml_path = yaml_path

        self.prob_have_npc = 5
        self.prob_new_location = 5

        # Cache YAML lúc khởi tạo — file này không thay đổi lúc runtime
        self._directives_cache = self._load_yaml()

    def _load_yaml(self) -> dict:
        if not os.path.exists(self.yaml_path):
            game_logger.error(f"[ActionManager] Lỗi Hệ Thống: Không tìm thấy file YAML tại: {self.yaml_path}")
            return {"BaseDirectives": {}, "RNGModifiers": {}}

        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
                game_logger.debug(f"[ActionManager] Đã tải thành công file {os.path.basename(self.yaml_path)}!")
                return data if data else {}
        except yaml.YAMLError as exc:
            game_logger.error(f"[ActionManager] Lỗi YAML: Sai cú pháp trong file {self.yaml_path}:\n{exc}")
            return {"BaseDirectives": {}, "RNGModifiers": {}}

    # ==========================================
    # COMBAT STATS BLOCK
    # ==========================================
    def _build_combat_stats_directive(self, status: str) -> str:
        """
        Tính toán và đóng gói chỉ số chiến đấu của người chơi thành một đoạn
        chỉ thị bổ sung cho StoryAgent.

        Không gọi LLM — toàn bộ là số học thuần túy từ PlayerState.
        StoryAgent dùng các con số này làm anchor để kể chuyện nhất quán,
        thay vì tự bịa damage/outcome.

        Args:
            status (str): "SUCCESS" hoặc "FAILURE" từ dice roll.

        Returns:
            str: Đoạn text chỉ thị combat stats, sẵn sàng nối vào system_directive.
        """
        stats = self.player_state.stats.total_stats
        weapon = self.player_state.get_equipped_weapon()

        # --- THÔNG SỐ NGƯỜI CHƠI ---
        strength   = stats.get("strength", 10)
        agility    = stats.get("agility", 10)
        defense    = stats.get("defense", 5)
        hp_current = self.player_state.get_current_hp()
        hp_max     = self.player_state.get_max_hp()
        hp_ratio   = hp_current / hp_max if hp_max > 0 else 1.0

        # --- THÔNG SỐ VŨ KHÍ ---
        if weapon:
            weapon_name   = weapon.name
            base_damage   = weapon.base_damage
            status_effect = weapon.status_effect    # VD: "burn", "poison", None
            proc_chance   = weapon.proc_chance      # VD: 0.2
        else:
            weapon_name   = "tay không"
            base_damage   = max(1, strength // 5)   # Bare-hand fallback: str/5
            status_effect = None
            proc_chance   = 0.0

        # --- TÍNH DAMAGE OUTPUT ---
        # Công thức: base_damage + str_bonus ± variance nhỏ
        # str_bonus: mỗi 10 str thêm 1 damage → tránh scaling quá mạnh
        str_bonus  = strength // 10
        variance   = random.randint(-2, 3)          # ±variance nhỏ để không bị flat
        deal_damage = max(1, base_damage + str_bonus + variance)

        # SUCCESS tăng 20% output, FAILURE giảm 30%
        if status == "SUCCESS":
            deal_damage = int(deal_damage * 1.2)
        else:
            deal_damage = int(deal_damage * 0.7)

        # --- PROC STATUS EFFECT ---
        # Kiểm tra ngay ở đây để đưa vào directive — không cần LLM đoán
        proc_triggered = (
            status_effect is not None
            and proc_chance > 0.0
            and random.random() < proc_chance
        )

        # --- MÔ TẢ TRẠNG THÁI MÁU (cho StoryAgent biết mức độ nguy hiểm) ---
        if hp_ratio >= 0.75:
            hp_description = "còn khỏe mạnh"
        elif hp_ratio >= 0.40:
            hp_description = "đã bị thương nhẹ"
        elif hp_ratio >= 0.15:
            hp_description = "đang chiến đấu với vết thương nặng"
        else:
            hp_description = "đang kiệt sức, gần chết"

        # --- ĐÓNG GÓI DIRECTIVE ---
        # Viết dưới dạng instruction rõ ràng để StoryAgent bám vào
        lines = [
            "\n[COMBAT STATS - FOLLOW STRICTLY]",
            f"Player weapon: {weapon_name} | Base damage output this strike: {deal_damage}",
            f"Player status: {hp_description} (HP {hp_current}/{hp_max})",
            f"Player agility: {agility} — {'high agility: describe swift, precise movements' if agility >= 15 else 'low agility: describe heavy, forceful but slower strikes'}",
        ]

        if proc_triggered:
            lines.append(
                f"PROC TRIGGERED: The weapon inflicts '{status_effect}' on the target this strike. "
                f"You MUST weave this effect naturally into the narration."
            )

        if status == "SUCCESS":
            lines.append(
                f"Outcome: Player's attack LANDS. The strike deals approximately {deal_damage} damage. "
                f"Narrate the physical impact clearly and viscerally."
            )
        else:
            lines.append(
                f"Outcome: Player's attack MISSES or is COUNTERED. "
                f"Narrate the failure — a dodge, parry, or stumble. "
                f"The enemy retaliates. Player takes damage fitting the enemy's strength."
            )

        game_logger.info(
            f"[Combat] Weapon: {weapon_name} | Damage: {deal_damage} | "
            f"Proc: {proc_triggered}({status_effect}) | HP: {hp_current}/{hp_max} | Roll: {status}"
        )

        return "\n".join(lines)

    async def get_system_directive(self, player_input: str) -> str:
        """
        Xử lý lệnh nhập của người chơi, sinh ra chỉ thị hệ thống dựa trên ý định,
        kết quả gieo xúc xắc và các yếu tố ngẫu nhiên (NPC, Location).

        Khi intent là COMBAT, bổ sung thêm combat stats block vào directive
        để StoryAgent có anchor số liệu cụ thể khi kể chuyện đánh nhau.

        Args:
            player_input (str): Chuỗi hành động người chơi nhập vào.

        Returns:
            str: Chỉ thị hệ thống (system directive) để điều hướng mạch truyện.
        """
        intent_data = await self.intent_parser.parse_intent(player_input)
        intent = intent_data.get("intent", "GENERAL_ACTION")
        target = intent_data.get("target", "the target")

        game_logger.debug(f"[ActionProcessor] Intent: {intent} | Target: {target}")

        valid_intents = ["MOVE", "COMBAT", "EXAMINE", "TAKE", "USE", "FLEE", "STEALTH", "TALK", "GENERAL_ACTION"]
        if intent not in valid_intents:
            intent = "GENERAL_ACTION"
        self.player_state.set_intent(intent=intent)

        action_roll = random.randint(1, 100)
        status = "SUCCESS" if action_roll <= Success_rate else "FAILURE"

        yaml_data = self._directives_cache
        base_directives = yaml_data.get("BaseDirectives", {})

        intent_dict = base_directives.get(intent)
        if intent_dict is None:
            game_logger.warning(
                f"[ActionManager] Không tìm thấy intent '{intent}' trong YAML. Bỏ qua format.")
            directive_template = ""
        else:
            directive_template = intent_dict.get(status, "")

        try:
            system_directive = directive_template.format(target=target)
        except KeyError as e:
            game_logger.warning(
                f"[ActionManager] Thiếu biến {e} trong template của intent '{intent}'.")
            system_directive = directive_template

        # ==========================================
        # COMBAT STATS INJECTION
        # Chỉ kích hoạt khi intent là COMBAT.
        # Không cần LLM call thêm — tính toán thuần túy từ PlayerState.
        # ==========================================
        if intent == "COMBAT":
            combat_directive = self._build_combat_stats_directive(status=status)
            system_directive += combat_directive

        npc_inc, loc_inc = RNG_WEIGHTS.get(intent, (0, 0))
        self.prob_have_npc += npc_inc
        self.prob_new_location += loc_inc

        rng_modifiers = yaml_data.get("RNGModifiers", {})

        # Kích hoạt sự kiện NPC (bỏ qua khi đang combat)
        if intent not in ["TALK", "COMBAT"]:
            roll_npc = random.randint(1, 100)
            if roll_npc <= self.prob_have_npc:
                game_logger.info(f"[ActionManager] Sự kiện NPC (Roll: {roll_npc}/{self.prob_have_npc})")
                system_directive += f"\n{rng_modifiers.get('NPC_EVENT', '')}"
                self.prob_have_npc = 5

        # Kích hoạt sự kiện Địa điểm mới (bỏ qua khi đang combat)
        if intent not in ["MOVE", "COMBAT"]:
            roll_loc = random.randint(1, 100)
            if roll_loc <= self.prob_new_location:
                game_logger.info(f"[ActionManager] Sự kiện Địa điểm ẩn (Roll: {roll_loc}/{self.prob_new_location})")
                system_directive += f"\n{rng_modifiers.get('LOCATION_EVENT', '')}"
                self.prob_new_location = 5

        return system_directive