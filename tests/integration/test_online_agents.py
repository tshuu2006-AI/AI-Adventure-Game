import pytest
import os
from engine.Utils.PromptManager import PromptManager
from engine.Agents.LocalAgents import IntentRouter
from engine.Agents.CloudAgents import ChoiceAgent
from world.Entity import Quest, WeaponItem

# Lấy cấu hình TEST_MODE từ conftest.py (hoặc biến môi trường trực tiếp)
TEST_MODE = os.environ.get("TEST_MODE", "offline").lower()

@pytest.mark.skipif(TEST_MODE != "online", reason="Chỉ chạy khi TEST_MODE=online và có API key thật")
@pytest.mark.asyncio
async def test_online_intent_router_gemini():
    """Kiểm thử trực tiếp IntentRouter với Google Gemini API thật"""
    api_key = os.environ.get("GEMINI_API_KEY")
    assert api_key is not None, "Thiếu GEMINI_API_KEY trong file .env"
    assert api_key != "DUMMY_GEMINI_API_KEY", "GEMINI_API_KEY đang bị gán key ảo"

    pm = PromptManager('./static/prompts.yaml')
    router = IntentRouter(pm=pm, gemini_api_key=api_key)
    
    # Gửi câu lệnh hành động thực tế của người chơi
    player_input = "Tôi muốn mở chiếc hòm gỗ cổ xưa kia"
    result = await router.parse_intent(player_input)
    
    # Xác thực cấu trúc dữ liệu JSON phản hồi từ Gemini
    assert isinstance(result, dict)
    assert "intent" in result
    assert "target" in result
    assert "action_details" in result
    print(f"\n[Online Gemini] Phản hồi Intent: {result}")

@pytest.mark.skipif(TEST_MODE != "online", reason="Chỉ chạy khi TEST_MODE=online và có API key thật")
@pytest.mark.asyncio
async def test_online_choice_agent_groq():
    """Kiểm thử trực tiếp ChoiceAgent với Groq API thật"""
    api_key = os.environ.get("GROQ_API_KEY")
    assert api_key is not None, "Thiếu GROQ_API_KEY trong file .env"
    assert api_key != "DUMMY_GROQ_API_KEY", "GROQ_API_KEY đang bị gán key ảo"

    pm = PromptManager('./static/prompts.yaml')
    agent = ChoiceAgent(api_key=api_key, pm=pm, model_name="llama3-8b-8192")
    
    # Giả lập bối cảnh game để tạo menu lựa chọn
    result = await agent.generate_choices(
        current_location="Lâu đài hoang",
        npc_name="Elara",
        recent_story_summary="Elara đưa cho bạn một chiếc chìa khóa cổ và bảo bạn mở cánh cửa bí mật.",
        active_quest_context="Nhiệm vụ chính: Tìm lối thoát khỏi lâu đài.",
        quest_items="Chìa khóa cổ"
    )
    
    # Xác thực cấu trúc dữ liệu JSON phản hồi từ Groq (Llama-3)
    assert isinstance(result, dict)
    assert "choices" in result
    assert len(result["choices"]) > 0
    
    choice = result["choices"][0]
    assert "id" in choice
    assert "action_text" in choice
    assert "style" in choice
    print(f"\n[Online Groq] Phản hồi Choices: {result}")
