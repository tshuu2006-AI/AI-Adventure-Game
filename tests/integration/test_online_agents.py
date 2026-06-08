import pytest
import os
from engine.Utils.PromptManager import PromptManager
from engine.Agents.LocalAgents import IntentRouter, MusicClassifier
from engine.Agents.CloudAgents import ChoiceAgent, QueryAgent
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
    agent = ChoiceAgent(api_key=api_key, pm=pm, model_name="llama-3.3-70b-versatile")
    
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

@pytest.mark.skipif(TEST_MODE != "online", reason="Chỉ chạy khi TEST_MODE=online và có API key thật")
@pytest.mark.asyncio
async def test_online_music_classifier_gemini():
    """Kiểm thử trực tiếp MusicClassifier với Gemini API thật"""
    api_key = os.environ.get("GEMINI_API_KEY")
    assert api_key is not None, "Thiếu GEMINI_API_KEY trong file .env"
    
    pm = PromptManager('./static/prompts.yaml')
    classifier = MusicClassifier(pm=pm, gemini_api_key=api_key)
    
    # Phân tích một bối cảnh đáng sợ
    result = await classifier.classify_emotion("Bóng tối bao trùm lấy ngóc ngách lâu đài, tiếng bước chân kẽo kẹt sau lưng và tiếng sói hú vang vọng.")
    assert result in ["bình thường", "căng thẳng", "buồn", "vui", "sợ hãi"]
    print(f"\n[Online Gemini] Phản hồi Cảm xúc Nhạc nền: {result}")

@pytest.mark.skipif(TEST_MODE != "online", reason="Chỉ chạy khi TEST_MODE=online và có API key thật")
@pytest.mark.asyncio
async def test_online_query_agent_groq():
    """Kiểm thử trực tiếp QueryAgent với Groq API thật"""
    api_key = os.environ.get("GROQ_API_KEY")
    assert api_key is not None, "Thiếu GROQ_API_KEY trong file .env"
    
    pm = PromptManager('./static/prompts.yaml')
    agent = QueryAgent(api_key=api_key, pm=pm, model_name="llama-3.3-70b-versatile")
    
    result = await agent.generate_query(
        current_location="Rừng sâu",
        npc_names=["Elara"],
        context="Người chơi đang đi tìm kiếm thảo dược quý để trị thương."
    )
    assert isinstance(result, str)
    assert len(result) > 0
    print(f"\n[Online Groq] Phản hồi Query: {result}")

