import random
from engine.Agents.LocalAgents import IntentRouter
from static.config import RNG_WEIGHTS, Success_rate

class ActionProcessor:
    def __init__(self, db, player_state, pm):
        self.db = db
        self.player_state = player_state
        self.pm = pm  # Lưu lại PromptManager để gọi YAML
        self.intent_parser = IntentRouter(pm=pm, model_name="qwen2.5:1.5b")

        # Xác suất Random Events (Sự kiện đột xuất)
        self.prob_have_npc = 5
        self.prob_new_location = 5


    async def pre_process(self, player_input: str) -> str:
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

        # Lấy Template từ YAML qua PromptManager (truy xuất lồng 2 cấp: Intent -> Status)
        # Cấu trúc an toàn dùng .get() để tránh KeyError nếu YAML bị thiếu
        base_directives = self.pm.yaml_data.get("BaseDirectives", {})
        directive_template = base_directives.get(intent, {}).get(status, "")

        # Format chuỗi với biến target
        system_directive = directive_template.format(target=target)

        # ==========================================
        # BƯỚC 2: CỘNG DỒN HỆ SỐ & KÍCH HOẠT SỰ KIỆN RNG
        # ==========================================
        npc_inc, loc_inc = RNG_WEIGHTS.get(intent, (0, 0))
        self.prob_have_npc += npc_inc
        self.prob_new_location += loc_inc

        rng_modifiers = self.pm.yaml_data.get("RNGModifiers", {})

        # 1. ĐỔ XÍ NGẦU CHO NPC
        if intent not in ["TALK", "COMBAT"]:
            roll_npc = random.randint(1, 100)
            if roll_npc <= self.prob_have_npc:
                print(f"[RNG] 🎲 Triggering NPC Event ({roll_npc}/{self.prob_have_npc})")
                npc_directive = rng_modifiers.get("NPC_EVENT", "")
                system_directive += f"\n{npc_directive}"
                self.prob_have_npc = 5  # Reset

        # 2. ĐỔ XÍ NGẦU CHO LOCATION
        if intent not in ["MOVE", "COMBAT"]:
            roll_loc = random.randint(1, 100)
            if roll_loc <= self.prob_new_location:
                print(f"[RNG] 🎲 Triggering Location Event ({roll_loc}/{self.prob_new_location})")
                loc_directive = rng_modifiers.get("LOCATION_EVENT", "")
                system_directive += f"\n{loc_directive}"
                self.prob_new_location = 5  # Reset

        return system_directive