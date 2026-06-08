import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from engine.Subengine.ActionProcessor import ActionProcessor
from engine.DataManager.PlayerState import PlayerState
from world.Entity import WeaponItem
from engine.Agents.CloudAgents import CombatAgent
from engine.Subengine.StateProcessor import StateProcessor
from engine.Utils.PromptManager import PromptManager

@pytest.fixture
def mock_prompt_manager():
    pm = MagicMock(spec=PromptManager)
    # Giả lập trả về prompt mẫu khi gọi get_prompt
    pm.get_prompt.return_value = "Mocked Prompt"
    return pm

def test_action_processor_build_combat_stats_directive_success():
    player_state = PlayerState(name="TestHero")
    player_state.stats.current_hp = 100
    player_state.stats.max_hp = 100
    player_state.stats.base_stats = {"strength": 15, "agility": 12, "defense": 5}
    
    mock_db = MagicMock()
    mock_pm = MagicMock(spec=PromptManager)
    
    # Khởi tạo ActionProcessor với các mock
    ap = ActionProcessor(
        db=mock_db,
        player_state=player_state,
        pm=mock_pm,
        provider="gemini",
        gemini_api_key="mock_key",
        yaml_path="static/action_directives.yaml"
    )
    
    # 1. Test với status = SUCCESS, không có vũ khí (tay không)
    directive = ap._build_combat_stats_directive(status="SUCCESS")
    
    assert "[COMBAT STATS - FOLLOW STRICTLY]" in directive
    assert "tay không" in directive
    assert "Outcome: Player's attack LANDS" in directive
    assert "Player status: còn khỏe mạnh" in directive

def test_action_processor_build_combat_stats_directive_failure_with_weapon():
    player_state = PlayerState(name="TestHero")
    player_state.stats.current_hp = 30
    player_state.stats.max_hp = 100
    player_state.stats.base_stats = {"strength": 20, "agility": 16, "defense": 8}
    
    # Trang bị vũ khí có hiệu ứng
    sword = WeaponItem(id=1, name="Thánh kiếm", description="Mô tả", base_damage=25, status_effect="burn", proc_chance=1.0)
    player_state.equip_weapon(sword)
    
    mock_db = MagicMock()
    mock_pm = MagicMock(spec=PromptManager)
    
    ap = ActionProcessor(
        db=mock_db,
        player_state=player_state,
        pm=mock_pm,
        provider="gemini",
        gemini_api_key="mock_key",
        yaml_path="static/action_directives.yaml"
    )
    
    # Test với status = FAILURE, HP thấp (bị thương nặng/kiệt sức), có vũ khí và hiệu ứng kích hoạt
    directive = ap._build_combat_stats_directive(status="FAILURE")
    
    assert "[COMBAT STATS - FOLLOW STRICTLY]" in directive
    assert "Thánh kiếm" in directive
    assert "PROC TRIGGERED: The weapon inflicts 'burn'" in directive
    assert "Outcome: Player's attack MISSES or is COUNTERED" in directive
    assert "Player status: đã bị thương nhẹ" in directive or "Player status: đang chiến đấu với vết thương nặng" in directive

@pytest.mark.asyncio
async def test_combat_agent_extract_combat(mock_prompt_manager):
    # Khởi tạo CombatAgent với API key ảo
    agent = CombatAgent(api_key="mock_groq_key", model_name="mock_model", pm=mock_prompt_manager)
    
    # Mock hàm _generate_json_with_retry bất đồng bộ
    expected_result = {"taken_damage": 12}
    agent._generate_json_with_retry = AsyncMock(return_value=expected_result)
    
    story_response = "Con quái vật vung vuốt sắc bén cào trúng ngực bạn, gây 12 sát thương."
    result = await agent.extract_combat(story_response)
    
    assert result == expected_result
    agent._generate_json_with_retry.assert_called_once()

@pytest.mark.asyncio
async def test_state_processor_combat_integration(mock_prompt_manager):
    player_state = PlayerState(name="Warrior")
    player_state.stats.current_hp = 100
    player_state.stats.max_hp = 100
    player_state.stats.base_stats = {"strength": 10, "agility": 10, "defense": 10} # defense = 10 -> damage reduction
    
    mock_db = MagicMock()
    mock_image = MagicMock()
    
    # Khởi tạo StateProcessor
    sp = StateProcessor(
        db=mock_db,
        player_state=player_state,
        image_manager=mock_image,
        provider="gemini",
        groq_api_key="mock_groq_key",
        gemini_api_key="mock_gemini_key",
        pm=mock_prompt_manager
    )
    
    # Mock combat_agent của StateProcessor
    sp.combat_agent = MagicMock(spec=CombatAgent)
    sp.combat_agent.extract_combat = AsyncMock(return_value={"taken_damage": 20})
    
    # Gọi update_player_state với is_being_attacked = True
    await sp._update_player_state(
        items_added=[],
        items_removed=[],
        story_response="Bạn bị tấn công bởi yêu tinh rừng.",
        context="context",
        is_safe_zone=False,
        is_being_attacked=True
    )
    
    # Kiểm tra sát thương thực tế nhận: 20 - 0.5 * defense(10) = 15 -> HP còn 100 - 15 = 85
    assert player_state.stats.current_hp == 85
    sp.combat_agent.extract_combat.assert_called_once_with(story_response="Bạn bị tấn công bởi yêu tinh rừng.")
