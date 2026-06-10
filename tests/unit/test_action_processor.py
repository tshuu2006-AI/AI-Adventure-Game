import pytest
from unittest.mock import MagicMock
from engine.Subengine.ActionProcessor import ActionProcessor
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from world.Entity import WeaponItem

def test_action_processor_build_combat_stats_directive_success():
    player_state = PlayerState(name="TestHero")
    player_state.stats.base_stats = {
        "strength": 15,
        "agility": 12,
        "intelligence": 10,
        "defense": 5
    }
    player_state.stats.current_hp = 100
    player_state.stats.max_hp = 100
    
    db = MagicMock()
    pm = PromptManager('./static/prompts.yaml')
    
    processor = ActionProcessor(db=db, player_state=player_state, pm=pm, provider="gemini", local_api_key="dummy", yaml_path='./static/action_directives.yaml')
    
    # Sinh chỉ thị chiến đấu thành công (SUCCESS)
    directive = processor._build_combat_stats_directive(status="SUCCESS")
    
    assert "[COMBAT STATS - FOLLOW STRICTLY]" in directive
    assert "Player weapon: tay không" in directive
    assert "Player status: còn khỏe mạnh" in directive
    assert "Outcome: Player's attack LANDS" in directive

def test_action_processor_build_combat_stats_directive_failure():
    player_state = PlayerState(name="TestHero")
    player_state.stats.current_hp = 30
    player_state.stats.max_hp = 100
    
    # Trang bị vũ khí "Thánh kiếm"
    weapon = WeaponItem(id=1, name="Thánh kiếm", description="Thánh kiếm diệt quỷ", base_damage=25, modifiers={}, status_effect="burn", proc_chance=1.0)
    player_state.equip_weapon(weapon)
    
    db = MagicMock()
    pm = PromptManager('./static/prompts.yaml')
    
    processor = ActionProcessor(db=db, player_state=player_state, pm=pm, provider="gemini", local_api_key="dummy", yaml_path='./static/action_directives.yaml')
    
    # Sinh chỉ thị chiến đấu thất bại (FAILURE)
    directive = processor._build_combat_stats_directive(status="FAILURE")
    
    assert "[COMBAT STATS - FOLLOW STRICTLY]" in directive
    assert "Player weapon: Thánh kiếm" in directive
    assert "đang chiến đấu với vết thương nặng" in directive
    assert "PROC TRIGGERED: The weapon inflicts 'burn' on the target" in directive
    assert "Outcome: Player's attack MISSES or is COUNTERED" in directive
