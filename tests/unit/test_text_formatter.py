import pytest
from engine.Utils.TextFormatter import TextFormatter

def test_parse_story_with_tags():
    # Câu truyện có đầy đủ tag [NPC_TALK] và [PLAYER_TALK] xen kẽ narration
    text = (
        "Bóng đêm buông xuống khu rừng.\n"
        "[NPC_TALK: Elara]Hãy đi lối này![/NPC_TALK]\n"
        "Elara chỉ tay về phía đông.\n"
        "[PLAYER_TALK]Tôi hiểu rồi.[/PLAYER_TALK]"
    )
    
    segments = TextFormatter.parse_story_into_segments(text)
    
    assert len(segments) == 4
    
    # Đoạn Master kể
    assert segments[0]["speaker"] == "Master"
    assert segments[0]["text"] == "Bóng đêm buông xuống khu rừng."
    
    # NPC nói
    assert segments[1]["speaker"] == "Elara"
    assert segments[1]["text"] == '"Hãy đi lối này!"'
    
    # Master dẫn chuyện tiếp
    assert segments[2]["speaker"] == "Master"
    assert segments[2]["text"] == "Elara chỉ tay về phía đông."
    
    # Người chơi nói
    assert segments[3]["speaker"] == "Player"
    assert segments[3]["text"] == '"Tôi hiểu rồi."'

def test_parse_story_with_npc_talk_no_name():
    # Tag [NPC_TALK] không kèm tên cụ thể
    text = "[NPC_TALK]Chào người lạ mặt.[/NPC_TALK]"
    segments = TextFormatter.parse_story_into_segments(text)
    
    assert len(segments) == 1
    assert segments[0]["speaker"] == "NPC"
    assert segments[0]["text"] == '"Chào người lạ mặt."'

def test_parse_story_fallback_with_quotes():
    # Không có tag, hệ thống tự động bóc tách dựa trên ngoặc kép (fallback)
    text = (
        "Elara nhìn tôi trìu mến.\n"
        "\"Hãy cẩn thận trên đường đi!\"\n"
        "Cô ấy đưa cho tôi một bình thuốc phục hồi."
    )
    
    segments = TextFormatter.parse_story_into_segments(text)
    
    assert len(segments) == 3
    assert segments[0]["speaker"] == "Master"
    assert segments[0]["text"] == "Elara nhìn tôi trìu mến."
    
    # Bóc hội thoại trong ngoặc kép thành NPC
    assert segments[1]["speaker"] == "NPC"
    assert segments[1]["text"] == '"Hãy cẩn thận trên đường đi!"'
    
    assert segments[2]["speaker"] == "Master"
    assert segments[2]["text"] == "Cô ấy đưa cho tôi một bình thuốc phục hồi."

def test_parse_story_pure_narration():
    # Chỉ chứa lời kể của Master, không có tag lẫn hội thoại
    text = "Vương quốc Eldoria từng là một nơi phồn thịnh.\nNhưng giờ đây chỉ còn đống đổ nát."
    segments = TextFormatter.parse_story_into_segments(text)
    
    assert len(segments) == 2
    assert segments[0]["speaker"] == "Master"
    assert segments[0]["text"] == "Vương quốc Eldoria từng là một nơi phồn thịnh."
    assert segments[1]["speaker"] == "Master"
    assert segments[1]["text"] == "Nhưng giờ đây chỉ còn đống đổ nát."

def test_parse_story_empty_text():
    # Chuỗi rỗng
    segments = TextFormatter.parse_story_into_segments("")
    assert segments == []
