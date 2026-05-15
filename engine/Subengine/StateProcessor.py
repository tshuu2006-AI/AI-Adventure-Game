
import asyncio
import time
from world.Entity import Location, NPC
from engine.Agents.LocalAgents import StateExtractor


class StateProcessor:
    def __init__(self, db, player_state, image_manager, pm):
        self.db = db
        self.player_state = player_state
        self.image_manager = image_manager
        # self.action_processor = ActionProcessor(pm = pm, model_name = "qwen2.5:1.5b")
        self.extractor = StateExtractor(pm=pm, model_name="qwen2.5:1.5b")


    async def _handle_new_location(self, new_loc_data: dict) -> Location:
        """
        Xử lý logic khi người chơi bước vào một khu vực mới.
        Cập nhật PlayerState, lưu Database và vẽ ảnh nền.
        Trả về đối tượng Location để sử dụng ở các bước tiếp theo.
        """
        if not new_loc_data:
            return None

        # 1. Khởi tạo đối tượng Location từ dữ liệu JSON của LLM
        new_location = Location(
            id=None,
            name=new_loc_data.get('name', 'Vùng đất vô danh'),
            description=new_loc_data.get('description', ''),
            atmosphere=new_loc_data.get('atmosphere', 'Bình thường')
        )

        print(f">> [Hệ Thống] Phát hiện khu vực mới: {new_location.name}. Đang tải ảnh nền...")


        # 2. Gọi ImageManager tải/vẽ ảnh nền (Chạy bất đồng bộ)
        img_path = await self.image_manager.get_or_create_location_image(
            location_name=new_location.name,
            description=new_location.description,
            atmosphere=new_location.atmosphere
        )

        # 3. Cập nhật PlayerState
        if img_path:
            new_location.image_path = img_path
            print(f"[UI] Đã tải xong ảnh nền: {img_path}")

        self.player_state.currentLocation = new_location

        # 4. Ghi nhận địa điểm mới vào CSDL để dùng cho FAISS Entity-Centric sau này
        self.db.add_location_to_db(new_location)

        return new_location


    async def _handle_new_npc(self, new_npc_data: dict) -> NPC:
        """
        Xử lý logic khi người chơi gặp một nhân vật mới.
        Lưu Database và vẽ chân dung nhân vật.
        Trả về đối tượng NPC.
        """
        if not new_npc_data:
            # Xóa ảnh NPC cũ khỏi màn hình nếu không có NPC nào trong scene
            self.player_state.current_npc_image = None
            return None

        # 1. Khởi tạo đối tượng NPC từ dữ liệu JSON
        new_npc = NPC(
            id=None,
            name=new_npc_data.get('name', 'Kẻ lạ mặt'),
            description=new_npc_data.get('description', ''),
            personality=new_npc_data.get('personality', 'Bí ẩn'),
            affectionate=0,  # Bắt đầu với mức độ thân thiết trung lập
            location=new_npc_data.get('location', self.player_state.currentLocation.name),
            status=new_npc_data.get('status', 'Bình thường')
        )

        print(f">> [Hệ Thống] Gặp gỡ nhân vật: {new_npc.name}. Đang tải chân dung...")

        # 2. Gọi ImageManager tải/vẽ chân dung (Chạy bất đồng bộ)
        img_path = await self.image_manager.get_or_create_npc_image(
            npc_name=new_npc.name,
            description=new_npc.description
        )

        # 3. Cập nhật PlayerState để UI (Unity/Web) hiển thị ảnh
        if img_path:
            self.player_state.current_npc_image = img_path
            print(f"[UI] Đã tải xong ảnh nhân vật: {img_path}")

        # 4. Lưu NPC vào CSDL
        self.db.add_npc_to_db(new_npc)

        return new_npc


    async def _update_inventory(self, items_added: list, items_removed: list):
        """Hàm chuyên xử lý logic túi đồ và tạo/xóa ảnh vật phẩm."""
        if items_added or items_removed:
            print("\n[Hệ Thống] ---> THAY ĐỔI TÚI ĐỒ <---")

            # 1. Thêm Item mới -> Vẽ ảnh
            if isinstance(items_added, list):
                for item in items_added:
                    # Kiểm tra item chưa có trong keys của Dictionary
                    if item and item not in self.player_state.inventory:
                        # Gọi Kaggle vẽ ảnh
                        img_path = await self.image_manager.get_or_create_item_image(item)

                        # Lưu vào Dict
                        self.player_state.inventory[item] = img_path
                        print(f" [+] Nhận được: {item}")

            # 2. Mất Item cũ -> Xóa ảnh và gỡ khỏi Dict
            if isinstance(items_removed, list):
                for item in items_removed:
                    if item and item in self.player_state.inventory:
                        # Lấy đường dẫn ảnh bằng pop() (vừa lấy vừa xóa khỏi Dict)
                        img_path = self.player_state.inventory.pop(item)

                        # Xóa file vật lý
                        if img_path:
                            self.image_manager.delete_image(img_path)
                        print(f" [-] Bị mất: {item}")

            # Lấy danh sách chìa khóa (Tên items) để in ra console
            inventory_status = ", ".join(self.player_state.inventory.keys()) if self.player_state.inventory else "Trống rỗng"
            print(f" [Balo hiện tại]: {inventory_status}")


    async def process_background_tasks(self, player_input, story_response):
        """Chạy song song trích xuất State"""
        start_bg = time.perf_counter()
        state_changes = await self.extractor.extract_state(player_input = player_input, story_response = story_response)
        print(f"[Profile] Background Tasks: {time.perf_counter() - start_bg:.3f}s")

        if not isinstance(state_changes, dict): state_changes = {}

        # Áp dụng các thay đổi (Bưng nguyên cụm update_tasks cũ sang)
        update_tasks = [
            self._update_inventory(state_changes.get("items_added", []), state_changes.get("items_removed", [])),
            self._handle_new_location(state_changes.get("new_location_entered")),
            self._handle_new_npc(state_changes.get("new_npc_encountered"))
        ]

        await asyncio.gather(*update_tasks)
        npc_data = state_changes.get("new_npc_encountered")
        new_npc_name = npc_data.get('name') if isinstance(npc_data, dict) else None

        atomic_memories = state_changes.get("atomic_memories", [])
        return new_npc_name, atomic_memories  # Trả về tên NPC để lưu Memory

    # Các hàm _update_inventory, _handle_new_location (gọi ImageManager) bỏ vào đây.