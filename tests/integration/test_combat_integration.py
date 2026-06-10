import pytest
from unittest.mock import MagicMock, AsyncMock
from engine.Subengine.StateProcessor import StateProcessor
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager

@pytest.mark.asyncio
async def test_combat_integration_damage():
    # Khởi tạo PlayerState với 100 HP và 10 Defense
    player_state = PlayerState(name="Warrior")
    player_state.stats.base_stats["defense"] = 10
    player_state.stats.max_hp = 100
    player_state.stats.current_hp = 100
    
    db = MagicMock()
    image_manager = MagicMock()
    pm = PromptManager('./static/prompts.yaml')
    
    # Khởi tạo StateProcessor
    processor = StateProcessor(
        db=db,
        player_state=player_state,
        image_manager=image_manager,
        provider="gemini",
        groq_api_key="dummy",
        local_api_key="dummy",
        pm=pm
    )
    
    # Mock combat_agent.extract_combat
    processor.combat_agent.extract_combat = AsyncMock(return_value={"taken_damage": 20})
    
    # Chạy _update_player_state với trạng thái bị tấn công
    await processor._update_player_state(
        items_added=[],
        items_removed=[],
        story_response="Bạn bị tấn công bởi yêu tinh rừng.",
        context="test_context",
        is_safe_zone=False,
        is_being_attacked=True
    )
    
    # Sát thương thực tế được tính toán là: 20 * (100 / (100 + 10)) = 18.18. HP còn lại = 100 - 18 = 82.
    assert player_state.stats.current_hp == 82
