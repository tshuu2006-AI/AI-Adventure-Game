import random
from world.Entity import NPC

class NPCSpawner:
    """
    Class chuyên chịu trách nhiệm quyết định và sinh ra NPC.
    Nó đứng giữa Orchestration và các phương pháp sinh (AI hoặc Random).
    """
    def __init__(self, ai_agent):
        self.ai_agent = ai_agent  # Nhận NPCAgent từ Orchestrator truyền vào
        
        # Dữ liệu cho Procedural Generation
        self.first_names = ["Kael", "Lyra", "Gorn", "Elara", "Darius"]
        self.last_names = ["Ironfoot", "Shadow", "Sunwalker", "Storm"]
        self.traits = ["Nóng nảy", "Tham lam", "Nhát gan", "Hào sảng"]
        self.jobs = ["Lính canh đang tuần tra", "Thương gia", "Kẻ lang thang"]

    async def spawn(self, is_important_event: bool, world_state, player_state, rag_context: str, recent_story: str) -> NPC:
        """Hàm logic chính để Orchestrator gọi."""
        location = player_state.currentLocation.name
        atmosphere = player_state.currentLocation.state

        # Tỷ lệ 30% hoặc event quan trọng -> Gọi AI có RAG
        if is_important_event or random.random() < 0.3:
            print("[NPC Spawner] Gọi AI thiết kế nhân vật có RAG...")
            npc_data = await self.ai_agent.generate_npc(
                world_mission=world_state.mission,
                world_conflict=world_state.core_conflict,
                rag_context=rag_context,
                location_name=location,
                atmosphere=atmosphere,
                recent_story=recent_story
            )
            return NPC(
                id=None, 
                name=npc_data.get('name', 'Kẻ Vô Danh'), 
                personality=npc_data.get('personality', 'Bình thường'),
                description=npc_data.get('description', 'Không rõ'), 
                affectionate=npc_data.get('affectionate', 0),
                location=location, 
                status=npc_data.get('status', 'Bình thường')
            )
        else:
            # 70% dùng thuật toán Random
            print("[NPC Spawner] Sinh NPC phụ bằng thuật toán ngẫu nhiên...")
            return self._generate_random(location)

    def _generate_random(self, location_name: str) -> NPC:
        """Hàm nội bộ (Helper) sinh NPC ngẫu nhiên."""
        name = f"{random.choice(self.first_names)} {random.choice(self.last_names)}"
        trait = random.choice(self.traits)
        job = random.choice(self.jobs)
        
        return NPC(
            id=None, name=name, personality=trait,
            description=f"Một {job} với vẻ mặt {trait.lower()}.",
            affectionate=random.randint(-3, 3),
            location=location_name, status="Bình thường", image_path=None
        )