import pytest
import os
import asyncio
from engine.DataManager.DatabaseManager import DatabaseManager
from world.Entity import NPC, Location, Memory

@pytest.mark.asyncio
async def test_database_manager_lifecycle(test_db_paths):
    db_path, db_folder = test_db_paths
    
    # 1. Khởi tạo DatabaseManager
    db = DatabaseManager(db_path=db_path, db_folder=db_folder)
    
    # 2. Kết nối và tạo bảng
    await db.connect()
    await db.create_tables()
    
    # Đảm bảo file DB được tạo ra
    assert os.path.exists(db_path)
    
    # 3. Test thêm Location vào DB
    loc = Location(id=None, name="Eldoria Great Hall", description="A grand ancient hall", atmosphere="Mystical")
    added_loc = await db.add_location_to_db(loc)
    assert added_loc is True

    # Truy vấn lại Location
    locs = await db.get_location_by_names(["Eldoria Great Hall"])
    assert len(locs) == 1
    assert locs[0].name == "Eldoria Great Hall"
    assert locs[0].atmosphere == "Mystical"

    # 4. Test thêm NPC vào DB (vị trí NPC phải chỉ tới Location hợp lệ do có Foreign Key)
    npc = NPC(
        id=None,
        name="Priest Joseph",
        personality="Strict but kind",
        description="Protector of the ancient temple",
        affectionate=20,
        location="Eldoria Great Hall",
        status="Normal"
    )
    added_npc = await db.add_npc_to_db(npc)
    assert added_npc is True

    # Truy vấn lại NPC
    npcs = await db.get_npc_by_names(["Priest Joseph"])
    assert len(npcs) == 1
    assert npcs[0].name == "Priest Joseph"
    assert npcs[0].location == "Eldoria Great Hall"

    # 5. Test cập nhật trạng thái NPC
    update_res = await db.update_npc_state(npc_name="Priest Joseph", affection_change=5, new_status="Tired")
    assert update_res is True

    npcs_updated = await db.get_npc_by_names(["Priest Joseph"])
    assert npcs_updated[0].affectionate == 25
    assert npcs_updated[0].status == "Tired"

    # 6. Test thêm Memory vào DB
    memory = Memory(location="Eldoria Great Hall", text="Joseph told you the Eldoria legend", game_turn=2)
    memory_id = await db.add_memory_to_db(memory)
    assert isinstance(memory_id, int)
    assert memory_id > 0

    # Lấy memory bằng ID
    mems = await db.get_memories_by_ids([memory_id])
    assert len(mems) == 1
    assert mems[0].text == "Joseph told you the Eldoria legend"

    # 7. Test liên kết Memory với NPC
    await db.link_memory_to_npc(npc_name="Priest Joseph", memory_id=memory_id)
    
    # Truy vấn memory thông qua tên NPC
    linked_mem_ids = await db.get_recent_memories_by_npc(npc_name="Priest Joseph", limit=5)
    assert memory_id in [item['id'] for item in linked_mem_ids]

    # 8. Test Fuzzy Search (Tìm kiếm mờ)
    search_results = await db.search_entities_by_query(query="Joseph")
    assert len(search_results["npcs"]) == 1
    assert search_results["npcs"][0].name == "Priest Joseph"

    search_results_loc = await db.search_entities_by_query(query="Hall")
    assert len(search_results_loc["locations"]) == 1
    assert search_results_loc["locations"][0].name == "Eldoria Great Hall"

    # 9. Test Reset Database
    await db.reset_database()
    
    all_npcs = await db.get_all_npcs()
    all_locs = await db.get_all_locations()
    assert len(all_npcs) == 0
    assert len(all_locs) == 0

    # 10. Đóng kết nối
    await db.conn.close()
