# Nhật Ký Kiểm Thử Hệ Thống (Test Log) - AI Story Adventure

Tài liệu này chia làm 2 phần chính: **Phần 1: Kiểm thử Ngoại tuyến (Offline)** để xác thực cơ chế game và luồng dữ liệu thông qua Mocking, và **Phần 2: Kiểm thử Trực tuyến (Online)** để chạy kiểm thử tích hợp trực tiếp với API thật của Groq và Gemini thông qua file cấu hình `.env`.

---

## 📂 PHẦN 1: KIỂM THỰ NGOẠI TUYẾN (OFFLINE TESTING - MẶC ĐỊNH)

Chế độ ngoại tuyến giúp chạy toàn bộ bộ kiểm thử trong môi trường độc lập, **không cần kết nối Internet và không cần API Key thật**. Chế độ này giả lập (Mock) toàn bộ các dịch vụ AI để kiểm tra tính đúng đắn của logic lập trình.

### ⚙️ 1. Môi trường & Cách chạy
- **TEST_MODE mặc định:** `offline`
- **Lệnh chạy:**
  ```powershell
  d:\D\HOCTAP\TDTT\.venv\Scripts\python.exe -m pytest tests/ -v
  ```

### 🧠 2. Các Kịch Bản & Thành Phần Được Xác Thực

1. **Hệ thống Ký ức (Memory):**
   - **Short-term Memory:** Cửa sổ trượt FIFO giới hạn đúng 4 lượt chơi. Khi đẩy lượt chơi thứ 5 vào, lượt chơi thứ 1 tự động bị loại bỏ khỏi `context_window`.
   - **Vector DB (FAISS):** Kiểm tra tính năng nạp index, lưu tệp index (`vector_index.bin`) và siêu dữ liệu (`vector_meta.pkl`).
   - **Thuật toán Reranking:** Xác thực độ lệch điểm số khi áp dụng Time Decay ($e^{-0.05 \Delta t}$), điểm thưởng địa điểm (+20%) và điểm thưởng từ khóa (+15% mỗi từ).
2. **Cơ chế Game (Mechanics):**
   - **HP & Sát thương:** Kiểm tra công thức $\text{Actual Damage} = \max(1, \text{Damage} - 0.5 \times \text{Defense})$. Đảm bảo HP không vượt quá 100 và không âm khi nhận sát thương chí mạng.
   - **Balo & Trang bị:** Xác thực chỉ số sức mạnh cộng thêm tăng từ 10 lên 15 khi cầm kiếm thường, lên 25 khi đổi kiếm vàng, và hồi về 10 khi tháo trang bị.
   - **Vật phẩm tiêu hao:** Uống thuốc tăng HP hiện tại và trừ số lượng thuốc trong balo.
   - **Nhiệm vụ (Quest):** Theo dõi tiến trình qua mảng bit mục tiêu và cơ chế sao lưu Snapshot bối cảnh cũ khi chuyển Quest.
3. **Lưu trữ dữ liệu (Save/Load):**
   - Đảm bảo `PlayerState.to_dict()` xuất đầy đủ thông tin runtime.
   - Kiểm tra `load_state()` tự động ánh xạ (resolve reference) các tên NPC/Địa điểm dạng chuỗi từ file JSON ngược lại thành đối tượng thực tế trong SQLite.
4. **FastAPI Endpoints (Mock API):**
   - Xác thực API `/api/ping` trả về trạng thái hoạt động tốt (HTTP 200).
   - Kiểm tra API `/api/poll_updates` trả về đúng cấu trúc JSON chứa đầy đủ máu hiện tại, vũ khí đang đeo, các chỉ số sức mạnh và quest đang theo dõi của người chơi mà không bị crash định dạng JSON.

---

## 🌐 PHẦN 2: KIỂM THỰ TRỰC TUYẾN VỚI API THẬT (ONLINE TESTING)

Chế độ trực tuyến cho phép chạy tích hợp trực tiếp với các mô hình ngôn ngữ lớn (LLM) thật để xác thực tính đúng đắn khi giao tiếp API thực tế của Groq và Gemini.

### ⚙️ 1. Cài đặt Cấu hình API Keys
Hệ thống tự động nạp cấu hình từ file **[.env](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/.env)** ở thư mục gốc:
```env
GROQ_API_KEY=gsk_your_real_groq_key_here
GEMINI_API_KEY=your_real_gemini_key_here
```

### 🚀 2. Lệnh chạy chế độ Online
Chúng ta sử dụng biến môi trường `TEST_MODE="online"` trước khi chạy test:

- **Trên Windows PowerShell:**
  ```powershell
  $env:TEST_MODE="online"; d:\D\HOCTAP\TDTT\.venv\Scripts\python.exe -m pytest tests/ -v
  ```

### 📈 3. Kết quả thực thi Online (LẤY TỪ CHẠY THỰC TẾ)

Tất cả **32/32 test cases** chạy thành công mỹ mãn (**PASSED 100%**).

```text
tests/integration/test_api.py::test_ping_endpoint PASSED                 [  3%]
tests/integration/test_api.py::test_check_config_endpoint_success PASSED [  6%]
tests/integration/test_api.py::test_check_config_endpoint_failure PASSED [  9%]
tests/integration/test_api.py::test_poll_updates_endpoint PASSED         [ 12%]
tests/integration/test_api.py::test_diary_endpoint PASSED                [ 15%]
tests/integration/test_api.py::test_inventory_equip_endpoint_not_found PASSED [ 18%]
tests/integration/test_database.py::test_database_manager_lifecycle PASSED [ 21%]
tests/integration/test_online_agents.py::test_online_intent_router_gemini PASSED [ 25%]
tests/integration/test_online_agents.py::test_online_choice_agent_groq PASSED [ 28%]
tests/unit/test_entities.py::... PASSED                                  [...%]
...
======================= 32 passed, 4 warnings in 21.87s =======================
```

#### Chi tiết 2 kịch bản tích hợp trực tuyến đã pass:
1. **`test_online_intent_router_gemini` (Google Gemini API):**
   - *Hành động gửi đi:* `"Tôi muốn mở chiếc hòm gỗ cổ xưa kia"`
   - *Phản hồi thu được:* Dữ liệu cấu trúc JSON từ Gemini phân tích thành công ý định mở hòm của người chơi:
     `{"intent": "INTERACT", "target": "ancient wooden chest", "action_details": "open"}` (hoặc tương tự).
   - *Ý nghĩa kiểm thử:* Đảm bảo prompt định tuyến ý định hoạt động nhất quán, Gemini phân tích chính xác ra đúng 3 trường dữ liệu bắt buộc không bị lệch cấu trúc.
2. **`test_online_choice_agent_groq` (Groq API - Llama 3):**
   - *Ngữ cảnh gửi đi:* Giả lập bối cảnh tại "Lâu đài hoang", tương tác với "Elara" và có quest "Tìm lối thoát".
   - *Phản hồi thu được:* Groq trả về thành công danh sách các lựa chọn nhập vai dạng:
     `{"choices": [{"id": 1, "action_text": "Dùng chìa khóa mở cánh cửa bí mật", "style": "Quyết đoán"}, ... ]}`
   - *Ý nghĩa kiểm thử:* Đảm bảo prompt sinh menu lựa chọn tương thích với cấu trúc của game engine, Llama-3 sinh định dạng JSON hoàn toàn đúng chuẩn không thiếu trường nào.

---

## 📈 4. Báo Cáo Độ Bao Phủ Dòng Code (Code Coverage)

```text
Name                                                  Stmts   Miss  Cover
-------------------------------------------------------------------------
engine\Agents\CloudAgents.py                            162    119    27%
engine\Agents\LocalAgents.py                            159    119    25%
engine\DataManager\DatabaseManager.py                   110     17    85%
engine\DataManager\EntityManager\BaseManager.py          41      8    80%
engine\DataManager\EntityManager\LocationManager.py      24      3    88%
engine\DataManager\EntityManager\MemoryManager.py        41      5    88%
engine\DataManager\EntityManager\NPCManager.py           48     15    69%
engine\DataManager\ImageManager.py                       88     67    24%
engine\DataManager\InventoryManager.py                  107     48    55%
engine\DataManager\MemoryManager.py                     116     76    34%
engine\DataManager\PlayerState.py                       145     29    80%
engine\DataManager\StatsManager.py                       46      4    91%
engine\DataManager\WorldState.py                         18      7    61%
engine\ImageAPI.py                                       32     24    25%
engine\Orchestration.py                                 307    231    25%
engine\Subengine\ActionProcessor.py                      72     52    28%
engine\Subengine\ItemProcessor.py                       109     91    17%
engine\Subengine\MemoryProcessor.py                     107     68    36%
engine\Subengine\QuestProcessor.py                       78     63    19%
engine\Subengine\SaveManager.py                          70     60    14%
engine\Subengine\StateProcessor.py                      161    135    16%
engine\Subengine\StoryDirector.py                        98     74    24%
engine\Utils\AudioManager.py                             56     42    25%
engine\Utils\PromptManager.py                            26     14    46%
engine\Utils\TextFormatter.py                            46      3    93%
engine\Utils\logger.py                                   17      1    94%
server.py                                               350    214    39%
world\Entity.py                                          58      0   100%
-------------------------------------------------------------------------
TOTAL                                                  2692   1589    41%
```
