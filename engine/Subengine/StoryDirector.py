import json
from typing import AsyncGenerator, List
from world.Entity import Location, Quest, NPC
from static.config import STORY_AGENT_MODEL, CHOICE_AGENT_MODEL, LOCATION_AGENT_MODEL, WORLD_GENERATE_AGENT_MODEL, NPC_AGENT_MODEL
from engine.Agents.CloudAgents import StoryAgent, ChoiceAgent, WorldGenerateAgent, LocationAgent, NPCAgent
from engine.Utils.logger import game_logger  # Thêm import logger
from engine.Utils.PromptManager import PromptManager
from engine.DataManager.WorldState import WorldState
from engine.DataManager.PlayerState import PlayerState

class StoryDirector:
    """
    Quản lý toàn bộ quá trình sáng tạo nội dung của AI trên Cloud (Groq).
    Đóng vai trò là Game Master (GM) tổng hợp dữ liệu từ các hệ thống khác
    để viết cốt truyện, tạo menu lựa chọn, và thiết kế bối cảnh thế giới.
    """

    def __init__(self, groq_api_key: str, pm: PromptManager):
        """
        Khởi tạo hệ thống Đạo diễn Cốt truyện và các Cloud Agents.

        Args:
            groq_api_key (str): Khóa API để kết nối với dịch vụ Groq (chạy Llama/Qwen).
            pm (PromptManager): Trình quản lý Prompt nạp từ file YAML.
        """
        self.pm = pm

        # CHÚ Ý LỰA CHỌN MODEL ĐỂ TỐI ƯU CHI PHÍ & TỐC ĐỘ:

        # 1. StoryAgent: Dùng để văn phong mượt mà, tự nhiên nhất
        self.story_agent = StoryAgent(api_key=groq_api_key, pm=self.pm, model_name=STORY_AGENT_MODEL)
        self.location_agent = LocationAgent(api_key=groq_api_key, pm=self.pm, model_name=LOCATION_AGENT_MODEL)
        self.npc_agent = NPCAgent(api_key=groq_api_key, pm=self.pm, model_name=NPC_AGENT_MODEL)

        # 2. Các Agent xuất JSON: Dùng Qwen-32B để nhanh, rẻ và tuân thủ JSON tuyệt đối
        self.choice_agent = ChoiceAgent(api_key=groq_api_key, pm=self.pm, model_name=CHOICE_AGENT_MODEL)
        self.world_generator = WorldGenerateAgent(api_key=groq_api_key, pm=self.pm, model_name=WORLD_GENERATE_AGENT_MODEL)

        game_logger.debug("[StoryDirector] Đã khởi tạo các Cloud Agents (Llama-3 & Qwen).")

    async def narrate_turn(self, player_input: str,
                           world_state: WorldState,
                           player_state: PlayerState,
                           npcs_context: List[NPC],
                           hybrid_rag_context: str,
                           system_directive: str) -> AsyncGenerator[str, None]:
        """
        Nhận toàn bộ Bối cảnh, RAG, Hành động của người chơi và Chỉ thị hệ thống
        để sinh cốt truyện tiếp theo (Streaming).

        Args:
            player_input (str): Lệnh hoặc câu thoại người chơi vừa nhập.
            world_state (WorldState): Trạng thái thế giới hiện tại (World Bible).
            player_state (PlayerState): Trạng thái của người chơi (vị trí, nhiệm vụ, v.v.).
            npcs_context (List[NPC]): Danh sách các NPC đang có mặt xung quanh.
            hybrid_rag_context (str): Văn bản tổng hợp từ Ký ức ngắn hạn (Window) và dài hạn (FAISS).
            system_directive (str): Chỉ thị bắt buộc từ hệ thống (VD: "Ép đồ bị hỏng", "Chuyển map").

        Yields:
            str: Từng cụm ký tự (chunk) của đoạn truyện để in ra màn hình theo thời gian thực (hiệu ứng gõ chữ).
        """
        full_user_input = f"[Context]:\n{hybrid_rag_context}\n\n[Player action]: {player_input}"

        if npcs_context:
            npc_context_str = "\n".join(
                [f"- {npc.name}: Thiện cảm {npc.affectionate}/100, Thể trạng: {npc.status}"
                 for npc in npcs_context]
            )
        else:
            npc_context_str = "Nobody is near"

        active_quest = player_state.active_quest
        objectives = active_quest.objectives.copy() if active_quest else []

        for i in range(len(objectives)):
            if active_quest.is_finished[i]:
                objectives[i] = "[completed]"

        active_quest_context = ""
        if active_quest:
            active_quest_context += f'Name: {active_quest.name}\n Description: {active_quest.description}\n Objectives: {objectives}'

        items = player_state.quest_items
        quest_items = []
        for i, item in enumerate(items):
            item_str = f"Item#{i}:\n - Name: {item.name}\n - Description: {item.description}"
            quest_items.append(item_str)
        quest_items_str = "\n".join(quest_items)

        game_logger.debug(
            f"[StoryDirector] Bắt đầu sinh luồng truyện (Streaming) cho hành động: '{player_input[:50]}...'")

        # Kích hoạt StoryAgent sinh chữ
        stream = self.story_agent.generate_story(
            world_theme=world_state.theme_and_tone,
            world_conflict=world_state.core_conflict,
            world_vocabulary=world_state.dynamic_vocabulary,
            current_location=player_state.currentLocation.name if player_state.currentLocation else "Không xác định",
            npc_context=npc_context_str,
            rag_context=hybrid_rag_context,  # Đã bao gồm cả FAISS và Cửa sổ trượt 4 lượt
            system_directive=system_directive,
            user_input=full_user_input,
            active_quest_context=active_quest_context,
            quest_items=quest_items_str
        )

        # Truyền luồng stream ra ngoài
        async for chunk in stream:
            yield chunk

    async def generate_player_choices(self, current_location_name: str, encountered_npc_name: str,
                                      recent_story_text: str, active_quest: Quest, quest_items: List) -> list:
        """
        Dựa vào đoạn truyện vừa được kể xong để suy luận và tạo ra 3-4 gợi ý hành động
        (menu options) khả thi cho người chơi.

        Args:
            current_location_name (str): Tên địa điểm người chơi đang đứng.
            encountered_npc_name (str): Tên NPC đang tương tác (nếu có).
            recent_story_text (str): Đoạn truyện Game Master vừa kể xong.
            active_quest (Quest): Nhiệm vụ người chơi đang theo dõi (để tạo lựa chọn bám sát quest).
            quest_items (List): Danh sách các vật phẩm nhiệm vụ người chơi đang sở hữu.

        Returns:
            list: Danh sách các dictionary, mỗi dict chứa thông tin về một lựa chọn (id, action_text, style).
        """
        game_logger.info("[StoryDirector] Đang tính toán các lựa chọn tiếp theo...")

        npc_name = encountered_npc_name if encountered_npc_name else "Không có"

        objectives = active_quest.objectives.copy() if active_quest else []

        for i in range(len(objectives)):
            if active_quest and active_quest.is_finished[i]:
                objectives[i] = "[completed]"

        active_quest_context = ""
        if active_quest:
            active_quest_context += f'Name: {active_quest.name}\n Description: {active_quest.description}\n Objectives:\n {"\n".join(objectives)}'

        items = quest_items
        formatted_quest_items = []
        for i, item in enumerate(items):
            item_str = f"Item#{i}:\n - Name: {item.name}\n - Description: {item.description}"
            formatted_quest_items.append(item_str)
        quest_items_str = "\n".join(formatted_quest_items)

        choices_data = await self.choice_agent.generate_choices(
            current_location=current_location_name,
            npc_name=npc_name,
            recent_story_summary=recent_story_text,  # Đưa đoạn truyện vừa kể vào đây để AI ra lựa chọn sát thực tế
            active_quest_context=active_quest_context,
            quest_items=quest_items_str
        )

        choices_list = choices_data.get('choices', [])
        game_logger.debug(f"[StoryDirector] Đã tạo thành công {len(choices_list)} lựa chọn khả thi.")

        return choices_list

    # ---- CÁC HÀM KHỞI TẠO GAME BỎ VÀO ĐÂY ----
    async def create_world_bible(self, player_idea: str, path: str = './data/world_bible.json') -> dict:
        """
        Khởi tạo "Kinh thánh thế giới" (World Bible) dựa trên ý tưởng một câu của người chơi,
        sau đó lưu xuống tệp JSON để tái sử dụng.

        Args:
            player_idea (str): Ý tưởng bối cảnh từ người chơi (VD: "Thế giới hậu tận thế zombie").
            path (str, optional): Đường dẫn lưu file json. Mặc định là './data/world_bible.json'.

        Returns:
            dict: Toàn bộ cấu trúc từ điển chứa World Bible (theme, luật lệ, từ vựng...).
        """
        game_logger.info("[StoryDirector] Đang tạo World Bible từ ý tưởng người chơi...")
        world_bible = await self.world_generator.generate_bible(player_idea=player_idea)

        try:
            with open(path, 'w', encoding='utf-8') as file:
                json.dump(world_bible, file, indent=4, ensure_ascii=False)
            game_logger.debug(f"[StoryDirector] Đã lưu World Bible xuống file: {path}")
        except Exception as e:
            game_logger.error(f"[StoryDirector Lỗi] Không thể lưu file World Bible: {e}", exc_info=True)

        return world_bible


    async def create_starting_location(self, world_state: WorldState) -> Location:
        """
        Khởi tạo địa điểm xuất phát đầu tiên cho người chơi dựa trên bối cảnh thế giới.

        Args:
            world_state (WorldState): Thông tin thế giới

        Returns:
            Location: Đối tượng Location chứa thông tin về điểm khởi đầu.
        """
        game_logger.info(f"[StoryDirector] Đang khởi tạo địa điểm xuất phát cho thế giới")
        return await self.location_agent.initialize_location(world_state=world_state)


    async def initialize_key_npcs(self, world_state: WorldState) -> list:
        """
        Khởi tạo các NPC quan trọng (Key NPCs) ngay từ lúc bắt đầu game để tạo động lực và xung đột.

        Args:
            world_state (WorldState): Thông tin thế giới

        Returns:
            list: Danh sách chứa dictionary thông tin của các NPC khởi đầu.
        """
        game_logger.info(f"[StoryDirector] Đang khởi tạo các npc quan trọng cho thế giới")
        return await self.npc_agent.initialize_npcs(world_state=world_state)


    async def initialize_story(self, starting_location: Location, world_bible_dir: str) -> AsyncGenerator[str, None]:
        """
        Sinh đoạn văn bản mở màn (Prologue) dạng luồng (Streaming) khi người chơi bắt đầu game mới,
        nhằm giới thiệu bối cảnh, mục tiêu và đưa người chơi vào địa điểm xuất phát.

        Args:
            starting_location (Location): Đối tượng địa điểm nơi người chơi thức dậy/bắt đầu.
            world_bible_dir (str): Đường dẫn tới file world_bible.json để nạp luật thế giới.

        Yields:
            str: Từng cụm ký tự (chunk) của đoạn truyện mở đầu.
        """
        try:
            with open(world_bible_dir, "r", encoding='utf-8') as file:
                world_bible = json.load(file)
        except Exception as e:
            game_logger.error(f"[StoryDirector Lỗi] Không thể đọc file world_bible.json: {e}", exc_info=True)
            world_bible = {}  # Fallback an toàn

        sys_requirements = world_bible.get("system_requirements", {})
        world_name = sys_requirements.get("world_name", None)
        world_mission = sys_requirements.get("world_mission", None)
        theme_and_tone = sys_requirements.get("theme_and_tone", None)
        core_conflict = sys_requirements.get("core_conflict", None)

        vocabulary = world_bible.get("dynamic_vocabulary", None)

        location_name = starting_location.name
        location_atmosphere = starting_location.atmosphere
        location_description = starting_location.description

        game_logger.info(f"[StoryDirector] Bắt đầu sinh phân đoạn truyện mở đầu tại '{location_name}'...")

        story_stream = self.story_agent.initialize_story(name=world_name,
                                                         theme=theme_and_tone,
                                                         core_conflict=core_conflict,
                                                         mission=world_mission,
                                                         vocab=vocabulary,
                                                         location_name=location_name,
                                                         location_atmosphere=location_atmosphere,
                                                         location_description=location_description
                                                         )

        async for chunk in story_stream:
            yield chunk