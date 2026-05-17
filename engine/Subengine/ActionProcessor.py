import random
import os
import yaml
from engine.Agents.LocalAgents import IntentRouter
from static.config import RNG_WEIGHTS, Success_rate
from engine.Utils.logger import game_logger  # Thêm import logger


class ActionProcessor:
    def __init__(self, db, player_state, pm, yaml_path="static/action_directives.yaml"):
        self.db = db
        self.player_state = player_state
        self.intent_parser = IntentRouter(pm=pm, model_name="qwen2.5:1.5b")
        self.yaml_path = yaml_path

        # Xác suất Random Events (Sự kiện đột xuất)
        self.prob_have_npc = 5
        self.prob_new_location = 5

    def _load_yaml(self) -> dict:
        """
        Đọc file YAML và chuyển đổi thành Dictionary cho hệ thống sử dụng.
        """
        if not os.path.exists(self.yaml_path):
            game_logger.error(f"[ActionManager] Lỗi Hệ Thống: Không tìm thấy file YAML tại: {self.yaml_path}")
            # Trả về dict rỗng với cấu trúc cơ bản để tránh crash ActionManager
            return {"BaseDirectives": {}, "RNGModifiers": {}}

        try:
            with open(self.yaml_path, 'r', encoding='utf-8') as file:
                data = yaml.safe_load(file)
                game_logger.debug(f"[ActionManager] Đã tải thành công file {os.path.basename(self.yaml_path)}!")
                return data if data else {}

        except yaml.YAMLError as exc:
            game_logger.error(f"[ActionManager] Lỗi YAML: Sai cú pháp trong file {self.yaml_path}:\n{exc}")
            return {"BaseDirectives": {}, "RNGModifiers": {}}

    async def get_system_directive(self, player_input: str) -> str:
        intent_data = await self.intent_parser.parse_intent(player_input)
        intent = intent_data.get("intent", "GENERAL_ACTION")
        target = intent_data.get("target", "the target")

        # Xử lý an toàn: Nếu Intent trả về không có trong YAML, đưa về GENERAL_ACTION
        valid_intents = ["MOVE", "COMBAT", "EXAMINE", "TAKE", "USE", "FLEE", "STEALTH", "TALK", "GENERAL_ACTION"]
        if intent not in valid_intents:
            intent = "GENERAL_ACTION"

        # ==========================================
        # BƯỚC 1: ĐỔ XÍ NGẦU KIỂM TRA HÀNH ĐỘNG (CHECK DICE)
        # ==========================================
        action_roll = random.randint(1, 100)
        status = "SUCCESS" if action_roll <= Success_rate else "FAILURE"

        # Tải cấu hình YAML (Gán vào 1 biến để dùng chung)
        yaml_data = self._load_yaml()

        base_directives = yaml_data.get("BaseDirectives", {})

        # Thêm xử lý an toàn: Nếu không có intent trong YAML thì fallback về chuỗi rỗng trước khi gọi .get(status)
        intent_dict = base_directives.get(intent)
        if intent_dict is None:
            game_logger.warning(
                f"[ActionManager] Lỗi thiếu dữ liệu: Không tìm thấy intent '{intent}' trong {self.yaml_path}. Bỏ qua format.")
            directive_template = ""
        else:
            directive_template = intent_dict.get(status, "")

        # Format chuỗi với biến target
        try:
            system_directive = directive_template.format(target=target)
        except KeyError as e:
            game_logger.warning(
                f"[ActionManager] Cảnh báo Format chuỗi: Thiếu biến {e} trong template của intent '{intent}'.")
            system_directive = directive_template

        # ==========================================
        # BƯỚC 2: CỘNG DỒN HỆ SỐ & KÍCH HOẠT SỰ KIỆN RNG
        # ==========================================
        npc_inc, loc_inc = RNG_WEIGHTS.get(intent, (0, 0))
        self.prob_have_npc += npc_inc
        self.prob_new_location += loc_inc

        # [SỬA LỖI] Lấy RNGModifiers từ yaml_data vừa load, không gọi self.pm.yaml_data nữa
        rng_modifiers = yaml_data.get("RNGModifiers", {})

        # 1. ĐỔ XÍ NGẦU CHO NPC
        if intent not in ["TALK", "COMBAT"]:
            roll_npc = random.randint(1, 100)
            if roll_npc <= self.prob_have_npc:
                game_logger.info(f"[ActionManager] 🎲 Sự kiện NPC xuất hiện (Xí ngầu: {roll_npc}/{self.prob_have_npc})")
                npc_directive = rng_modifiers.get("NPC_EVENT", "")
                system_directive += f"\n{npc_directive}"
                self.prob_have_npc = 5  # Reset

        # 2. ĐỔ XÍ NGẦU CHO LOCATION
        if intent not in ["MOVE", "COMBAT"]:
            roll_loc = random.randint(1, 100)
            if roll_loc <= self.prob_new_location:
                game_logger.info(
                    f"[ActionManager] 🎲 Sự kiện Địa điểm ẩn (Xí ngầu: {roll_loc}/{self.prob_new_location})")
                loc_directive = rng_modifiers.get("LOCATION_EVENT", "")
                system_directive += f"\n{loc_directive}"
                self.prob_new_location = 5  # Reset

        return system_directive