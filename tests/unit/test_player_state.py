import pytest
from unittest.mock import MagicMock, AsyncMock
from engine.DataManager.PlayerState import PlayerState
from world.Entity import WeaponItem, ConsumableItem, Location, NPC, Quest

def test_player_state_initialization():
    state = PlayerState(name="Hero")
    assert state.name == "Hero"
    assert state.currentLocation is None
    assert state.currentTurn == 0
    assert state.currentNPCs == []
    assert state.is_dead() is False
    assert state.stats.current_hp == 100 # Giả định HP khởi điểm

def test_player_state_clear():
    state = PlayerState()
    loc = Location(1, "Rừng sâu", "Mô tả", "U ám")
    npc = NPC(1, "Elara", "Tốt", "Mô tả", 10, "Rừng sâu", "Bình thường")
    
    state.set_location(loc)
    state.add_npc(npc)
    state.currentTurn = 5
    
    # Thực hiện clear
    state.clear()
    assert state.currentLocation is None
    assert state.currentNPCs == []
    assert state.currentTurn == 0

def test_player_take_damage_and_die():
    state = PlayerState()
    assert state.is_dead() is False
    
    # Nhận sát thương: thô 50, thực tế = 50 - 0.5 * defense(5) = 47.5 -> round(100 - 47.5) = 52
    state.take_damage(50)
    assert state.stats.current_hp == 52
    assert state.is_dead() is False
    
    # Nhận thêm sát thương chết người: thô 60 -> thực tế = 57.5 -> HP = 0
    state.take_damage(60)
    assert state.stats.current_hp <= 0
    assert state.is_dead() is True

def test_equip_and_change_weapon():
    state = PlayerState()
    
    # Khởi tạo vũ khí có modifier sức mạnh +5
    sword = WeaponItem(id=1, name="Kiếm sắt", description="Kiếm rèn thô", base_damage=10, modifiers={"strength": 5})
    
    # Trang bị vũ khí (Base strength 10 + bonus 5 = 15)
    state.equip_weapon(sword)
    assert state.get_equipped_weapon() == sword
    assert state.stats.total_stats["strength"] == 15

    # Đổi sang vũ khí khác mạnh hơn (Base strength 10 + bonus 15 = 25)
    gold_sword = WeaponItem(id=2, name="Kiếm vàng", description="Kiếm quý", base_damage=20, modifiers={"strength": 15})
    state.change_weapon(gold_sword)
    assert state.get_equipped_weapon() == gold_sword
    # Đảm bảo modifier cũ bị gỡ bỏ và modifier mới được áp dụng
    assert state.stats.total_stats["strength"] == 25

    # Thử tháo vũ khí (unequip)
    state.unequip_weapon()
    assert state.get_equipped_weapon() is None
    assert state.stats.total_stats["strength"] == 10

def test_use_consumables():
    state = PlayerState()
    # Nhận sát thương thô 30 -> thực tế = 30 * 100/105 = 28.57 -> HP = round(100 - 28.57) = 71
    state.take_damage(30) 
    
    # Bình máu hồi 20 HP
    potion = ConsumableItem(id=1, name="Bình máu nhỏ", description="Hồi 20 HP", effect={"hp": 20})
    
    # Add vào túi đồ trước khi dùng
    state.add_item(potion)
    assert potion in state.get_all_items()
    
    # Sử dụng (71 + 20 = 91 HP)
    state.use_consumables(potion)
    assert state.stats.current_hp == 91
    # Đã dùng xong thì phải bị loại bỏ khỏi túi đồ
    assert potion not in state.get_all_items()

def test_quest_management():
    state = PlayerState()
    main_quest = Quest(id=1, name="Main Quest", description="Mô tả", objectives=["Mục tiêu 1"], give_by="N/A", rewards=[])
    side_quest = Quest(id=2, name="Side Quest", description="Mô tả", objectives=["Mục tiêu 2"], give_by="NPC", rewards=[])
    
    state.set_main_quest(main_quest)
    state.add_quest(main_quest)
    state.add_quest(side_quest)
    
    assert state.active_quest == main_quest
    assert state.main_quest == main_quest
    assert len(state.get_all_quests()) == 2

def test_serialize_to_dict():
    state = PlayerState(name="Arthur")
    loc = Location(1, "Làng", "Bình yên", "ấm áp")
    state.set_location(loc)
    
    data = state.to_dict()
    assert data["current_location_name"] == "Làng"
    assert "inventory_data" in data
    assert "quests" in data
    assert "stats_data" in data

@pytest.mark.asyncio
async def test_deserialize_load_state():
    state = PlayerState()
    
    # Tạo mock cho db_manager và image_manager
    mock_db = MagicMock()
    mock_db.location_manager.get_all = AsyncMock(return_value=[
        Location(1, "Thành cổ", "Mô tả", "U ám")
    ])
    mock_db.npc_manager.get_all = AsyncMock(return_value=[
        NPC(1, "Arthur", "Mô tả", "Hiệp sĩ", 10, "Thành cổ", "Bình thường")
    ])
    
    mock_image = MagicMock()

    data = {
        "current_turn": 3,
        "current_location_name": "Thành cổ",
        "current_npc_names": ["Arthur"],
        "inventory_data": {
            "weapon_inventory": [],
            "consumable_inventory": [],
            "quest_inventory": [],
            "miscellaneous_inventory": [],
            "equipped_weapon": None
        },
        "quests": [
            {
                "id": 1,
                "name": "Tìm chìa khóa",
                "description": "...",
                "objectives": ["Tìm kiếm"],
                "is_finished": [0],
                "give_by": "Arthur",
                "rewards": [],
                "status": "in_progress",
                "snapshot": {
                    "location_name": "Thành cổ",
                    "npc_names": ["Arthur"],
                    "last_story": "...",
                    "last_choices": []
                }
            }
        ],
        "active_quest_id": 1,
        "main_quest_id": 1,
        "stats_data": {
            "max_hp": 100,
            "current_hp": 85,
            "base_stats": {},
            "equipment_modifiers": {}
        }
    }
    
    await state.load_state(data, mock_db, mock_image)
    
    assert state.currentTurn == 3
    assert state.currentLocation.name == "Thành cổ"
    assert len(state.currentNPCs) == 1
    assert state.currentNPCs[0].name == "Arthur"
    assert state.stats.current_hp == 85
    assert len(state.quests) == 1
    assert state.active_quest.name == "Tìm chìa khóa"
