import random
from engine.Agents.LocalAgents import IntentRouter


class ActionProcessor:
    def __init__(self, db, player_state, pm):
        self.db = db
        self.player_state = player_state
        self.intent_parser = IntentRouter(pm=pm, model_name="qwen2.5:1.5b")

        # Base Probability (Percentage)
        self.prob_have_npc = 10
        self.prob_new_location = 5


    async def pre_process(self, player_input: str) -> dict:
        intent_data = await self.intent_parser.parse_intent(player_input)
        intent = intent_data.get("intent", "GENERAL_ACTION")
        target = intent_data.get("target", "")

        system_directive = ""

            # 2. MOVE (Propose movement)
        if intent == "MOVE" and target:
            system_directive = (
                f"The player WANTS to move to '{target}'. "
                f"Evaluate the physical and logical possibility. If successful, narrate the transition and strictly set `current_location` to '{target}'. "
                f"If blocked, narrate the failure and keep the old location."
            )
            self.prob_new_location = 5

            # 3. COMBAT
        elif intent == "COMBAT":
            system_directive = (
                "The player initiates combat or a hostile action. "
                "Narrate with a fast pace, focusing on physical actions, weapons used, and damage impact."
            )
            self.prob_have_npc = 10

            # 4. EXAMINE
        elif intent == "EXAMINE":
            system_directive = (
                "The player is examining the surroundings or an object. "
                "Focus on rich sensory details (visual, auditory, tactile) to provide clues without necessarily advancing the plot too fast."
            )

        # ==========================================
        # 5. DYNAMIC ENCOUNTERS (RNG)
        # ==========================================

        self.prob_have_npc += 5
        self.prob_new_location += 2

        # RNG FOR NPC (Only roll if not actively interacting with one)
        if intent not in ["TALK", "COMBAT"]:
            roll_npc = random.randint(1, 100)
            if roll_npc <= self.prob_have_npc:
                print(f"[RNG] 🎲 Triggering NPC Event ({roll_npc}/{self.prob_have_npc})")

                npc_directive = (
                    " [SUDDEN EVENT] A character, creature, or monster (either fitting the current context or ENTIRELY NEW) "
                    "suddenly appears and interrupts or interacts with the player. You MUST log this entity's name in `new_npc_encountered`."
                )
                system_directive += npc_directive
                self.prob_have_npc = 10

                # RNG FOR NEW LOCATION (Only roll if not actively moving)
        if intent != "MOVE":
            roll_loc = random.randint(1, 100)
            if roll_loc <= self.prob_new_location:
                print(f"[RNG] 🎲 Triggering Location Event ({roll_loc}/{self.prob_new_location})")

                loc_directive = (
                    " [SUDDEN DISCOVERY] The player accidentally stumbles into, falls into, or discovers a BRAND NEW HIDDEN LOCATION "
                    "(e.g., a secret cave, a hidden room, a dark thicket). Narrate this discovery and strictly set `current_location` to this new place."
                )
                system_directive += loc_directive
                self.prob_new_location = 5

        return system_directive