import pytest
from engine.Utils.Headroom import HeadroomOptimizer

def test_headroom_compression():
    """Kiểm thử tính năng nén ngữ cảnh của HeadroomOptimizer"""
    optimizer = HeadroomOptimizer(enabled=True)
    
    raw_context = (
        "[BỐI CẢNH HIỆN TẠI]\n"
        "- Địa điểm: Thư viện Cổ - Nơi chứa nhiều sách cổ\n"
        "- Quá khứ gần: player đang đọc sách cổ\n"
        "- Player đang làm: Nghiên cứu lời nguyền\n\n"
        "[LỊCH SỬ CÁ NHÂN VỚI NPC]\n"
        "Lịch sử với Eldrin:\n"
        "- Turn 1: Eldrin kể câu chuyện về Rồng thiêng\n\n"
        "[CÁC KÝ ỨC MÔI TRƯỜNG KHÁC (TỪ FAISS)]\n"
        "- (Turn 1 tại Thư viện Cổ): Có một chiếc chìa khóa vàng rơi dưới gầm bàn"
    )
    
    compressed = optimizer.compress_rag_context(raw_context)
    
    # Kiểm tra xem các header đã được chuyển đổi viết tắt chưa
    assert "[CURR_CTX]" in compressed
    assert "@Loc:" in compressed
    assert "Past:" in compressed
    assert "Act:" in compressed
    assert "[NPC_HIST]" in compressed
    assert "w/ Eldrin:" in compressed
    assert "[FAISS_MEM]" in compressed
    assert "- T1 @ Thư viện Cổ:" in compressed
    
    # Kiểm tra các từ thay thế ngắn gọn
    assert "player" in compressed
    
    # Kiểm tra xem có giảm kích thước không
    assert len(compressed) < len(raw_context)

def test_headroom_ccr_cache():
    """Kiểm thử tính năng Compress-Cache-Retrieve (CCR)"""
    optimizer = HeadroomOptimizer(enabled=True)
    
    original_text = "Đây là thông tin ký ức cực kỳ bí mật và chi tiết về kho báu."
    ref_id = optimizer.register_in_ccr(original_text)
    
    assert ref_id.startswith("ref_")
    
    # Lấy lại dữ liệu gốc từ cache
    retrieved = optimizer.retrieve_original(ref_id)
    assert retrieved == original_text
    
    # Truy xuất id không tồn tại
    assert optimizer.retrieve_original("ref_999") == "[Không tìm thấy dữ liệu gốc]"

def test_headroom_disabled():
    """Kiểm thử trường hợp tắt Headroom (enabled = False)"""
    optimizer = HeadroomOptimizer(enabled=False)
    
    raw_context = "[BỐI CẢNH HIỆN TẠI]\n- Địa điểm: Thư viện Cổ"
    compressed = optimizer.compress_rag_context(raw_context)
    
    # Nếu disabled, context phải giữ nguyên 100%
    assert compressed == raw_context

def test_headroom_statistics():
    """Kiểm thử thống kê lượng token/character tiết kiệm được"""
    optimizer = HeadroomOptimizer(enabled=True)
    
    raw_context = "[BỐI CẢNH HIỆN TẠI]\n- Địa điểm: Thư viện Cổ - Nơi chứa nhiều sách cổ"
    compressed = optimizer.compress_rag_context(raw_context)
    
    stats = optimizer.get_stats()
    assert stats["raw_chars"] == len(raw_context)
    assert stats["compressed_chars"] == len(compressed)
    assert stats["char_savings"] == len(raw_context) - len(compressed)
    assert stats["saving_percent"] > 0
    assert stats["est_token_savings"] >= 0
