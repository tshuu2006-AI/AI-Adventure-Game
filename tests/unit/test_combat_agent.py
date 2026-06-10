import pytest
from unittest.mock import AsyncMock
from engine.Agents.CloudAgents import CombatAgent
from engine.Utils.PromptManager import PromptManager

@pytest.mark.asyncio
async def test_combat_agent_extract():
    pm = PromptManager('./static/prompts.yaml')
    
    agent = CombatAgent(api_key="dummy_key", pm=pm, model_name="dummy_model")
    
    mock_response = {"taken_damage": 12}
    agent._generate_json_with_retry = AsyncMock(return_value=mock_response)
    
    story = "Con quái vật vung vuốt sắc bén cào trúng ngực bạn, gây 12 sát thương."
    result = await agent.extract_combat(story_response=story)
    
    assert isinstance(result, dict)
    assert result.get("taken_damage") == 12
    agent._generate_json_with_retry.assert_called_once()
