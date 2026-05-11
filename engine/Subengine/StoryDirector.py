import json
import time
from typing import AsyncGenerator
from world.Entity import Location

from engine.Agents.CloudAgents import StoryAgent, ChoiceAgent, WorldGenerateAgent, LocationAgent


class StoryDirector:
    """
    Quản lý toàn bộ quá trình sáng tạo nội dung của AI trên Cloud (Groq).
    Bao gồm: Viết cốt truyện, tạo menu lựa chọn, và thiết kế bối cảnh thế giới.
    """

    def __init__(self, groq_api_key, pm):
        self.pm = pm

        # CHÚ Ý LỰA CHỌN MODEL ĐỂ TỐI ƯU CHI PHÍ & TỐC ĐỘ:

        # 1. StoryAgent: Dùng Llama-3.3-70B để văn phong mượt mà, tự nhiên nhất
        self.story_agent = StoryAgent(api_key=groq_api_key, pm=self.pm, model_name="llama-3.3-70b-versatile")

        # 2. Các Agent xuất JSON: Dùng Qwen-32B để nhanh, rẻ và tuân thủ JSON tuyệt đối
        self.choice_agent = ChoiceAgent(api_key=groq_api_key, pm=self.pm, model_name="qwen/qwen3-32b")
        self.world_generator = WorldGenerateAgent(api_key=groq_api_key, pm=self.pm, model_name="qwen/qwen3-32b")
        self.location_agent = LocationAgent(api_key=groq_api_key, pm=self.pm, model_name="qwen/qwen3-32b")

    async def narrate_turn(self, player_input: str, world_state, player_state, npcs_context, hybrid_rag_context) -> \
    AsyncGenerator[str, None]:
        """
        Nhận toàn bộ Bối cảnh + RAG + Hành động của người chơi để sinh cốt truyện (Streaming).
        Hàm này trả về một Generator để GameOrchestrator có thể in từng chữ ra màn hình.
        """
        full_user_input = f"[Bối cảnh hiện tại]:\n{hybrid_rag_context}\n\n[Hành động mới của người chơi]: {player_input}"

        npc_names = [npc.name for npc in npcs_context] if npcs_context else ["Không có"]

        # Kích hoạt StoryAgent sinh chữ
        stream = self.story_agent.generate_story(
            world_theme=world_state.theme_and_tone,
            world_conflict=world_state.core_conflict,
            world_vocabulary=world_state.dynamic_vocabulary,
            current_location=player_state.currentLocation.name,
            npc_names=npc_names,
            rag_context=hybrid_rag_context,  # Đã bao gồm cả FAISS và Cửa sổ trượt 4 lượt
            system_directive="Narrate the immediate physical consequences of the player's action. Stop abruptly at a point of tension.",
            user_input=full_user_input
        )

        # Truyền luồng stream ra ngoài
        async for chunk in stream:
            yield chunk

    async def generate_player_choices(self, current_location_name: str, encountered_npc_name: str,
                                      recent_story_text: str) -> list:
        """
        Dựa vào kết quả đoạn truyện vừa sinh ra để làm ra 3-4 lựa chọn tiếp theo.
        """
        print("\n[StoryDirector] Đang tính toán các lựa chọn tiếp theo...")

        npc_name = encountered_npc_name if encountered_npc_name else "Không có"

        choices_data = await self.choice_agent.generate_choices(
            current_location=current_location_name,
            npc_name=npc_name,
            recent_story_summary=recent_story_text  # Đưa đoạn truyện vừa kể vào đây để AI ra lựa chọn sát thực tế
        )

        return choices_data.get('choices', [])

    # ---- CÁC HÀM KHỞI TẠO GAME BỎ VÀO ĐÂY ----
    async def create_world_bible(self, player_idea: str, path = './data/world_bible.json') -> dict:
        world_bible =  await self.world_generator.generate_bible(player_idea=player_idea)
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(world_bible, file, indent=4, ensure_ascii=False)
        return world_bible


    async def create_starting_location(self, world_name, world_type, theme):
        return await self.location_agent.initialize_location(world_name, world_type, theme)


    async def initialize_story(self, starting_location: Location):
        with open("./data/world_bible.json", "r", encoding='utf-8') as file:
            world_bible = json.load(file)

        sys_requirements = world_bible.get("system_requirements", {})
        world_name = sys_requirements.get("world_name", None)
        world_type = sys_requirements.get("world_type", None)
        world_mission = sys_requirements.get("world_mission", None)
        theme_and_tone = sys_requirements.get("theme_and_tone", None)
        core_conflict = sys_requirements.get("core_conflict", None)

        vocabulary = world_bible.get("dynamic_vocabulary", None)

        location_name = starting_location.name
        location_atmosphere = starting_location.atmosphere
        location_description = starting_location.description

        story_stream = self.story_agent.initialize_story(name=world_name,
                                                                 theme= theme_and_tone,
                                                                 core_conflict = core_conflict,
                                                                 mission = world_mission,
                                                                 vocab = vocabulary,
                                                                 location_name=location_name,
                                                                 location_atmosphere=location_atmosphere,
                                                                 location_description = location_description
                                                                 )

        async for chunk in story_stream:
            yield chunk


