import os
import sys
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)
os.chdir(BASE_DIR)

GAME_ROOT_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
SAVE_DIR = os.path.join(GAME_ROOT_DIR, "SaveData")
os.makedirs(SAVE_DIR, exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)

import base64
import re
from dotenv import load_dotenv

env_path = os.path.join(SAVE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True)
else:
    load_dotenv()

from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
# Import Orchestrator từ cấu trúc mới
from engine.Orchestration import GameOrchestrator
from engine.Utils.logger import game_logger
from world.Entity import NPC

import asyncio
import httpx
from groq import Groq
from google import genai

def safe_key(key: str) -> str:
    return key if key and key.strip() else "DUMMY_KEY_TO_PREVENT_BUG"

app = FastAPI()

current_config = {
    "mode": "default",       # "default" hoặc "custom"
    "cloud_provider": "groq",# Hoặc "custom_key"
    "cloud_key": "",
    "local_provider": "gemini", 
    "local_model_or_key": ""
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Đảm bảo các thư mục cần thiết luôn tồn tại trước khi khởi tạo
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)

# Khởi tạo Bộ não trung tâm
orchestrator = GameOrchestrator(
    db_path=os.path.join(SAVE_DIR, "eldoria.db"),
    db_folder=SAVE_DIR,
    vector_model_path="all-MiniLM-L6-v2", 
    groq_api_key=safe_key(os.getenv("GROQ_API_KEY", "")), 
    gemini_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""))
)

# ==========================================
# CÁC HÀM TIỆN ÍCH (HELPER)
# ==========================================
# Gom cụm logic xuất dữ liệu runtime để ghi thành file JSON

def image_to_base64_with_default(image_path, is_item=False):
    """(Req 4) Chuyển ảnh sang Base64, tự động bọc đường dẫn tuyệt đối"""
    if image_path:
        if not os.path.isabs(image_path):
            image_path = os.path.join(BASE_DIR, image_path)

        if os.path.exists(image_path):
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    
    if is_item:
        default_item_path = os.path.join(BASE_DIR, "static", "default_item.png")
        if os.path.exists(default_item_path):
            with open(default_item_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    return ""

def build_inventory_payload():
    """Đồng bộ túi đồ chuẩn từ InventoryManager (Khắc phục xé chuỗi & Nhầm Type)"""
    try:
        payload = []
        inv_manager = orchestrator.player_state.inventory_manager
        
        # 1. Lấy thẳng danh sách đối tượng Item (Không lấy chuỗi String)
        all_items = inv_manager.get_all_item()
        
        # Dùng set để ghi nhớ những món đồ đã đóng gói, tránh trùng lặp
        seen_names = set()
        
        for item_obj in all_items:
            name = getattr(item_obj, 'name', 'Vô danh')
            
            # Khử trùng lặp: Nếu tên này chưa từng xuất hiện thì mới xử lý
            if name not in seen_names:
                seen_names.add(name)
                
                # 🌟 SỬA LỖI TYPE: Phải gọi 'item_type' thay vì 'type'
                raw_type = getattr(item_obj, 'item_type', 'miscellaneous')
                safe_type = str(raw_type).strip().lower() if raw_type else 'miscellaneous'
                
                payload.append({
                    "name": name,
                    "type": safe_type, # Bây giờ nó sẽ ra đúng 'weapon', 'consumable'...
                    "description": getattr(item_obj, 'description', 'Chưa rõ công dụng.'),
                    "quote": getattr(item_obj, 'quote', ''),
                    "image_b64": image_to_base64_with_default(getattr(item_obj, 'image_path', None), is_item=True)
                })
                game_logger.info(f"Tên vật phẩm: {getattr(item_obj, 'name', name)}, loại: {safe_type}")
                
        return payload
    except Exception as e:
        print(f"❌ Lỗi tải túi đồ: {e}")
        return []

def parse_story_into_segments(full_text):
    """Cắt text dựa trên tag [NPC_TALK: Tên] và [PLAYER_TALK] từ LLM"""
    pattern = r'\[(NPC_TALK|PLAYER_TALK)(?::\s*([^\]]*))?\](.*?)\[/\1\]'

    # 🌟 1. NẾU LLM KHÔNG DÙNG TAG NÀO (VD: Prologue), GỌI FALLBACK NGAY LẬP TỨC
    if not re.search(pattern, full_text):
        return parse_story_fallback(full_text)

    segments = []
    last_end = 0
    for match in re.finditer(pattern, full_text, flags=re.DOTALL):
        # 2. XỬ LÝ LỜI DẪN CHUYỆN: Cắt nhỏ theo đoạn văn (\n) để Unity bắt click chuột
        narration = full_text[last_end:match.start()].strip()
        if narration:
            for p in narration.split('\n'):
                if p.strip():
                    segments.append({"speaker": "Master", "text": p.strip()})

        # 3. XỬ LÝ THOẠI NHÂN VẬT (Giữ nguyên logic cũ)
        tag_type = match.group(1)
        speaker_name = match.group(2).strip() if match.group(2) else ""
        dialogue = match.group(3).strip()

        if dialogue:
            if tag_type == "NPC_TALK":
                final_speaker = speaker_name if speaker_name else "NPC"
                segments.append({"speaker": final_speaker, "text": f'"{dialogue}"'})
            elif tag_type == "PLAYER_TALK":
                segments.append({"speaker": "Player", "text": f'"{dialogue}"'})

        last_end = match.end()

    # 4. LỜI DẪN CHUYỆN CÒN SÓT Ở CUỐI: Vẫn cắt nhỏ theo đoạn văn
    remaining_narration = full_text[last_end:].strip()
    if remaining_narration:
        for p in remaining_narration.split('\n'):
            if p.strip():
                segments.append({"speaker": "Master", "text": p.strip()})

    return segments


def parse_story_fallback(full_text):
    """Fallback an toàn: Cắt text dựa trên ngoặc kép như phiên bản cũ"""
    segments = []
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]
    for p in paragraphs:
        parts = re.split(r'(".*?")', p)
        for part in parts:
            part = part.strip()
            if not part: continue

            if part.startswith('"') and part.endswith('"'):
                dialogue = part[1:-1].strip()
                if dialogue:
                    segments.append({"speaker": "NPC", "text": f'"{dialogue}"'})
            else:
                segments.append({"speaker": "Master", "text": part})
    return segments

# ==========================================
# BACKGROUND TASKS & UTILS
# ==========================================
async def verify_groq_key(api_key: str) -> bool:
    try:
        def test():
            client = Groq(api_key=api_key)
            client.models.list()
            return True
        return await asyncio.to_thread(test)
    except Exception:
        return False

async def verify_gemini_key(api_key: str) -> bool:
    try:
        def test():
            client = genai.Client(api_key=api_key)
            client.models.list()
            return True
        return await asyncio.to_thread(test)
    except Exception:
        return False

async def verify_ollama_model(model_name: str) -> bool:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=3.0)
            if response.status_code == 200:
                available_models = response.json().get("models", [])
                names = [m.get("name") for m in available_models]
                return any(model_name.lower() in name.lower() for name in names)
    except Exception:
        return False
    return False
# 🌟 Bổ sung tham số is_new_game=False
async def background_post_turn_processing(player_input, story_response, is_new_game=False):
    """Hàm này sẽ chạy ngầm sau khi Text đã được ném về Unity"""
    try:
        # 🌟 NẾU LÀ GAME MỚI -> ÉP KAGGLE VẼ ẢNH ĐỊA ĐIỂM XUẤT PHÁT
        if is_new_game:
            curr_loc = orchestrator.player_state.currentLocation
            if curr_loc:
                if not curr_loc.image_path:
                    game_logger.info(f"🎨 [Turn 0] Bắt đầu vẽ ảnh địa điểm xuất phát: {curr_loc.name}")
                    img_path = await orchestrator.image_manager.get_or_create_location_image(
                        location_name=curr_loc.name,
                        description=curr_loc.description,
                        atmosphere=curr_loc.atmosphere
                    )
                    if img_path:
                        curr_loc.image_path = img_path
                
                # 🌟 ĐƯA LỆNH LƯU DATABASE VÀO ĐÂY (Lúc này object đã có đầy đủ ảnh)
                await orchestrator.db.add_location_to_db(curr_loc)

                for npc in orchestrator.player_state.currentNPCs:
                    if not npc.image_path:
                        game_logger.info(f"🎨 [Turn 0] Bắt đầu vẽ ảnh NPC: {npc.name}")
                        npc_img = await orchestrator.image_manager.get_or_create_npc_image(
                            npc_name=npc.name,
                            description=npc.description
                        )
                        if npc_img:
                            npc.image_path = npc_img
                    
                    # Giờ thì lưu thoải mái không sợ lỗi Khóa Ngoại nữa!
                    await orchestrator.db.add_npc_to_db(npc)

        # Vẫn cho chạy trích xuất ngầm bình thường để bắt NPC/Item từ đoạn Prologue
        ep_data, scene_emotion = await orchestrator.state_sys.process_background_tasks(player_input, story_response)
        orchestrator.current_emotion = scene_emotion

        await orchestrator.quest_sys.evaluate_turn(player_input, story_response)

        encountered = [n.name for n in orchestrator.player_state.currentNPCs]
        await orchestrator.memory_sys.save_turn(
            player_input=player_input,
            story_response=story_response,
            episode_data=ep_data,
            current_location_name=orchestrator.player_state.currentLocation.name,
            encountered_npc_names=encountered
        )
        game_logger.info("Hoàn tất xử lý ngầm (State & Memory)!")
    except Exception as e:
        game_logger.error(f"Lỗi chạy ngầm: {e}", exc_info=True)
    finally:
        orchestrator.is_processing_bg = False

# ==========================================
# UNITY SYSTEM ENDPOINTS
# ==========================================
@app.get("/api/ping")
async def ping():
    """Unity sẽ gọi hàm này liên tục để xem Server đã khởi động xong chưa"""
    return JSONResponse(content={"status": "ok", "message": "Server is ready"})

@app.post("/api/shutdown")
async def shutdown():
    """Tắt Server an toàn khi Unity đóng"""
    os._exit(0)

# ==========================================
# API ENDPOINTS CHÍNH
# ==========================================

@app.post("/api/new_game")
async def new_game(idea: str = Form(...), bg_tasks: BackgroundTasks = BackgroundTasks()):
    """Khởi tạo Game Loop mới giống hệt run() trong Orchestration"""
    try:
        orchestrator.is_processing_bg = True
        orchestrator.player_state.currentNPCs = []
        orchestrator.player_state.inventory = [] # Dọn list cũ
        
        # 🌟 DỌN SẠCH KHO ĐỒ KHI TẠO GAME MỚI
        inv_manager = orchestrator.player_state.inventory_manager
        inv_manager.equipped_weapon = None
        
        old_items = list(inv_manager.get_all_item_names())
        for old_item_name in old_items:
            obj = inv_manager.get_item_by_name(old_item_name)
            if obj:
                inv_manager.remove_item(obj)

        await orchestrator.db.connect()
        await orchestrator.db.reset_database()
        await orchestrator.db.create_tables()
        orchestrator.image_manager.clear_image_folders()

        world_bible_dir = os.path.join(orchestrator.db.db_folder, "world_bible.json")
        world_bible = await orchestrator.story_director.create_world_bible(player_idea=idea, path=world_bible_dir)

        reqs = world_bible.get("system_requirements", {})
        orchestrator.world_state.name = reqs.get("world_name", "Vùng đất vô danh")
        orchestrator.world_state.type = reqs.get("world_type", "Fantasy")
        orchestrator.world_state.theme_and_tone = reqs.get("theme_and_tone", "Tối tăm")
        orchestrator.world_state.core_conflict = reqs.get("core_conflict", "Sinh tồn")
        orchestrator.world_state.mission = reqs.get("world_mission", "Sống sót")
        orchestrator.world_state.dynamic_vocabulary = world_bible.get("dynamic_vocabulary", {})
        
        starting_loc = await orchestrator.story_director.create_starting_location(
            orchestrator.world_state.name, 
            orchestrator.world_state.type, 
            orchestrator.world_state.theme_and_tone
        )
        orchestrator.player_state.currentLocation = starting_loc
        # await orchestrator.db.add_location_to_db(starting_loc)
        starting_npcs = await orchestrator.story_director.initialize_key_npcs(
            world_name=orchestrator.world_state.name,
            world_type=orchestrator.world_state.type,
            world_theme=orchestrator.world_state.theme_and_tone,
            world_conflict=orchestrator.world_state.core_conflict,
            world_mission=orchestrator.world_state.mission
        )
        
        for npc_data in starting_npcs:
            npc_obj = NPC(
                id=None,
                name=npc_data.get("name", "Vô danh"),
                personality=npc_data.get("personality", "Bí ẩn"),
                description=npc_data.get("description", "Không rõ"),
                affectionate=npc_data.get("affectionate", 0),
                location=starting_loc.name, #Ép location
                status=npc_data.get("status", "Bình thường")
            )
            # await orchestrator.db.add_npc_to_db(npc_obj)
            orchestrator.player_state.currentNPCs.append(npc_obj)

        await orchestrator.quest_sys.initialize_main_quest(
            world_state=orchestrator.world_state,
            starting_npcs=orchestrator.player_state.currentNPCs
        )
        
        story_response = ""
        # 🌟 Truyền thêm tham số world_bible_dir vào đây:
        async for chunk in orchestrator.story_director.initialize_story(starting_loc, world_bible_dir=world_bible_dir):
            story_response += chunk

        segments = parse_story_into_segments(story_response)

        choices = await orchestrator.story_director.generate_player_choices(
            current_location_name=starting_loc.name, 
            encountered_npc_name=[], 
            recent_story_text=story_response,
            active_quest=orchestrator.player_state.active_quest,
            quest_items=getattr(orchestrator.player_state, 'quest_items', [])
        )
        orchestrator.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        bg_tasks.add_task(background_post_turn_processing, "[Bắt đầu trò chơi]", story_response, is_new_game=True)

        return JSONResponse(content={
            "segments": segments,
            "choices": choice_texts,
            "bg_image_b64": "",
            "char_image_b64": "",
            "inventory": []
        })
    except Exception as e:
        game_logger.error("❌ LỖI CRASH KHI TẠO NEW GAME:", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/play")
async def play_turn(action: str = Form(...), bg_tasks: BackgroundTasks = BackgroundTasks()):
    """Xử lý lượt đi (Giống _process_game_turn)"""
    try:
        orchestrator.is_processing_bg = True
        directive = await orchestrator.action_sys.get_system_directive(action)
        hybrid_ctx, npcs_ctx = await orchestrator.memory_sys.get_hybrid_context(action, orchestrator.player_state)

        story_response = ""
        async for chunk in orchestrator.story_director.narrate_turn(
                action, orchestrator.world_state, orchestrator.player_state, npcs_ctx, hybrid_ctx, directive):
            story_response += chunk
        
        segments = parse_story_into_segments(story_response)

        choices = await orchestrator.story_director.generate_player_choices(
            current_location_name=orchestrator.player_state.currentLocation.name,
            encountered_npc_name=[n.name for n in orchestrator.player_state.currentNPCs],
            recent_story_text=story_response,
            active_quest=orchestrator.player_state.active_quest,
            quest_items=getattr(orchestrator.player_state, 'quest_items', [])
        )
        orchestrator.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        bg_tasks.add_task(background_post_turn_processing, action, story_response)

        return JSONResponse(content={
            "segments": segments,
            "choices": choice_texts,
            "bg_image_b64": "", 
            "char_image_b64": "",
            "inventory": []
        })
    except Exception as e:
        game_logger.error("❌ LỖI CRASH KHI TẠO NEW GAME:", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/poll_updates")
async def poll_updates():
    """(Req 1) API CHUYÊN DỤNG CHO UNITY GỌI NGẦM."""
    try:
        curr_loc = orchestrator.player_state.currentLocation
        bg_img = image_to_base64_with_default(curr_loc.image_path if curr_loc else None)
        
        # 🌟 NÂNG CẤP: Lấy ảnh của TẤT CẢ NPC trong cảnh hiện tại
        npc_images_payload = []
        if orchestrator.player_state.currentNPCs:
            for npc in orchestrator.player_state.currentNPCs:
                img_b64 = image_to_base64_with_default(npc.image_path)
                if img_b64:
                    npc_images_payload.append({
                        "name": npc.name,
                        "image_b64": img_b64
                    })
            
        inv_payload = build_inventory_payload()
        emotion = getattr(orchestrator, "current_emotion", "bình thường")

        current_hp = orchestrator.player_state.hp
        max_hp = orchestrator.player_state.max_hp
        equipped_weapon = orchestrator.player_state.inventory_manager.equipped_weapon
        weapon_name = equipped_weapon.name if equipped_weapon else "Tay không"

        active_quest = orchestrator.player_state.active_quest
        quest_payload = None
        if active_quest:
            # Lấy mảng objectives
            raw_obj = getattr(active_quest, 'objectives', getattr(active_quest, 'objective', []))
            if isinstance(raw_obj, str): raw_obj = [raw_obj] # Đảm bảo luôn là list
            
            # Lấy mảng is_finished (nếu không có thì mặc định mảng toàn 0)
            is_fin = getattr(active_quest, 'is_finished', [0]*len(raw_obj))
            
            quest_payload = {
                "name": active_quest.name,
                "objectives": raw_obj,  # Gửi nguyên mảng chữ
                "is_finished": is_fin,  # Gửi nguyên mảng số [0, 1, 0...]
                "status": active_quest.status
            }
            
        return JSONResponse(content={
            "bg_image_b64": bg_img,
            "npc_images": npc_images_payload, 
            "inventory": inv_payload,
            "hp": current_hp,              # MỚI
            "max_hp": max_hp,              # MỚI
            "weapon": weapon_name,         # MỚI
            "emotion": emotion,
            "active_quest": quest_payload,
            "is_processing_bg": getattr(orchestrator, "is_processing_bg", False)
        })
    except Exception as e:
        print(f"Lỗi poll_updates: {e}")
        return JSONResponse(content={"bg_image_b64": "", "npc_images": [], "inventory": []})

@app.get("/api/diary")
async def get_diary():
    """(Req 3) Hoàn thiện API Diary - Có thêm Nhiệm Vụ"""
    try:
        npcs = await orchestrator.db.npc_manager.get_all()
        locations = await orchestrator.db.location_manager.get_all()

        npc_list = [{"name": n.name, "personality": getattr(n, 'personality', 'Chưa rõ'), "description": getattr(n, 'description', ''),
                     "affectionate": getattr(n, 'affectionate', 0), "location": getattr(n, 'location', 'Chưa rõ'), "status": getattr(n, 'status', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(n.image_path)} for n in npcs]

        loc_list = [{"name": l.name, "description": getattr(l, 'description', ''), "atmosphere": getattr(l, 'atmosphere', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(l.image_path)} for l in locations]

        quests_payload = []
        if getattr(orchestrator.player_state, 'quests', None):
            for q in orchestrator.player_state.quests:
                raw_obj = getattr(q, 'objectives', getattr(q, 'objective', []))
                if isinstance(raw_obj, str): raw_obj = [raw_obj]
                
                is_fin = getattr(q, 'is_finished', [0]*len(raw_obj))

                quests_payload.append({
                    "name": getattr(q, 'name', 'Nhiệm vụ ẩn'),
                    "description": getattr(q, 'description', ''),
                    "objectives": raw_obj,
                    "is_finished": is_fin,
                    "status": getattr(q, 'status', 'available'),
                    "is_active": (q == orchestrator.player_state.active_quest)
                })

        return JSONResponse(content={"npcs": npc_list, "locations": loc_list, "quests": quests_payload})
    except Exception as e:
        game_logger.error(f"❌ Lỗi tải Diary: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/quest/switch")
async def switch_quest(quest_name: str = Form(...)):
    """API để Unity ra lệnh chuyển đổi Nhiệm vụ đang theo dõi"""
    try:
        target = next((q for q in orchestrator.player_state.quests if q.name == quest_name), None)
        
        if not target:
            return JSONResponse(content={"success": False, "message": "Không tìm thấy nhiệm vụ."})
        if target == orchestrator.player_state.active_quest:
            return JSONResponse(content={"success": False, "message": "Bạn đang thực hiện nhiệm vụ này rồi!"})
        
        # Gọi hệ thống QuestProcessor chuyển đổi & Sinh lời dẫn truyện
        transition_msg = await orchestrator.quest_sys.switch_quest(
            target_quest=target, 
            recent_story="Bạn mở sổ tay và quyết định thay đổi mục tiêu hành động.", 
            current_choices=orchestrator.last_choices
        )
        return JSONResponse(content={"success": True, "message": transition_msg})
    except Exception as e:
        game_logger.error(f"Lỗi chuyển nhiệm vụ: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.get("/api/progress")
async def get_progress():
    """API để Unity lấy tiến trình Loading (Thanh Progress bar)"""
    return JSONResponse(content={
        "message": getattr(orchestrator, "progress_msg", "Đang xử lý..."),
        "percent": getattr(orchestrator, "progress_percent", 0.5)
    })

@app.post("/api/check_config")
async def check_config(
    cloud_key: str = Form(""),
    local_model_or_key: str = Form(""),
    is_ollama: str = Form("false")
):
    """Endpoint xử lý nút Check cấu hình từ Unity"""
    if not cloud_key.strip() or not local_model_or_key.strip():
        return JSONResponse(content={"success": False, "message": "Vui lòng nhập đầy đủ cả 2 trường thông tin!"})

    cloud_ok = await verify_groq_key(cloud_key.strip())
    if not cloud_ok:
        return JSONResponse(content={"success": False, "message": "❌ Cloud API Key (Groq) không hợp lệ hoặc không kết nối được!"})

    if is_ollama.lower() == "true":
        local_ok = await verify_ollama_model(local_model_or_key.strip())
        if not local_ok:
            return JSONResponse(content={"success": False, "message": "❌ Không tìm thấy mô hình Ollama này trên máy cục bộ!"})
    else:
        local_ok = await verify_gemini_key(local_model_or_key.strip())
        if not local_ok:
            return JSONResponse(content={"success": False, "message": "❌ Local API Key (Gemini) không hợp lệ hoặc không kết nối được!"})

    return JSONResponse(content={"success": True, "message": "💚 Tuyệt vời! Cả hai cấu hình đều hợp lệ và sẵn sàng sử dụng."})


@app.post("/api/settings")
async def update_settings(
    mode: str = Form(None),             # Đổi Form(...) thành Form(None) để làm tham số tùy chọn
    cloud_key: str = Form(None),
    local_model_or_key: str = Form(None),
    is_ollama: str = Form(None),
    enable_image: str = Form(None),     # Bổ sung nhận lệnh bật/tắt ảnh từ Unity
    quality: str = Form(None)           # Bổ sung nhận lệnh chất lượng ảnh từ Unity
):
    """Lưu và áp dụng cấu hình cài đặt từ Unity"""
    global current_config
    global orchestrator

    # 1. NẾU UNITY CHỈ GỬI LỆNH ĐỔI CHẤT LƯỢNG ẢNH
    if quality is not None:
        orchestrator.image_manager.api.quality = quality.lower()
        game_logger.info(f"Đã cập nhật chất lượng Ảnh thành: {quality.upper()}")
        return JSONResponse(content={"success": True, "message": "Đã đổi chất lượng Hình ảnh!"})

    # 2. NẾU UNITY CHỈ GỬI LỆNH BẬT/TẮT ẢNH
    if enable_image is not None:
        is_enabled = enable_image.lower() == "true"
        orchestrator.image_manager.api.enable_image = is_enabled
        trang_thai = "BẬT" if is_enabled else "TẮT"
        game_logger.info(f"Đã {trang_thai} tính năng vẽ ảnh.")
        return JSONResponse(content={"success": True, "message": f"Đã {trang_thai} tính năng Hình ảnh!"})

    # 3. NẾU UNITY GỬI LỆNH ĐỔI AI (LLM KEY)
    if mode is not None:
        current_config["mode"] = mode
        current_config["cloud_key"] = cloud_key.strip() if cloud_key else ""
        current_config["local_model_or_key"] = local_model_or_key.strip() if local_model_or_key else ""
        current_config["local_provider"] = "ollama" if str(is_ollama).lower() == "true" else "gemini"

        # Khởi tạo lại AI nhưng PHẢI GIỮ LẠI trạng thái bật/tắt ảnh trước đó
        old_enable_image = getattr(orchestrator.image_manager.api, 'enable_image', True)
        old_quality = getattr(orchestrator.image_manager.api, 'quality', 'medium')

        if mode == "custom":
            orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                groq_api_key=safe_key(current_config["cloud_key"]),
                gemini_api_key=safe_key(current_config["local_model_or_key"])
            )
        else:
            orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                groq_api_key=safe_key(os.getenv("GROQ_API_KEY", "")),
                gemini_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""))
            )
        
        # Nạp lại trạng thái ảnh cho Orchestrator mới
        orchestrator.image_manager.api.enable_image = old_enable_image
        orchestrator.image_manager.api.quality = old_quality

        game_logger.info(f"Đã áp dụng hệ thống AI: {mode.upper()}")
        return JSONResponse(content={"success": True, "message": "Đã lưu và áp dụng cài đặt AI mới!"})

    return JSONResponse(status_code=400, content={"error": "Không nhận được tham số hợp lệ"})

@app.post("/api/save_game")
async def save_game(slot: str = Form(...)):
    """API lưu toàn bộ Database và Memory xuống ổ cứng"""
    try:
        await orchestrator.save_manager.save_game(orchestrator, slot_name=slot)
        return JSONResponse(content={"success": True, "message": f"Đã đồng bộ AI vào {slot}"})
    except Exception as e:
        game_logger.error(f"Lỗi Save API: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/load_game")
async def load_game(slot: str = Form(...)):
    """API ghi đè Database và Memory từ file save lên hệ thống"""
    try:
        success, msg = await orchestrator.save_manager.load_game(orchestrator, slot_name=slot)
        if success:
            return JSONResponse(content={"success": True, "message": msg})
        else:
            return JSONResponse(status_code=400, content={"error": msg})
    except Exception as e:
        game_logger.error(f"Lỗi Load API: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

# ==========================================
# 🌟 CÁC API DÀNH RIÊNG CHO HỆ THỐNG TÚI ĐỒ MỚI
# ==========================================

@app.post("/api/inventory/use")
async def use_item(item_name: str = Form(...)):
    """API để Unity ra lệnh dùng vật phẩm (Hồi máu, giải độc...)"""
    try:
        inv_manager = orchestrator.player_state.inventory_manager
        # Gọi thẳng logic đã viết rất chuẩn của bạn
        result_msg = inv_manager.use_consumable(item_name, orchestrator.player_state)
        return JSONResponse(content={"success": True, "message": result_msg})
    except Exception as e:
        game_logger.error(f"Lỗi dùng vật phẩm: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/inventory/equip")
async def equip_item(item_name: str = Form(...)):
    """API để Unity ra lệnh trang bị vũ khí"""
    try:
        inv_manager = orchestrator.player_state.inventory_manager
        result_msg = inv_manager.equip_weapon(item_name)
        return JSONResponse(content={"success": True, "message": result_msg})
    except Exception as e:
        game_logger.error(f"Lỗi trang bị: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/inventory/craft")
async def craft_item(items_str: str = Form(...), action_detail: str = Form(...)):
    """
    API để Unity ra lệnh chế tạo. 
    - items_str: chuỗi các tên vật phẩm cách nhau bằng dấu phẩy (VD: 'Thanh gỗ, Đá nhọn')
    - action_detail: mô tả ý định ghép (VD: 'Dùng dây leo buộc đá vào gỗ')
    """
    try:
        inv_manager = orchestrator.player_state.inventory_manager
        target_items = []
        
        # Tách chuỗi để lấy ra các Object Item thật từ Balo
        for name in items_str.split(","):
            if not name.strip(): continue
            item_obj = inv_manager.get_item_by_name(name.strip())
            if item_obj:
                target_items.append(item_obj)

        if len(target_items) < 1:
            return JSONResponse(content={"success": False, "message": "⚠️ Vật phẩm không tồn tại trong túi đồ!"})

        # Gọi ItemAgent xử lý (Tốn API LLM)
        craft_result = await orchestrator.item_sys.interact(
            item_list=target_items,
            action_details=action_detail,
            image_manager=orchestrator.image_manager
        )
        return JSONResponse(content={"success": True, "message": craft_result})
    except Exception as e:
        game_logger.error(f"Lỗi chế tạo: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    import uvicorn
    # QUAN TRỌNG: Phải set reload=False khi đóng gói hoặc chạy qua Unity để tránh lỗi vòng lặp tiến trình
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="warning")