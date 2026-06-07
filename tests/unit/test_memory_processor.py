import pytest
from unittest.mock import MagicMock
from engine.Subengine.MemoryProcessor import MemoryProcessor
from world.Entity import Memory
from engine.Utils.PromptManager import PromptManager

def test_rerank_memories_time_decay_and_bonuses():
    """
    Kiểm thử thuật toán Reranking trong MemoryProcessor.
    Thuật toán sử dụng điểm FAISS gốc kết hợp với:
    - Time Decay (Hàm mũ giảm dần theo số lượt chơi trôi qua).
    - Location Bonus (+20% cho địa điểm trùng khớp).
    - Keyword Bonus (+15% cho mỗi từ khóa trùng khớp).
    """
    # 1. Khởi tạo Mock các Dependency
    db = MagicMock()
    pm = PromptManager('./static/prompts.yaml')
    
    mp = MemoryProcessor(db=db, vector_model_path="dummy_path", groq_api_key="dummy_key", pm=pm)
    
    # 2. Tạo tập dữ liệu ký ức giả lập
    # mem1: Lượt 1, Đại sảnh Eldoria, không có từ khóa đặc biệt
    mem1 = Memory(location="Eldoria Great Hall", text="Gặp Joseph nói chuyện xã giao", game_turn=1)
    
    # mem2: Lượt 2, Rừng sương mù, chứa từ khóa chiến đấu, sói xám
    mem2 = Memory(location="Foggy Forest", text="Chiến đấu với sói xám hung dữ", game_turn=2)
    
    # mem3: Lượt 3, Đại sảnh Eldoria, chứa từ khóa Joseph, Rồng thiêng
    mem3 = Memory(location="Eldoria Great Hall", text="Joseph kể chuyện về Rồng thiêng Eldoria", game_turn=3)
    
    memories = [mem1, mem2, mem3]
    faiss_scores = [0.8, 0.8, 0.8]  # Đặt điểm FAISS cơ sở bằng nhau để xem xét rõ sự sai lệch khi Rerank
    
    # --- KỊCH BẢN 1: Chỉ xét Time Decay (current_turn = 4, không vị trí, không từ khóa) ---
    # Kết quả mong muốn: Ký ức mới nhất (mem3) có điểm cao nhất, ký ức cũ nhất (mem1) thấp nhất.
    reranked_time = mp._rerank_memories(
        memories=memories,
        faiss_scores=faiss_scores,
        current_turn=4,
        time_decay_rate=0.05
    )
    assert reranked_time[0] == mem3  # Turn 3 (mới nhất)
    assert reranked_time[1] == mem2  # Turn 2
    assert reranked_time[2] == mem1  # Turn 1 (cũ nhất)

    # --- KỊCH BẢN 2: Cộng điểm địa điểm trùng khớp (đang đứng ở Eldoria Great Hall) ---
    # Ký ức mem1 và mem3 có địa điểm khớp, được nhân hệ số thưởng 1.20 (tức +20%).
    # mem2 ở Foggy Forest không được cộng điểm địa điểm.
    reranked_loc = mp._rerank_memories(
        memories=memories,
        faiss_scores=faiss_scores,
        current_turn=3,
        current_location="Eldoria Great Hall",
        time_decay_rate=0.05
    )
    # mem3 (mới + khớp địa điểm) -> Xếp thứ 1
    # mem1 (cũ hơn nhưng khớp địa điểm) -> Xếp thứ 2
    # mem2 (mới hơn mem1 nhưng không khớp địa điểm) -> Bị tụt xuống thứ 3
    assert reranked_loc[0] == mem3
    assert reranked_loc[1] == mem1
    assert reranked_loc[2] == mem2

    # --- KỊCH BẢN 3: Cộng điểm từ khóa khớp (Keywords = ["sói", "xám"]) ---
    # mem2 chứa từ "sói" và "xám" trong văn bản, nhận được nhân hệ số thưởng (1.0 + 0.15 * 2 = 1.30, tức +30%).
    # Mặc dù mem2 cũ hơn mem3, điểm thưởng từ khóa sẽ kéo mem2 vọt lên đầu.
    reranked_kw = mp._rerank_memories(
        memories=memories,
        faiss_scores=faiss_scores,
        current_turn=3,
        keywords=["sói", "xám"],
        time_decay_rate=0.05
    )
    assert reranked_kw[0] == mem2  # mem2 vọt lên đứng đầu
    assert reranked_kw[1] == mem3  # mem3 không có từ khóa nhưng mới hơn mem1
    assert reranked_kw[2] == mem1  # mem1 cũ nhất
