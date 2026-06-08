# BÁO CÁO CÔNG NGHỆ VÀ THƯ VIỆN KIỂM THỬ (TEST TECHNICAL REPORT)

Tài liệu này cung cấp danh sách đầy đủ, chi tiết và mô tả vai trò của tất cả các công nghệ, thư viện, công cụ và phương pháp đã được sử dụng để xây dựng và thực thi hệ thống kiểm thử (Unit Test & Integration Test) cho dự án **AI Story Adventure**.

---

## 1. KHUNG KIỂM THỬ CHÍNH (CORE TESTING FRAMEWORK)

### 🧪 Pytest
* **Thư viện:** `pytest`
* **Vai trò:** Là khung kiểm thử chính (Test Runner & Framework) điều phối toàn bộ vòng đời kiểm thử của dự án.
* **Mô tả chi tiết:**
  * **Tự động phát hiện (Test Discovery):** Tự động tìm kiếm các tệp tin có tiền tố `test_*.py` trong thư mục `tests/` để đưa vào danh sách thực thi.
  * **Cơ chế Fixture mạnh mẽ:** Sử dụng các Fixture (như `event_loop`, `mock_external_apis`, `test_db_paths`, `mock_orchestrator`) để thiết lập (setup) và dọn dẹp (teardown) môi trường trước và sau mỗi ca kiểm thử.
  * **Hỗ trợ Asyncio:** Kết hợp với thư viện lập trình bất đồng bộ để chạy các ca kiểm thử liên quan đến các hàm `async/await`.

---

## 2. GIẢ LẬP VÀ CÔ LẬP HỆ THỐNG (MOCKING & ISOLATION)

Để đảm bảo các bài kiểm thử chạy nhanh, ổn định và không phụ thuộc vào kết nối mạng bên ngoài hoặc làm thay đổi cơ sở dữ liệu thực tế, các thư viện giả lập đã được áp dụng triệt để:

### 🧩 Unittest.mock (Thư viện chuẩn của Python)
* **Thư viện:** `unittest.mock` (bao gồm `MagicMock`, `AsyncMock`, và `patch`)
* **Vai trò:** Giả lập hành vi của các module phức tạp, các API đám mây (Groq, Gemini), và các lớp xử lý AI.
* **Mô tả chi tiết:**
  * **`MagicMock`**: Tạo ra các đối tượng giả lập để thay thế cho các thực thể cơ sở dữ liệu hoặc cấu trúc dữ liệu phức tạp, trả về các giá trị cấu hình sẵn mà không cần chạy logic thực tế.
  * **`AsyncMock`**: Đặc biệt quan trọng để giả lập các hàm bất đồng bộ (Coroutines). Được dùng để mock các phương thức gọi API ngoài như `BaseCloudAgent._chat` và các thao tác ghi cơ sở dữ liệu bất đồng bộ.
  * **`patch`**: Trình trang trí (Decorator) dùng để ghi đè (patch) tạm thời các module ngay khi chúng được import. Ví dụ:
    * Patch `SentenceTransformer` để tránh việc tải mô hình nhúng thực tế (128 chiều) về máy khi chạy test, giúp tiết kiệm băng thông và tăng tốc độ chạy test lên hàng chục lần.
    * Patch các phương thức xác thực API keys của Groq và Gemini trong `server.py` để kiểm tra luồng cấu hình backend.

---

## 3. KIỂM THỬ TÍCH HỢP GIAO DIỆN LẬP TRÌNH (API TESTING)

### ⚡ FastAPI TestClient
* **Thư viện:** `fastapi.testclient.TestClient`
* **Vai trò:** Kiểm thử tích hợp các cổng kết nối API (Endpoints) của máy chủ FastAPI mà không cần chạy máy chủ thực tế trên cổng mạng.
* **Mô tả chi tiết:**
  * Khởi tạo một client HTTP giả lập kết nối trực tiếp đến đối tượng `app` trong [server.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/server.py).
  * Gửi các truy vấn giả lập (GET, POST) kèm theo dữ liệu form hoặc JSON và nhận lại phản hồi đầy đủ (HTTP Status Code, Headers, JSON Body).
  * Được sử dụng để kiểm tra các API chính:
    * `/api/ping`: Kiểm tra trạng thái máy chủ.
    * `/api/check_config`: Kiểm tra tính hợp lệ của cấu hình khóa tác nhân.
    * `/api/poll_updates`: Lấy thông tin trạng thái người chơi thời gian thực (HP, chỉ số, nhiệm vụ hiện tại).
    * `/api/diary`: Lấy lịch sử hành trình (danh sách NPC đã gặp, địa điểm đã đi qua, nhiệm vụ).
    * `/api/inventory/equip`: Kiểm tra logic trang bị vật phẩm của nhân vật.

---

## 4. DỮ LIỆU VÀ CÁC THƯ VIỆN HỖ TRỢ (DATA & UTILITIES)

### 🧮 NumPy
* **Thư viện:** `numpy`
* **Vai trò:** Tạo lập dữ liệu ma trận/mảng số thực giả lập cho các vectơ đặc trưng (embeddings).
* **Mô tả chi tiết:**
  * Dùng `np.random.randn(len(sentences), 128).astype('float32')` để sinh ra các vectơ nhúng giả lập có kích thước 128 chiều.
  * Giúp kiểm tra thuật toán tìm kiếm và xếp hạng ký ức (Memory Retrieval Score) hoạt động chính xác dựa trên độ tương đồng và hệ số suy giảm thời gian.

### 🔑 Python-dotenv
* **Thư viện:** `python-dotenv` (import dưới dạng `dotenv`)
* **Vai trò:** Nạp các cấu hình môi trường từ tệp `.env`.
* **Mô tả chi tiết:**
  * Sử dụng phương thức `load_dotenv()` để đọc các biến cấu hình từ môi trường.
  * Cho phép chuyển đổi linh hoạt giữa chế độ kiểm thử ngoại tuyến (`TEST_MODE=offline` - sử dụng mock API và API keys giả lập) và kiểm thử trực tuyến (`TEST_MODE=online` - thực hiện kết nối và gọi API thực đến Groq/Gemini).

### 🔄 Asyncio
* **Thư viện:** `asyncio` (Thư viện chuẩn của Python)
* **Vai trò:** Quản lý vòng lặp sự kiện (Event Loop) cho các luồng xử lý bất đồng bộ.
* **Mô tả chi tiết:**
  * Khởi tạo một fixture `event_loop` dùng chung cho toàn bộ phiên chạy test (Session-scoped).
  * Giúp đồng bộ hóa các tác vụ bất đồng bộ phức tạp của Game Orchestrator và Database Manager trong quá trình kiểm thử tích hợp.

---

## 5. CÔ LẬP CƠ SỞ DỮ LIỆU (DATABASE SANDBOXING)

### 🗄️ SQLite & Pytest `tmp_path`
* **Công nghệ:** `sqlite3` kết hợp với Fixture `tmp_path` của Pytest.
* **Vai trò:** Tạo môi trường cơ sở dữ liệu tạm thời cô lập cho từng ca kiểm thử.
* **Mô tả chi tiết:**
  * Fixture `test_db_paths` tạo ra một thư mục tạm thời duy nhất cho mỗi luồng chạy test.
  * Đường dẫn DB được định cấu hình động tới một tệp SQLite tạm (`WorldTest.db`).
  * Cơ sở dữ liệu này được khởi tạo tự động, chạy các câu lệnh tạo bảng, chèn dữ liệu kiểm thử và thực hiện truy vấn. Sau khi ca test kết thúc, thư mục tạm này sẽ tự động bị hệ thống xóa sạch, đảm bảo:
    1. Không ghi đè hoặc làm hỏng cơ sở dữ liệu chính của trò chơi (`World.db`).
    2. Các ca test hoàn toàn độc lập, không bị ảnh hưởng bởi dữ liệu rác của các ca test trước đó.

---

## 6. ĐO LƯỜNG ĐỘ BAO PHỦ MÃ NGUỒN (CODE COVERAGE)

### 📊 Coverage.py
* **Thư viện:** `coverage` (thường tích hợp qua `pytest-cov`)
* **Vai trò:** Theo dõi và báo cáo phần trăm các dòng mã nguồn được thực thi bởi bộ kiểm thử.
* **Mô tả chi tiết:**
  * Tạo ra tệp lưu trữ dữ liệu `.coverage` ở thư mục gốc sau khi chạy lệnh test.
  * Giúp lập trình viên xác định các nhánh rẽ trong code logic (ví dụ: các điều kiện `if/else`, khối ngoại lệ `try/except`) chưa được kiểm thử bao phủ để bổ sung ca test kịp thời.

---

## 7. CẤU TRÚC THƯ MỤC KIỂM THỬ (TEST DIRECTORY STRUCTURE)

Hệ thống mã nguồn kiểm thử được tổ chức quy củ theo cấu trúc dưới đây để dễ dàng quản lý và phân loại:

```text
tests/
│
├── conftest.py               # Tệp cấu hình chung: Khởi tạo Fixtures, mock API ngoài, nạp .env
│
├── unit/                     # Thư mục chứa các ca kiểm thử đơn vị độc lập
│   ├── test_entities.py          # Kiểm tra cấu trúc khởi tạo các thực thể (NPC, Item, Quest...)
│   ├── test_player_state.py      # Kiểm tra công thức máu, sát thương, trang bị và lưu trạng thái
│   ├── test_combat_mechanics.py  # Kiểm tra các cơ chế chỉ số chiến đấu (Combat Stats) và tích hợp CombatAgent
│   ├── test_memory_processor.py  # Kiểm tra thuật toán sắp xếp và chấm điểm ký ức
│   └── test_text_formatter.py    # Kiểm tra bộ tách/định dạng các thẻ hội thoại văn bản
│
└── integration/              # Thư mục chứa các ca kiểm thử tích hợp
    ├── test_database.py          # Kiểm tra vòng đời đọc/ghi/truy vấn của cơ sở dữ liệu SQLite
    ├── test_api.py               # Kiểm tra các cổng API của server FastAPI bằng TestClient
    └── test_online_agents.py     # Kiểm tra gọi API thực tế tới tác nhân Groq/Gemini (khi online)
```

> [!NOTE]
> Bộ kiểm thử này được thiết kế để có thể chạy hoàn toàn **Offline** mà không cần kết nối mạng hay khóa API thực tế (sử dụng 34 ca test đầu), hoặc chạy ở chế độ **Online** (kết hợp thêm 4 ca test trực tuyến) khi cần xác thực tích hợp đầu-cuối với các mô hình ngôn ngữ lớn từ Google và Groq.
