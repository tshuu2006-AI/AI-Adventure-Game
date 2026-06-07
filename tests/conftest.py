import pytest
import os
import sys
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
import numpy as np
from dotenv import load_dotenv

# Nạp file .env từ thư mục gốc
load_dotenv()

TEST_MODE = os.environ.get("TEST_MODE", "offline").lower()

# Mock SentenceTransformer ngay lập tức tại thời điểm import để tránh tải model thực khi import server.py
mock_encoder = MagicMock()
mock_encoder.get_sentence_embedding_dimension.return_value = 128
mock_encoder.get_embedding_dimension.return_value = 128
mock_encoder.encode.side_effect = lambda sentences, **kwargs: np.random.randn(len(sentences), 128).astype('float32')

sentence_transformer_patcher = patch('sentence_transformers.SentenceTransformer', return_value=mock_encoder)
sentence_transformer_patcher.start()

# Thêm đường dẫn gốc của dự án vào sys.path để các module test import trực tiếp được
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Thiết lập API keys giả lập chỉ khi chạy ở chế độ offline và chưa có key thật
if TEST_MODE == "offline":
    os.environ["GROQ_API_KEY"] = "DUMMY_GROQ_API_KEY"
    os.environ["GEMINI_API_KEY"] = "DUMMY_GEMINI_API_KEY"

@pytest.fixture(scope="session")
def event_loop():
    """Tạo event loop dùng chung cho các test bất đồng bộ (async tests)"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest.fixture(autouse=True)
def mock_external_apis():
    """Mock các kết nối API ngoài tùy thuộc vào chế độ TEST_MODE (offline/online)"""
    patchers = [
        patch('engine.DataManager.ImageManager.ImageManager.get_or_create_location_image', new_callable=AsyncMock, return_value="static/default_location.png"),
        patch('engine.DataManager.ImageManager.ImageManager.get_or_create_npc_image', new_callable=AsyncMock, return_value="static/default_npc.png"),
        patch('engine.DataManager.MemoryManager.SentenceTransformer', return_value=mock_encoder)
    ]
    
    if TEST_MODE == "offline":
        # Ở chế độ offline, mock thêm các API của LLM Groq và Gemini
        patchers.extend([
            patch('engine.Agents.CloudAgents.BaseCloudAgent._chat', new_callable=AsyncMock),
            patch('engine.Agents.CloudAgents.BaseCloudAgent._generate_json_with_retry', new_callable=AsyncMock, return_value={}),
            patch('engine.Agents.LocalAgents.BaseLocalAgent._generate_json', new_callable=AsyncMock, return_value={})
        ])
        
    # Kích hoạt tất cả patchers
    for p in patchers:
        p.start()
        
    yield
    
    # Dừng tất cả patchers khi hoàn tất test
    for p in patchers:
        try:
            p.stop()
        except RuntimeError:
            pass

@pytest.fixture
def test_db_paths(tmp_path):
    """Fixture cung cấp thư mục và đường dẫn DB SQLite tạm thời cho test"""
    db_folder = tmp_path / "data_test"
    db_folder.mkdir(parents=True, exist_ok=True)
    db_path = db_folder / "WorldTest.db"
    return str(db_path), str(db_folder)
