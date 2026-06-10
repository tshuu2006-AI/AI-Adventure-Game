import pytest
from unittest.mock import MagicMock, AsyncMock
from engine.Subengine.QuestProcessor import QuestProcessor
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from world.Entity import Quest, Location, NPC

@pytest.mark.asyncio
async def test_quest_processor_switch_quest():
    player_state = PlayerState(name="TestHero")
    pm = PromptManager('./static/prompts.yaml')
    
    # Thiết lập vùng an toàn để có thể switch quest
    player_state.is_safe_zone = True
    
    quest1 = Quest(id=1, name="Nhiệm vụ 1", description="Tìm nước", objectives=["Tìm nước"], give_by="NPC1", rewards=[])
    quest2 = Quest(id=2, name="Nhiệm vụ 2", description="Tìm lửa", objectives=["Tìm lửa"], give_by="NPC2", rewards=[])
    
    player_state.add_quest(quest1)
    player_state.add_quest(quest2)
    player_state.active_quest = quest1
    player_state.currentLocation = Location(id=1, name="Rừng", description="Rừng sâu", atmosphere="U ám")
    player_state.currentNPCs = [NPC(id=1, name="Elara", personality="Tốt", description="Phù thủy", affectionate=10, location="Rừng", status="Bình thường")]
    
    processor = QuestProcessor(player_state=player_state, provider="gemini", pm=pm, local_api_key="dummy")
    
    # Mock QuestAgent.generate_transition_narrative
    processor.quest_agent.generate_transition_narrative = AsyncMock(return_value="Bạn rời Rừng để nhận nhiệm vụ mới.")
    
    # Thực hiện chuyển đổi nhiệm vụ
    transitive_text = await processor.switch_quest(target_quest=quest2, recent_story="Gặp Elara và nhận vật phẩm", current_choices=["Lựa chọn 1"])
    
    # Xác thực chuyển đổi
    assert transitive_text == "Bạn rời Rừng để nhận nhiệm vụ mới."
    assert player_state.active_quest == quest2
    assert quest1.status == "available"
    assert quest2.status == "in_progress"
    
    # Snapshot của quest1 phải được ghi lại chính xác
    assert quest1.snapshot is not None
    assert quest1.snapshot["location"].name == "Rừng"
    assert quest1.snapshot["npcs"][0].name == "Elara"
    assert quest1.snapshot["last_story"] == "Gặp Elara và nhận vật phẩm"
    assert quest1.snapshot["last_choices"] == ["Lựa chọn 1"]

@pytest.mark.asyncio
async def test_quest_processor_evaluate_turn_and_update_progress():
    player_state = PlayerState(name="TestHero")
    pm = PromptManager('./static/prompts.yaml')
    
    quest = Quest(id=1, name="Tìm đá quý", description="Tìm đá quý trong hang", objectives=["Tìm đá đỏ", "Tìm đá xanh"], give_by="Trưởng làng", rewards=[])
    quest.status = "in_progress"
    player_state.add_quest(quest)
    player_state.active_quest = quest
    
    processor = QuestProcessor(player_state=player_state, provider="gemini", pm=pm, local_api_key="dummy")
    
    # Mock QuestAgent.evaluate_quest_status
    mock_evaluation = {
        "objectives_status": [True, False],  # Đã hoàn thành mục tiêu 1, mục tiêu 2 chưa xong
        "is_new_quest_offered": False
    }
    processor.quest_agent.evaluate_quest_status = AsyncMock(return_value=mock_evaluation)
    
    # Đánh giá lượt chơi
    await processor.evaluate_turn(player_input="Tôi nhặt viên đá đỏ", story_response="Bạn đã tìm thấy viên đá đỏ rực.")
    
    # Xác thực tiến trình quest
    assert quest.is_finished == [True, False]
    assert quest.status == "in_progress"
