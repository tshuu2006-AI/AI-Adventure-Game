# Edit Log - ItemAgent & QuestAgent

Ngay cap nhat: 2026-05-31

## Tong quan
Da them he thong ItemAgent va QuestAgent, mo rong kieu Item, va bo sung luong quest phu. Cac thay doi duoc thiet ke de khong anh huong mach truyen chinh.

## Cac file da thay doi
- world/Entity.py
  - Them cac lop Item: ConsumableItem, WeaponItem, QuestItem
  - Mo rong Item voi item_type, effect, quest_id, image_path
  - Them dataclass Quest de luu thong tin quest phu

- engine/Agents/LocalAgents.py
  - Them ItemAgent
    - classify_item: phan loai item theo ten va boi canh
    - build_item_object: tao object item tu du lieu JSON
    - fallback heuristics cho truong hop LLM loi
  - Them QuestAgent
    - generate_side_quest: sinh quest phu tu boi canh
    - evaluate_quest: kiem tra hoan thanh quest
    - fallback quest/reward neu LLM loi

- static/prompts.yaml
  - Them prompt ItemAgent
  - Them prompt QuestAgent (generate/evaluate)

- engine/Subengine/StateProcessor.py
  - Ket noi ItemAgent vao luong _update_inventory
  - Them luong quest phu: _maybe_create_side_quest va _evaluate_active_quests
  - Tu dong ghi quest hoan thanh va tang thuong vao inventory

- engine/Subengine/SaveManager.py
  - Luu/nap item theo JSON (giu item_type, effect, quest_id)
  - Luu/nap active_quests va completed_quests

- engine/DataManager/DatabaseManager.py
  - Mo rong PlayerState: active_quests, completed_quests

- server.py
  - payload inventory bo sung item_type va effect

## Co che ItemAgent
- Dau vao: ten item + boi canh
- Dau ra: JSON voi item_type va cac truong bat buoc
- Ba loai item:
  - ConsumableItem: description + effect
  - WeaponItem: description + (damage, rarity)
  - QuestItem: description
- Neu LLM loi, fallback theo tu khoa:
  - "kiem/dao/sung" -> WeaponItem
  - "thuoc/nuoc/tang luc" -> ConsumableItem
  - Con lai -> QuestItem

## Co che QuestAgent
- generate_side_quest
  - Sinh 1 quest phu tu boi canh (khong anh huong mach chinh)
  - Gioi han so quest active (toi da 2)
  - Reward chi duoc la ConsumableItem hoac WeaponItem

- evaluate_quest
  - Kiem tra quest co hoan thanh dua tren story_response va state
  - Neu hoan thanh -> cap reward, danh dau completed

## Vi tri debug nhanh
- ItemAgent/QuestAgent logic: engine/Agents/LocalAgents.py
- Gan quest vao runtime: engine/Subengine/StateProcessor.py
- Luu/nap quest: engine/Subengine/SaveManager.py
- Payload ve Unity: server.py (build_inventory_payload)

## Fix loi 2026-06-01
### Nguyen nhan
- Loi nhe: Memory table trong database cu thieu cot `gameturn` hoac dung schema cu, dan toi query trong get_memories_by_ids bi loi.
- Loi nghiem trong: bang MEMORY_NPC tham chieu Memory khong dung schema (foreign key mismatch) do Memory table khong co primary key `memory_id` theo schema moi.

### Chinh sua
- Them kiem tra schema trong DatabaseManager._ensure_memory_schema
  - Neu Memory thieu cot hoac primary key sai -> drop va tao lai Memory + MEMORY_NPC
  - Neu MEMORY_NPC fk sai -> drop va tao lai MEMORY_NPC
- Goi _ensure_memory_schema sau khi create_tables de tu dong sua schema cu.

## Fix loi 2026-06-01 (lan 2)
### Nguyen nhan
- reset_database bi loi FOREIGN KEY constraint failed khi xoa bang co khoa ngoai.

### Chinh sua
- Tat tam foreign_keys trong reset_database, xoa du lieu, commit, sau do bat lai foreign_keys.

## Cập nhật quest 2026-06-01
### Thay đổi
- Tăng giới hạn quest đang mở từ 2 lên 3.
- Thêm hàng đợi thông báo quest khi hoàn thành quest và nhận thưởng.
- Xuất active/completed quest cùng quest_notifications ra API poll_updates.
- Thêm lifecycle_state để nhìn rõ vòng đời quest: active -> completed -> rewarded.

### Ghi chú debug
- Reward notification được đẩy từ StateProcessor khi quest hoàn thành.
- Unity có thể đọc quest_notifications từ /api/poll_updates để hiện popup/toast.

## Cập nhật quest 2026-06-01 (lan 2)
### Thay đổi
- Thêm thong bao khi tao quest moi (quest_notifications).
- In thong bao quest va danh sach quest dang lam trong console mode (Orchestration).
- Thong bao hoan thanh quest se duoc in ra terminal va xoa khoi hang doi sau khi hien thi.

## Cơ chế quest branch 2026-06-01
### Mô hình mới
- Quest được chia thành 2 lớp: `available_quests` và `active_quests`.
- Người chơi chọn `quest accept <n>` để lưu checkpoint mạch chính và tách sang quest branch.
- Người chơi có thể `quest abandon` để quay lại checkpoint mà không phá mạch chính.
- Khi quest hoàn thành, hệ thống tự lưu sự kiện quest, trả thưởng, rồi quay lại checkpoint bằng transition hợp lý.

### Database mới
- `QuestBranches`: lưu checkpoint, trạng thái branch, lý do quay lại, câu chuyển cảnh.
- `QuestEvents`: lưu các sự kiện trong quest theo từng turn, kể cả khi chưa hoàn thành.

### Debug nhanh
- Terminal: dùng `quest list`, `quest accept <n>`, `quest abandon`, `quest status`.
- API poll_updates: nhận `available_quests`, `active_quests`, `completed_quests`, `quest_notifications`, `quest_branch_active`.

## Quest branch co lua chon 2026-06-01
### Thay đổi
- Quest branch duoc ke chuyen bang prompt QuestStoryAgent, giu main plot tam dung.
- Quest branch sinh choices bang QuestChoiceAgent, dam bao co 1 lua chon quay ve mach chinh.
- Orchestration va server /api/play tu dong chuyen sang luong quest neu quest_branch_active.

## Hybrid Quest Choice System 2026-06-01
### Khái niệm (Hybrid Approach)
**Mục tiêu:** Sinh lựa chọn cho quest branch giống mạch chính, với caching tối ưu chi phí API.

### Thay đổi chính
1. **PlayerState** (DatabaseManager.py:319)
   - Thêm `preQuestMainChoices`: cache lựa chọn mạch chính trước khi vào quest
   - Thêm `questIntroGenerated`: flag kiểm tra xem đã sinh intro choices chưa

2. **StateProcessor** (StateProcessor.py:383)
   - Thêm hàm `capture_main_menu_choices()`: lưu choices trước khi accept quest
   - Dùng để restore lựa chọn khi quay lại mạch chính

3. **StoryDirector** (StoryDirector.py:158)
   - Thêm hàm `generate_quest_intro_choices()`: sinh choices khi bắt đầu quest
   - Gọi ChoiceAgent với prompt riêng cho quest intro

4. **ChoiceAgent** (CloudAgents.py:281)
   - Thêm hàm `generate_quest_intro_choices()`: gọi LLM để sinh choices intro
   - Dùng prompt 'QuestIntroChoiceAgent' (cần thêm vào prompts.yaml)

5. **Orchestration** (Orchestration.py:219)
   - Khi user input "quest accept <n>":
     * Capture lựa chọn hiện tại vào `preQuestMainChoices`
     * Gọi `start_quest_branch()`
     * Sinh quest intro choices với `generate_quest_intro_choices()`
     * Hiển thị choices intro
   - Khi return từ quest ("tạm gác", "quay lại"):
     * Gọi `return_from_quest_branch()`
     * Restore choices từ cache nếu có
     * Nếu không có cache, sinh mới choices mạch chính

### Flow Chi Tiết
```
┌─ Mạch Chính (Story + Choices) ─┐
│  Story 1 → Choices A,B,C       │
└────────────────────────────────┘
         ↓ User chọn Accept Quest
┌──────────────────────────────────┐
│ 1. Capture Choices A,B,C (cache) │
│ 2. start_quest_branch()          │
│ 3. Sinh Quest Intro Choices      │
│    (gọi LLM 1 lần)               │
│ 4. Show Intro Choices D,E,F      │
└──────────────────────────────────┘
         ↓ User trong Quest
┌──────────────────────────────────┐
│ Quest Story (QuestStoryAgent)    │
│ Quest Choices (QuestChoiceAgent) │
└──────────────────────────────────┘
    ↓ User "Tạm gác" hoặc Complete
┌──────────────────────────────────┐
│ 1. Return Transition (LLM)       │
│ 2. Khôi phục checkpoint chính    │
│ 3. Restore Choices A,B,C (cache) │
│    Nếu cache miss → sinh mới     │
│ 4. Show Main Choices again       │
└──────────────────────────────────┘
```

### Chi phí API (Hybrid vs Naive)
| Scenario | Naive | Hybrid |
|----------|-------|--------|
| Accept Quest | +1 API (intro) | +1 API (intro) |
| Quest Loop (n turns) | +n API (choices) | 0 API (lùi về old) |
| Return Quest | +1 API (choices) | 0 API (cache) |
| **Tổng (10 turns)** | **+12 API** | **+2 API** |

### Cách dùng & Debug
- **Terminal:** Gõ `quest accept 1` → phải thấy intro choices khác choices mạch chính
- **Terminal:** Gõ `quit`, `tạm gác`, hay hoàn tất quest → phải thấy choices mạch chính cũ
- **Log:** Tìm "[QuestSystem]" để theo dõi cache/restore
- **Prompt:** Cần thêm 'QuestIntroChoiceAgent' vào `static/prompts.yaml`

### Lợi ích
✓ **Nhanh:** Quay lại mạch chính chỉ cần cache, không gọi API
✓ **Rẻ:** Chỉ +1 API khi accept, không lặp lại mỗi turn
✓ **Linh hoạt:** Có fallback sinh mới nếu cache miss
✓ **Rõ ràng:** Intro choices khác choices quest, giúp user hiểu flow

## Fix lỗi QuestIntroChoiceAgent 2026-06-01
### Nguyên nhân
- Code gọi `generate_quest_intro_choices()` nhưng prompt `QuestIntroChoiceAgent` chưa được thêm vào `static/prompts.yaml`
- Dẫn tới KeyError khi PromptManager không tìm thấy prompt

### Sửa chữa
- Thêm prompt `QuestIntroChoiceAgent` vào `static/prompts.yaml` (sau QuestChoiceAgent)
- Prompt tập trung vào cách BẮT ĐẦU quest (investigate, talk, prepare, etc)
- Đảm bảo có 1 choice để quay lại mạch chính

