#================================================#
#
#       Config for ActionProcessor.py
#
#================================================#
Success_rate = 70

RNG_WEIGHTS = {
            "EXAMINE": (2, 10),
            "MOVE": (10, 2),
            "GENERAL_ACTION": (4, 4),
            "COMBAT": (0, 0),
            "TALK": (0, 0),
            "TAKE": (0, 0),
            "USE": (0, 0),
            "FLEE": (5, 5),
            "STEALTH": (5, 0)
        }



#================================================#
#
#       Config for CloudAgents.py
#
#================================================#
STORY_AGENT_MODEL = "llama-3.3-70b-versatile"
QUERY_AGENT_MODEL = "llama-3.3-70b-versatile"
LOCATION_AGENT_MODEL = "qwen/qwen3-32b"
NPC_AGENT_MODEL = "qwen/qwen3-32b"
CHOICE_AGENT_MODEL = "qwen/qwen3-32b"
WORLD_GENERATE_AGENT_MODEL = "qwen/qwen3-32b"








#================================================#
#
#       Config for LocalAgents.py
#
#================================================#
INTENT_ROUTER_MODEL = "gemini-3.1-flash-lite"
STATE_EXTRACTOR_MODEL = "gemini-3.1-flash-lite"
MEMORY_EXTRACTOR_MODEL = "gemini-3.1-flash-lite"
ITEM_AGENT_MODEL = "gemini-3.1-flash-lite"
