import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, AsyncMock, patch
from server import app
from world.Entity import Location, NPC, Quest, WeaponItem

client = TestClient(app)

@pytest.fixture
def mock_orchestrator():
    """Fixture để thay thế app.state.orchestrator bằng một Mock object cô lập"""
    orc = MagicMock()
    
    # Cấu hình các phương thức đồng bộ trả về dữ liệu giả lập
    orc.get_current_location.return_value = Location(1, "Thị trấn sương mù", "Thị trấn nhỏ đầy sương", "U ám")
    orc.get_current_npcs.return_value = [
        NPC(1, "Lão rèn", "Cộc cằn", "Thợ rèn giỏi nhất vùng", 15, "Thị trấn sương mù", "Bình thường")
    ]
    orc.get_all_items.return_value = []
    orc.get_item_by_name.return_value = None
    orc.get_current_hp.return_value = 85
    orc.get_max_hp.return_value = 100
    orc.get_equipped_weapon.return_value = WeaponItem(1, "Búa rèn", "Búa sắt nặng", base_damage=15)
    orc.player_state.stats.total_stats = {"strength": 12, "agility": 8, "defense": 10, "intelligence": 5}
    orc.player_state.active_quest = Quest(1, "Rèn kiếm thần", "Tìm sắt nguội", ["Tìm sắt"], "Lão rèn", [])
    orc.player_state.quest_items = []
    orc.get_active_quest.return_value = orc.player_state.active_quest
    orc.get_all_quests.return_value = [orc.player_state.active_quest]
    orc.current_emotion = "bình thường"
    orc.is_processing_bg = False
    
    # Cấu hình các phương thức async trả về dữ liệu giả lập
    orc.get_all_npcs = AsyncMock(return_value=orc.get_current_npcs())
    orc.get_all_locations = AsyncMock(return_value=[orc.get_current_location()])
    orc.switch_quest = AsyncMock(return_value="Đã chuyển sang nhiệm vụ mới.")
    
    # Hoán đổi orchestrator thật bằng mock
    old_orc = getattr(app.state, 'orchestrator', None)
    app.state.orchestrator = orc
    yield orc
    if old_orc:
        app.state.orchestrator = old_orc

def test_ping_endpoint():
    response = client.get("/api/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "message": "Server is ready"}

@patch("server.verify_groq_key", new_callable=AsyncMock)
@patch("server.verify_gemini_key", new_callable=AsyncMock)
def test_check_config_endpoint_success(mock_verify_gemini, mock_verify_groq):
    mock_verify_groq.return_value = True
    mock_verify_gemini.return_value = True

    response = client.post(
        "/api/check_config",
        data={
            "cloud_key": "valid_groq_key",
            "local_model_or_key": "valid_gemini_key",
            "is_ollama": "false"
        }
    )
    
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert "sẵn sàng sử dụng" in response.json()["message"]

@patch("server.verify_groq_key", new_callable=AsyncMock)
def test_check_config_endpoint_failure(mock_verify_groq):
    mock_verify_groq.return_value = False

    response = client.post(
        "/api/check_config",
        data={
            "cloud_key": "invalid_key",
            "local_model_or_key": "some_key",
            "is_ollama": "false"
        }
    )
    
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Groq" in response.json()["message"]

def test_poll_updates_endpoint(mock_orchestrator):
    response = client.get("/api/poll_updates")
    assert response.status_code == 200
    
    data = response.json()
    assert data["hp"] == 85
    assert data["max_hp"] == 100
    assert data["weapon"] == "Búa rèn"
    assert data["strength"] == 12
    assert data["active_quest"]["name"] == "Rèn kiếm thần"

def test_diary_endpoint(mock_orchestrator):
    response = client.get("/api/diary")
    assert response.status_code == 200
    
    data = response.json()
    assert "npcs" in data
    assert "locations" in data
    assert "quests" in data
    
    assert len(data["npcs"]) == 1
    assert data["npcs"][0]["name"] == "Lão rèn"
    assert data["locations"][0]["name"] == "Thị trấn sương mù"
    assert data["quests"][0]["name"] == "Rèn kiếm thần"

def test_inventory_equip_endpoint_not_found(mock_orchestrator):
    # Trả về None khi không tìm thấy vật phẩm
    mock_orchestrator.get_item_by_name.return_value = None
    
    response = client.post("/api/inventory/equip", data={"items_str": "Kiếm rỉ"})
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Không thể trang bị" in response.json()["message"]
