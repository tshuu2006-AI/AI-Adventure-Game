import random
import os
import yaml
from engine.Agents.LocalAgents import IntentRouter
from static.config import RNG_WEIGHTS, Success_rate
from engine.Utils.logger import game_logger
from static.config import INTENT_ROUTER_MODEL
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
                 gemini_api_key: str,
                 yaml_path: str = "static/action_directives.yaml"):
        """
        Khởi tạo bộ xử lý hành động.

        Args:
            db (DatabaseManager): Trình quản lý cơ sở dữ liệu.
            player_state (PlayerState): Trạng thái hiện tại của người chơi.
            pm (PromptManager): Trình quản lý prompt.
            gemini_api_key (str): API key để sử dụng Gemini.
            yaml_path (str): Đường dẫn đến file cấu hình chỉ thị hành động.
        """
        self.db = db
        self.player_state = player_state
        self.intent_parser = IntentRouter(pm=pm, model_name=INTENT_ROUTER_MODEL, gemini_api_key=gemini_api_key)
        self.yaml_path = yaml_path

        self.prob_have_npc = 5
        self.prob_new_location = 5

        self._directives_cache = self._load_yaml()

    def _load_yaml(self) -> dict:
        """
        Đọc và phân tích file cấu hình YAML chứa các chỉ thị (directives) và bộ sửa đổi (modifiers).

        Returns:
            dict: Dữ liệu được cấu trúc từ file YAML, hoặc dict rỗng nếu có lỗi.
        """
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

    async def get_system_directive(self, player_input: str) -> str:
        """
        Xử lý lệnh nhập của người chơi, sinh ra chỉ thị hệ thống dựa trên ý định,
        kết quả gieo xúc xắc và các yếu tố ngẫu nhiên (NPC, Location).

        Args:
            player_input (str): Chuỗi hành động người chơi nhập vào.

        Returns:
            str: Chỉ thị hệ thống (system directive) để điều hướng mạch truyện.
        """
        intent_data = await self.intent_parser.parse_intent(player_input)
        intent = intent_data.get("intent", "GENERAL_ACTION")
        target = intent_data.get("target", "the target")

        print(intent)

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
                f"[ActionManager] Lỗi thiếu dữ liệu: Không tìm thấy intent '{intent}' trong {self.yaml_path}. Bỏ qua format.")
            directive_template = ""
        else:
            directive_template = intent_dict.get(status, "")

        try:
            system_directive = directive_template.format(target=target)
        except KeyError as e:
            game_logger.warning(
                f"[ActionManager] Cảnh báo Format chuỗi: Thiếu biến {e} trong template của intent '{intent}'.")
            system_directive = directive_template

        npc_inc, loc_inc = RNG_WEIGHTS.get(intent, (0, 0))
        self.prob_have_npc += npc_inc
        self.prob_new_location += loc_inc

        rng_modifiers = yaml_data.get("RNGModifiers", {})

        # Kích hoạt sự kiện NPC
        if intent not in ["TALK", "COMBAT"]:
            roll_npc = random.randint(1, 100)
            if roll_npc <= self.prob_have_npc:
                game_logger.info(f"[ActionManager] Sự kiện NPC xuất hiện (Xí ngầu: {roll_npc}/{self.prob_have_npc})")
                npc_directive = rng_modifiers.get("NPC_EVENT", "")
                system_directive += f"\n{npc_directive}"
                self.prob_have_npc = 5  # Reset xác suất

        # Kích hoạt sự kiện Địa điểm mới
        if intent not in ["MOVE", "COMBAT"]:
            roll_loc = random.randint(1, 100)
            if roll_loc <= self.prob_new_location:
                game_logger.info(f"[ActionManager] Sự kiện Địa điểm ẩn (Xí ngầu: {roll_loc}/{self.prob_new_location})")
                loc_directive = rng_modifiers.get("LOCATION_EVENT", "")
                system_directive += f"\n{loc_directive}"
                self.prob_new_location = 5  # Reset xác suất

        return system_directive