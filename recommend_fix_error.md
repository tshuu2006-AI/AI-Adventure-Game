# ĐỀ XUẤT VÀ Ý TƯỞNG KHẮC PHỤC LỖI HỆ THỐNG ELDORIA (ERROR RECOMMENDATIONS)

Tài liệu này phân tích chi tiết nguyên nhân gốc rễ và đề xuất phương án sửa đổi cho 5 lỗi hệ thống được ghi nhận trong tệp tin `game_error.txt`.

---

## 1. 🔄 LỖI 1: CHƠI GAME MỚI KHÔNG RESET LƯỢT CHƠI (TURN COUNT) & ĐÈ KÝ ỨC RAG

### 🔴 Triệu chứng
Sau khi lưu game và bấm chơi game mới, game mới bị ảnh hưởng bởi dữ liệu lưu cũ: số lượt chơi (turn) không được reset về 0 mà tiếp tục tăng, và cốt truyện mới bị chồng chéo ký ức cũ.

### 🔍 Nguyên nhân gốc rễ
* Khi tạo game mới, máy chủ gọi hàm `setup_new_game_api` trong [Orchestration.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/Orchestration.py) để thực hiện `self.player_state.clear()`.
* Tuy nhiên, hệ thống **chỉ reset trạng thái người chơi** (RAM PlayerState) và SQLite DB, nhưng **hoàn toàn bỏ quên** việc làm sạch hệ thống ký ức của RAG:
  1. Cấu trúc bộ nhớ dài hạn `self.memory_sys.long_term_memory` (sử dụng FAISS và SentenceTransformer) **không được tẩy trắng**. Lượng vector ký ức cũ trong file `vector_index.bin` và `vector_meta.pkl` vẫn giữ nguyên.
  2. Biến đếm lượt chơi dài hạn `long_term_memory.game_turn` trong [MemoryManager.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/DataManager/MemoryManager.py) không được đưa về `0` (hàm `reset_vector_db` hiện tại chỉ reset `num_memory` mà quên reset `game_turn`).
  3. Cửa sổ bộ nhớ ngắn hạn `self.memory_sys.short_term_memory.context_window` không được dọn dẹp, dẫn đến việc LLM nạp lại lịch sử trò chuyện của game cũ.

### 💡 Giải pháp đề xuất
1. **Bổ sung reset game_turn trong FAISS Manager:** Cập nhật hàm `reset_vector_db` trong [MemoryManager.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/DataManager/MemoryManager.py):
   ```diff
   def reset_vector_db(self) -> None:
       try:
           self.index = faiss.IndexIDMap(faiss.IndexFlatIP(self.dimension))
           self.metadata = {}
           self.num_memory = 0
+          self.game_turn = 0  # Reset lượt chơi về 0
   ```
2. **Kích hoạt dọn dẹp bộ nhớ trong Orchestrator:** Thêm các dòng dọn dẹp bộ nhớ dài hạn và ngắn hạn khi tạo game mới trong `setup_new_game_api` ở [Orchestration.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/Orchestration.py):
   ```diff
   async def setup_new_game_api(self, player_idea: str) -> str:
       self.player_state.clear()
+      self.memory_sys.long_term_memory.reset_vector_db()
+      self.memory_sys.short_term_memory.context_window = []
+      self.memory_sys.short_term_memory.current_structured_memory = None
   ```

---

## 2. 🗡️ LỖI 2: CHỈ SỐ KHÔNG CỐ ĐỊNH KHI TRANG BỊ VẬT PHẨM (DYNAMIC MODIFIERS KEY)

### 🔴 Triệu chứng
Khi trang bị vật phẩm, các chỉ số thuộc tính của nhân vật tăng/giảm không cố định, hoặc buff chỉ số không được áp dụng chính xác.

### 🔍 Nguyên nhân gốc rễ
* Khi chế tạo thành công một vũ khí mới qua AI Agent, cấu trúc bổ trợ chỉ số (modifiers) được LLM sinh tự động.
* AI Agent thường sinh ra các key ngẫu nhiên hoặc viết tắt như `"str": 5`, `"def": 2`, `"agi": 3` thay vì viết đầy đủ.
* Trong khi đó, hệ thống quản lý thuộc tính [StatsManager.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/DataManager/StatsManager.py) chỉ chấp nhận các key chuẩn cố định là: `strength`, `agility`, `intelligence`, `defense`. 
* Khi chạy hàm `apply_equipment(modifiers)`:
  ```python
  if modifiers:
      for k, v in modifiers.items():
          if k in self.bonus_stats: # Chỉ nhận diện "strength", "agility"...
              self.bonus_stats[k] = v
  ```
  Nếu key từ LLM truyền sang là `"str"` hay `"def"`, nó sẽ bị bỏ qua hoàn toàn, dẫn đến việc trang bị vũ khí nhưng không được tăng chỉ số thực tế.

### 💡 Giải pháp đề xuất
Thực hiện chuẩn hóa (Normalization) dữ liệu modifiers đầu vào trước khi áp dụng trang bị. Có thể chèn hàm ánh xạ chuẩn trong `apply_equipment` ở [StatsManager.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/engine/DataManager/StatsManager.py):
```python
def apply_equipment(self, modifiers: dict):
    # Xóa buff cũ
    self.bonus_stats = {"strength": 0, "agility": 0, "intelligence": 0, "defense": 0}
    
    if not modifiers:
        return

    # Bản đồ ánh xạ từ viết tắt sang key chuẩn
    normalization_map = {
        "str": "strength", "strength": "strength",
        "agi": "agility", "agility": "agility",
        "int": "intelligence", "intelligence": "intelligence",
        "def": "defense", "defense": "defense"
    }

    for k, v in modifiers.items():
        standard_key = normalization_map.get(k.lower().strip())
        if standard_key and standard_key in self.bonus_stats:
            try:
                self.bonus_stats[standard_key] = int(v)
            except (ValueError, TypeError):
                pass
```

---

## 3. 🧠 LỖI 3: GAME BỊ MẤT TRÍ NHỚ (MẤT CONTEXT) SAU VÀI LẦN LƯU/TẢI

### 🔴 Triệu chứng
Sau khi lưu và tải game nhiều lần, cốt truyện bắt đầu có dấu hiệu mất trí nhớ, AI quên cốt truyện cũ hoặc nhầm lẫn bối cảnh hiện tại.

### 🔍 Nguyên nhân gốc rễ
* **Độ trễ I/O và Đè file:** Hàm `save_game` và `load_game` thực hiện đóng cơ sở dữ liệu SQLite, sao chép đè tệp tin vật lý (`eldoria.db`, `vector_index.bin`, `vector_meta.pkl`), rồi mở lại kết nối.
* Trong môi trường bất đồng bộ (`asyncio`), việc sao chép file vật lý bằng `shutil.copy` chạy đồng bộ (blocking) có thể gây xung đột luồng khi hệ thống đang ghi dở dữ liệu từ các luồng chạy ngầm (Background Task). Điều này dẫn đến phân mảnh hoặc hỏng tệp FAISS index.
* **Lệch Turn Ký ức:** Khi tải game (`load_game`), hệ thống chỉ gán lại `long_term_memory.game_turn` bằng turn của người chơi nhưng không khôi phục trạng thái bộ đếm `num_memory` của FAISS, làm sai lệch chỉ số ID liên kết giữa SQLite và FAISS.

### 💡 Giải pháp đề xuất
1. **Độc lập thư mục lưu trữ (Slots isolation):** Chia các khe lưu thành các thư mục vật lý riêng biệt hoàn toàn (Slot_1, Slot_2...) để tránh ghi đè trực tiếp lên tệp cơ sở dữ liệu runtime đang mở.
2. **Xử lý bất đồng bộ an toàn khi I/O:** Chuyển đổi các tác vụ sao chép file sang chế độ bất đồng bộ an toàn:
   ```python
   import aiofiles
   # Thay thế shutil.copy bằng cơ chế sao chép luồng bất đồng bộ hoặc chạy trong Executor
   await asyncio.to_thread(shutil.copy, src, dst)
   ```
3. **Đồng bộ triệt để dữ liệu RAG:** Đảm bảo khi nạp game thành công, phải gọi hàm khôi phục đầy đủ trạng thái của `long_term_memory` (gồm cả biến `num_memory` bằng độ dài metadata đã tải).

---

## 4. 🔗 LỖI 4: LỆCH THÔNG BÁO VẬT PHẨM GIỮA FRONTEND VÀ BACKEND

### 🔴 Triệu chứng
Trên giao diện người chơi (Frontend) báo đã nhận được vật phẩm, nhưng trong hòm đồ (Backend) kiểm tra lại không thấy có vật phẩm đó.

### 🔍 Nguyên nhân gốc rễ
* **Cơ chế tách rời bất đồng bộ:** Backend xử lý trích xuất vật phẩm thông qua nhiệm vụ nền chạy ngầm `background_post_turn_processing` (gọi AI qua `StateExtractor`).
* Frontend nhận văn bản câu chuyện thô trước, tự quét các từ khóa hoặc thẻ tag để hiển thị thông báo. Trong khi đó, Backend gọi API AI ở tác vụ nền để cập nhật túi đồ.
* Nếu Gemini bị hết token, quá tải mạng, hoặc phân tích logic bị lỗi/trả về JSON sai cấu trúc, tác vụ nền sẽ ghi nhận lỗi và **không cập nhật vật phẩm** vào cơ sở dữ liệu backend. Kết quả là người chơi nhìn thấy thông báo nhưng thực tế không sở hữu vật phẩm.

### 💡 Giải pháp đề xuất
1. **Chuyển tác vụ State Extraction lên đồng bộ:** Không nên chạy trích xuất trạng thái (nhặt đồ, NPC di chuyển) ở dạng tác vụ nền (Background Task). Việc này cần được xử lý và trả về chung luồng trong API `/api/play` để đảm bảo khi Client nhận phản hồi thì Database đã được cập nhật thành công.
2. **Cơ chế dự phòng bằng Thẻ tag tường minh (Rule-based Fallback):** Thêm một bộ quét Regex ở Backend để tự động nhặt đồ nếu trong văn bản trả về của Master có thẻ tag rõ ràng (VD: `[ITEM_ADD: Kiếm rỉ]`), tránh phụ thuộc 100% vào việc trích xuất của LLM.

---

## 5. 🏆 LỖI 5: THIẾU CƠ CHẾ KẾT THÚC GAME KHI HOÀN THÀNH NHIỆM VỤ CHÍNH

### 🔴 Triệu chứng
Người chơi đã hoàn thành tất cả các mục tiêu của nhiệm vụ chính (Campaign), tuy nhiên trò chơi vẫn tiếp diễn bình thường, không có màn hình thông báo chiến thắng hay kết thúc game.

### 🔍 Nguyên nhân gốc rễ
* Hệ thống `QuestProcessor.evaluate_turn` đã cập nhật trạng thái nhiệm vụ chính sang `completed`, nhưng game loop tại backend (`server.py` và `Orchestration.py`) hoàn toàn không có câu lệnh kiểm tra điều kiện thắng cuộc để dừng trò chơi.

### 💡 Giải pháp đề xuất
Thêm cờ kiểm tra trạng thái chiến thắng trong API lượt đi `/api/play` ở [server.py](file:///d:/D/HOCTAP/TDTT/AI-Adventure-Game/server.py):
```python
# Trong api play_turn
active_quest = orc.get_active_quest()
main_quest = orc.player_state.main_quest

is_victory = False
if main_quest and main_quest.status == "completed":
    is_victory = True
    game_logger.info("🏆 CHIẾN THẮNG! Người chơi đã hoàn thành chiến dịch chính.")

return JSONResponse(content={
    "segments": segments,
    "choices": choice_texts if not is_victory else [], # Không sinh thêm lựa chọn nếu đã thắng
    "bg_image_b64": "",
    "char_image_b64": "",
    "inventory": [],
    "hp": current_hp,
    "max_hp": orc.get_max_hp(),
    "is_dead": is_dead,
    "is_victory": is_victory # Gửi tín hiệu chiến thắng để Frontend hiển thị màn hình chúc mừng
})
```
