import pytest
from world.Entity import (
    BaseEntity, BaseItem, ConsumableItem, WeaponItem, 
    QuestItem, MiscellaneousItem, Quest, Location, NPC, Memory
)

def test_base_entity_initialization():
    entity = BaseEntity(id=1, name="Cổng cổ xưa", type="object", description="Một chiếc cổng làm từ đá cổ xưa")
    assert entity.id == 1
    assert entity.name == "Cổng cổ xưa"
    assert entity.type == "object"
    assert entity.description == "Một chiếc cổng làm từ đá cổ xưa"

def test_consumable_item_initialization():
    # Trường hợp truyền đầy đủ effect
    effect = {"hp": 50, "strength": 5}
    potion = ConsumableItem(id=2, name="Bình máu lớn", description="Hồi phục HP và tăng sức mạnh", effect=effect)
    
    assert potion.id == 2
    assert potion.name == "Bình máu lớn"
    assert potion.item_type == "consumable"
    assert potion.effect["hp"] == 50
    assert potion.effect["strength"] == 5
    assert potion.effect["defense"] == 0  # Giá trị mặc định là 0
    assert potion.effect["agility"] == 0

    # Trường hợp không truyền effect nào (rỗng)
    empty_potion = ConsumableItem(id=3, name="Nước lã", description="Nước tinh khiết", effect={})
    assert empty_potion.effect["hp"] == 0
    assert empty_potion.effect["strength"] == 0

def test_weapon_item_initialization():
    sword = WeaponItem(
        id=4, 
        name="Thánh kiếm Eldoria", 
        description="Vũ khí huyền thoại", 
        base_damage=100, 
        modifiers={"strength": 15}, 
        status_effect="Burn", 
        proc_chance=0.25
    )
    assert sword.id == 4
    assert sword.name == "Thánh kiếm Eldoria"
    assert sword.item_type == "weapon"
    assert sword.base_damage == 100
    assert sword.modifiers["strength"] == 15
    assert sword.status_effect == "Burn"
    assert sword.proc_chance == 0.25

    # Vũ khí cơ bản mặc định
    fist = WeaponItem(id=5, name="Nắm đấm thép", description="Tay không chiến đấu")
    assert fist.base_damage == 0
    assert fist.modifiers == {}
    assert fist.status_effect is None
    assert fist.proc_chance == 0.0

def test_quest_item_initialization():
    key = QuestItem(id=6, name="Chìa khóa ngục tối", description="Dùng để mở cửa phòng giam", quest="Quest_Mở_Cửa")
    assert key.id == 6
    assert key.name == "Chìa khóa ngục tối"
    assert key.item_type == "quest"
    assert key.quest == "Quest_Mở_Cửa"

def test_miscellaneous_item_initialization():
    junk = MiscellaneousItem(id=7, name="Đá vụn", description="Một mảnh đá không có giá trị")
    assert junk.id == 7
    assert junk.name == "Đá vụn"
    assert junk.item_type == "miscellaneous"

def test_quest_initialization():
    objectives = ["Tìm chìa khóa", "Giải cứu công chúa", "Tiêu diệt rồng"]
    quest = Quest(
        id=10, 
        name="Giải cứu vương quốc", 
        description="Nhiệm vụ cao cả của người anh hùng", 
        objectives=objectives, 
        give_by="Nhà vua", 
        rewards=["1000 Gold", "Thánh kiếm"]
    )
    assert quest.id == 10
    assert quest.name == "Giải cứu vương quốc"
    assert quest.description == "Nhiệm vụ cao cả của người anh hùng"
    assert quest.objectives == objectives
    assert quest.is_finished == [0, 0, 0]  # Khởi tạo danh mục mục tiêu chưa hoàn thành
    assert quest.give_by == "Nhà vua"
    assert quest.rewards == ["1000 Gold", "Thánh kiếm"]
    assert quest.status == "available"

def test_location_initialization():
    loc = Location(id=20, name="Rừng thiêng", description="Nơi sinh sống của các tinh linh rừng", atmosphere="Huyền bí", image_path="images/forest.png")
    assert loc.id == 20
    assert loc.name == "Rừng thiêng"
    assert loc.description == "Nơi sinh sống của các tinh linh rừng"
    assert loc.atmosphere == "Huyền bí"
    assert loc.image_path == "images/forest.png"

def test_npc_initialization():
    npc = NPC(
        id=30, 
        name="Elara", 
        personality="Thân thiện, ham học hỏi", 
        description="Một nữ phù thủy trẻ tài năng", 
        affectionate=50, 
        location="Thành phố Eldoria", 
        status="Bình thường",
        image_path="images/elara.png"
    )
    assert npc.id == 30
    assert npc.name == "Elara"
    assert npc.personality == "Thân thiện, ham học hỏi"
    assert npc.description == "Một nữ phù thủy trẻ tài năng"
    assert npc.affectionate == 50
    assert npc.location == "Thành phố Eldoria"
    assert npc.status == "Bình thường"
    assert npc.image_path == "images/elara.png"

def test_memory_dataclass():
    mem = Memory(location="Thị trấn khởi đầu", text="Người chơi nói chuyện với Elara", game_turn=1)
    assert mem.location == "Thị trấn khởi đầu"
    assert mem.text == "Người chơi nói chuyện với Elara"
    assert mem.game_turn == 1
    assert mem.id is None  # Giá trị mặc định
