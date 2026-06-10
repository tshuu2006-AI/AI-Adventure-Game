import pytest
from unittest.mock import MagicMock, AsyncMock
from engine.Subengine.ItemProcessor import ItemProcessor
from engine.DataManager.PlayerState import PlayerState
from engine.Utils.PromptManager import PromptManager
from world.Entity import WeaponItem, ConsumableItem, MiscellaneousItem

@pytest.mark.asyncio
async def test_item_processor_craft_success():
    player_state = PlayerState(name="TestHero")
    pm = PromptManager('./static/prompts.yaml')
    
    # Tạo vũ khí nguyên liệu và thêm vào balo
    iron = MiscellaneousItem(id=1, name="Sắt vụn", description="Mảnh sắt gỉ sét")
    wood = MiscellaneousItem(id=2, name="Gỗ vụn", description="Nhành cây khô")
    player_state.add_item(iron)
    player_state.add_item(wood)
    
    processor = ItemProcessor(player_state=player_state, provider="gemini", local_api_key="dummy", pm=pm)
    
    # Mock ItemAgent.craft
    mock_agent_response = {
        "success": True,
        "reasoning": "Sự kết hợp hợp lý giữa sắt và gỗ để rèn búa sắt.",
        "new_item": {
            "name": "Búa sắt",
            "description": "Búa đập nặng",
            "type": "weapon",
            "base_damage": 15,
            "modifiers": {"strength": 3},
            "status_effect": None,
            "proc_chance": 0.0
        },
        "lost_items": ["Sắt vụn", "Gỗ vụn"]
    }
    processor.item_agent.craft = AsyncMock(return_value=mock_agent_response)
    
    # Chạy thử nghiệm chế tạo
    result = await processor.craft(item_list=[iron, wood], action_details="Rèn búa sắt từ sắt và gỗ")
    
    # Xác thực kết quả
    assert "CHẾ TẠO THÀNH CÔNG" in result
    assert "Búa sắt" in result
    
    # Nguyên liệu bị mất
    assert iron not in player_state.get_all_items()
    assert wood not in player_state.get_all_items()
    
    # Vật phẩm mới được thêm vào
    equipped_weapon = player_state.get_item_by_name("Búa sắt")
    assert equipped_weapon is not None
    assert isinstance(equipped_weapon, WeaponItem)
    assert equipped_weapon.base_damage == 15

@pytest.mark.asyncio
async def test_item_processor_craft_failure_with_material_loss():
    player_state = PlayerState(name="TestHero")
    pm = PromptManager('./static/prompts.yaml')
    
    iron = MiscellaneousItem(id=1, name="Sắt vụn", description="Mảnh sắt gỉ sét")
    player_state.add_item(iron)
    
    processor = ItemProcessor(player_state=player_state, provider="gemini", local_api_key="dummy", pm=pm)
    
    # Mock ItemAgent.craft thất bại nhưng làm mất nguyên liệu
    mock_agent_response = {
        "success": False,
        "reasoning": "Lửa quá nóng làm chảy sắt vụn thành tro.",
        "lost_items": ["Sắt vụn"]
    }
    processor.item_agent.craft = AsyncMock(return_value=mock_agent_response)
    
    result = await processor.craft(item_list=[iron], action_details="Cố nung sắt vụn dưới ngọn lửa dung nham")
    
    assert "CHẾ TẠO THẤT BẠI" in result
    assert "làm hỏng/mất Sắt vụn" in result
    assert iron not in player_state.get_all_items()

@pytest.mark.asyncio
async def test_item_processor_use_success():
    player_state = PlayerState(name="TestHero")
    pm = PromptManager('./static/prompts.yaml')
    
    potion = ConsumableItem(id=1, name="Thuốc giải độc", description="Giải các loại độc tính", effect={"hp": 10})
    player_state.add_item(potion)
    
    processor = ItemProcessor(player_state=player_state, provider="gemini", local_api_key="dummy", pm=pm)
    
    mock_agent_response = {
        "success": True,
        "reasoning": "Thuốc giải độc phát huy tác dụng trung hòa chất độc.",
        "lost_items": ["Thuốc giải độc"]
    }
    processor.item_agent.use = AsyncMock(return_value=mock_agent_response)
    
    success, msg = await processor.use(item_list=[potion], action_details="Uống thuốc giải độc", context="Người chơi đang bị trúng độc")
    
    assert success is True
    assert "thành công" in msg
    assert potion not in player_state.get_all_items()
