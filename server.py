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
from engine.Utils.TextFormatter import TextFormatter

env_path = os.path.join(SAVE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(dotenv_path=env_path, override=True)
else:
    load_dotenv()

from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

app.state.orchestrator = GameOrchestrator(
    db_path=os.path.join(SAVE_DIR, "eldoria.db"),
    db_folder=SAVE_DIR,
    vector_model_path="all-MiniLM-L6-v2",
    groq_api_key=safe_key(os.getenv("GROQ_API_KEY", "")),
    gemini_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""))
)

# Đảm bảo các thư mục cần thiết luôn tồn tại trước khi khởi tạo
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)

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
    """Đồng bộ túi đồ chuẩn từ Orchestrator Wrapper"""
    try:
        payload = []
        orc = app.state.orchestrator
        
        all_items = orc.get_all_items()
        
        seen_names = set()
        for item_obj in all_items:
            # Bảo vệ nếu lỡ có chuỗi lọt vào
            if isinstance(item_obj, str): 
                continue

            name = getattr(item_obj, 'name', 'Vô danh')
            
            if name not in seen_names:
                seen_names.add(name)
                raw_type = getattr(item_obj, 'item_type', 'miscellaneous')
                safe_type = str(raw_type).strip().lower() if raw_type else 'miscellaneous'
                
                payload.append({
                    "name": name,
                    "type": safe_type,
                    "description": getattr(item_obj, 'description', 'Chưa rõ công dụng.'),
                    "quote": getattr(item_obj, 'quote', ''),
                    "image_b64": image_to_base64_with_default(getattr(item_obj, 'image_path', None), is_item=True)
                })
                
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

async def background_post_turn_processing(player_input, story_response, is_new_game=False):
    """Hàm này sẽ chạy ngầm sau khi Text đã được ném về Unity"""
    orc = app.state.orchestrator
    try:
        if is_new_game:
            curr_loc = orc.get_current_location() # Dùng hàm bọc
            if curr_loc:
                if not curr_loc.image_path:
                    game_logger.info(f"🎨 [Turn 0] Bắt đầu vẽ ảnh địa điểm xuất phát: {curr_loc.name}")
                    img_path = await orc.image_manager.get_or_create_location_image(
                        location_name=curr_loc.name,
                        description=curr_loc.description,
                        atmosphere=curr_loc.atmosphere
                    )
                    if img_path:
                        curr_loc.image_path = img_path
                
                await orc.add_location_to_db(curr_loc) # Dùng hàm bọc

                npcs = orc.player_state.currentNPCs 
                for npc in npcs:
                    if not getattr(npc, 'image_path', None):
                        game_logger.info(f"🎨 [Turn 0] Bắt đầu vẽ ảnh NPC: {npc.name}")
                        npc_img = await orc.image_manager.get_or_create_npc_image(
                            npc_name=npc.name,
                            description=npc.description
                        )
                        if npc_img:
                            npc.image_path = npc_img
                    
                    await orc.db.add_npc_to_db(npc)

        # 🌟 GỌI QUA HÀM BỌC (Đã có chữ 'return' nên không còn bị crash NoneType)
        ep_data, scene_emotion = await orc.state_process_background_tasks(player_input, story_response)
        orc.current_emotion = scene_emotion

        await orc.quest_evaluate_turn(player_input, story_response) # Dùng hàm bọc

        encountered = [n.name for n in orc.get_current_npcs()] # Dùng hàm bọc
        await orc.memory_save_turn( # Dùng hàm bọc
            player_input=player_input,
            story_response=story_response,
            episode_data=ep_data,
            current_location_name=orc.get_current_location_name(),
            encountered_npc_names=encountered
        )
        game_logger.info("Hoàn tất xử lý ngầm (State & Memory)!")
    except Exception as e:
        game_logger.error(f"Lỗi chạy ngầm: {e}", exc_info=True)
    finally:
        orc.is_processing_bg = False

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
    """Khởi tạo Game Loop mới siêu gọn nhẹ"""
    try:
        orc = app.state.orchestrator
        orc.is_processing_bg = True

        # 1. Giao toàn bộ việc nặng (Dọn dẹp, tạo thế giới, sinh truyện) cho Orchestrator
        story_response = await orc.setup_new_game_api(player_idea=idea)

        # 2. Định dạng text để gửi cho Unity UI
        segments = TextFormatter.parse_story_into_segments(story_response)

        # 3. Gọi AI sinh Menu lựa chọn từ kết quả Prologue
        choices = await orc.story_director.generate_player_choices(
            current_location_name=orc.get_current_location_name(),
            encountered_npc_name=[],
            recent_story_text=story_response,
            active_quest=orc.player_state.active_quest,
            quest_items=orc.player_state.quest_items
        )
        orc.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        # 4. Kích hoạt tác vụ ngầm (Trích xuất state, tải ảnh, ...)
        bg_tasks.add_task(background_post_turn_processing, "[Bắt đầu trò chơi]", story_response, is_new_game=True)

        # 5. Trả về cho Client
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
    """Xử lý lượt đi (Chuẩn Clean Code)"""
    try:
        orc = app.state.orchestrator
        orc.is_processing_bg = True

        # 1. Giao toàn bộ việc phân tích Action, gọi RAG Memory và sinh truyện cho Orchestrator
        story_response = await orc.generate_turn_narrative_api(action)

        # 2. Phân rã văn bản (Dùng Class tiện ích)
        segments = TextFormatter.parse_story_into_segments(story_response)

        # 3. Sinh Menu Lựa chọn (Giao tiếp qua các hàm bọc an toàn)
        choices = await orc.story_director.generate_player_choices(
            current_location_name=orc.get_current_location_name(),
            encountered_npc_name=orc.get_encountered_npc_names(),
            recent_story_text=story_response,
            active_quest=orc.player_state.active_quest,
            quest_items=orc.player_state.quest_items
        )
        orc.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        # 4. Kích hoạt Background Tasks (Trích xuất state, lưu DB)
        bg_tasks.add_task(background_post_turn_processing, action, story_response)

        return JSONResponse(content={
            "segments": segments,
            "choices": choice_texts,
            "bg_image_b64": "",
            "char_image_b64": "",
            "inventory": []
        })
    except Exception as e:
        # Đã sửa lại nội dung log cho đúng ngữ cảnh
        game_logger.error("❌ LỖI CRASH TẠI LƯỢT ĐI (PLAY TURN):", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/api/poll_updates")
async def poll_updates():
    try:
        orc = app.state.orchestrator
        curr_loc = orc.get_current_location()
        bg_img = image_to_base64_with_default(curr_loc.image_path if curr_loc else None)
        
        # 🌟 NÂNG CẤP: Lấy ảnh của TẤT CẢ NPC trong cảnh hiện tại
        npc_images_payload = []
        npcs = orc.get_current_npcs()
        if npcs:
            for npc in npcs:
                img_b64 = image_to_base64_with_default(npc.image_path)
                if img_b64:
                    npc_images_payload.append({
                        "name": npc.name,
                        "image_b64": img_b64
                    })
            
        inv_payload = build_inventory_payload()
        emotion = getattr(orc, "current_emotion", "bình thường")

        current_hp = orc.get_current_hp()
        max_hp = orc.get_max_hp()
        equipped_weapon = orc.get_equipped_weapon()
        weapon_name = equipped_weapon.name if equipped_weapon else "Tay không"

        t_stats = orc.player_state.stats.total_stats
        strength_val = t_stats.get("strength", 0)
        agility_val = t_stats.get("agility", 0)
        defense_val = t_stats.get("defense", 0)
        intelligence_val = t_stats.get("intelligence", 0)

        active_quest = orc.get_active_quest()
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
            "strength": strength_val,
            "agility": agility_val,
            "defense": defense_val,
            "intelligence": intelligence_val,
            "emotion": emotion,
            "active_quest": quest_payload,
            "is_processing_bg": getattr(orc, "is_processing_bg", False)
        })
    except Exception as e:
        print(f"Lỗi poll_updates: {e}")
        return JSONResponse(content={"bg_image_b64": "", "npc_images": [], "inventory": []})

@app.get("/api/diary")
async def get_diary():
    """(Req 3) Hoàn thiện API Diary - Có thêm Nhiệm Vụ"""
    try:
        orc = app.state.orchestrator
        npcs = await orc.get_all_npcs()
        locations = await orc.get_all_locations()

        npc_list = [{"name": n.name, "personality": getattr(n, 'personality', 'Chưa rõ'), "description": getattr(n, 'description', ''),
                     "affectionate": getattr(n, 'affectionate', 0), "location": getattr(n, 'location', 'Chưa rõ'), "status": getattr(n, 'status', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(n.image_path)} for n in npcs]

        loc_list = [{"name": l.name, "description": getattr(l, 'description', ''), "atmosphere": getattr(l, 'atmosphere', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(l.image_path)} for l in locations]

        quests_payload = []
        all_quests = orc.get_all_quests()
        for q in all_quests:
            raw_obj = getattr(q, 'objectives', getattr(q, 'objective', []))
            if isinstance(raw_obj, str): raw_obj = [raw_obj]

            is_fin = getattr(q, 'is_finished', [0]*len(raw_obj))

            quests_payload.append({
                "name": getattr(q, 'name', 'Nhiệm vụ ẩn'),
                "description": getattr(q, 'description', ''),
                "objectives": raw_obj,
                "is_finished": is_fin,
                "status": getattr(q, 'status', 'available'),
                "is_active": (q == orc.get_active_quest())
            })

        return JSONResponse(content={"npcs": npc_list, "locations": loc_list, "quests": quests_payload})
    except Exception as e:
        game_logger.error(f"❌ Lỗi tải Diary: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/quest/switch")
async def switch_quest(quest_name: str = Form(...)):
    """API để Unity ra lệnh chuyển đổi Nhiệm vụ đang theo dõi"""
    try:
        orc = app.state.orchestrator
        target = next((q for q in orc.get_all_quests() if q.name == quest_name), None)
        
        if not target:
            return JSONResponse(content={"success": False, "message": "Không tìm thấy nhiệm vụ."})
        if target == orc.get_active_quest():
            return JSONResponse(content={"success": False, "message": "Bạn đang thực hiện nhiệm vụ này rồi!"})
        
        if getattr(target, 'status', 'available') == 'available':
            target.status = 'in_progress'
        
        # Gọi hệ thống QuestProcessor chuyển đổi & Sinh lời dẫn truyện
        transition_msg = await orc.switch_quest(
            target_quest=target,
            recent_story="Bạn mở sổ tay và quyết định thay đổi mục tiêu hành động.",
            current_choices=orc.last_choices
        )
        return JSONResponse(content={"success": True, "message": transition_msg})
    except Exception as e:
        game_logger.error(f"Lỗi chuyển nhiệm vụ: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.get("/api/progress")
async def get_progress():
    """API để Unity lấy tiến trình Loading (Thanh Progress bar)"""
    orc = app.state.orchestrator
    return JSONResponse(content={
        "message": getattr(orc, "progress_msg", "Đang xử lý..."),
        "percent": getattr(orc, "progress_percent", 0.5)
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

    orc = app.state.orchestrator
    # 1. NẾU UNITY CHỈ GỬI LỆNH ĐỔI CHẤT LƯỢNG ẢNH
    if quality is not None:
        orc.image_manager.api.quality = quality.lower()
        game_logger.info(f"Đã cập nhật chất lượng Ảnh thành: {quality.upper()}")
        return JSONResponse(content={"success": True, "message": "Đã đổi chất lượng Hình ảnh!"})

    # 2. NẾU UNITY CHỈ GỬI LỆNH BẬT/TẮT ẢNH
    if enable_image is not None:
        is_enabled = enable_image.lower() == "true"
        orc.image_manager.api.enable_image = is_enabled
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
        old_enable_image = getattr(orc.image_manager.api, 'enable_image', True)
        old_quality = getattr(orc.image_manager.api, 'quality', 'medium')

        if mode == "custom":
            app.state.orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                groq_api_key=safe_key(current_config["cloud_key"]),
                gemini_api_key=safe_key(current_config["local_model_or_key"])
            )
        else:
            app.state.orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                groq_api_key=safe_key(os.getenv("GROQ_API_KEY", "")),
                gemini_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""))
            )
        
        # Nạp lại trạng thái ảnh cho Orchestrator mới
        orc = app.state.orchestrator
        orc.image_manager.api.enable_image = old_enable_image
        orc.image_manager.api.quality = old_quality

        game_logger.info(f"Đã áp dụng hệ thống AI: {mode.upper()}")
        return JSONResponse(content={"success": True, "message": "Đã lưu và áp dụng cài đặt AI mới!"})

    return JSONResponse(status_code=400, content={"error": "Không nhận được tham số hợp lệ"})

@app.post("/api/save_game")
async def save_game(slot: str = Form(...)):
    """API lưu toàn bộ Database và Memory xuống ổ cứng"""
    try:
        orc = app.state.orchestrator
        await orc.save_manager.save_game(orc, slot_name=slot)
        return JSONResponse(content={"success": True, "message": f"Đã đồng bộ AI vào {slot}"})
    except Exception as e:
        game_logger.error(f"Lỗi Save API: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/load_game")
async def load_game(slot: str = Form(...)):
    """API ghi đè Database và Memory từ file save lên hệ thống"""
    try:
        orc = app.state.orchestrator
        success, msg = await orc.save_manager.load_game(orc, slot_name=slot)
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
async def use_item(item_name: str = Form(...), action_detail: str = Form("")):
    """API để Unity ra lệnh dùng vật phẩm (Hỗ trợ cả Use thường và Use bằng AI)"""
    try:
        orc = app.state.orchestrator
        item_obj = orc.player_state.get_item_by_name(item_name)
        
        if not item_obj:
            return JSONResponse(content={"success": False, "message": "Vật phẩm không tồn tại trong túi đồ!"})
        
        if item_obj.item_type == "consumable" and not action_detail.strip():
            # Gọi trực tiếp qua PlayerState để nó cộng Máu và Stats
            orc.player_state.use_consumables(item_obj)
            return JSONResponse(content={"success": True, "message": f"Bạn đã sử dụng {item_name} thành công!"})
        
        target_items = [item_obj]
        action_text = action_detail if action_detail.strip() else f"Sử dụng {item_name}"
        use_result = await orc.item_sys.use(
            item_list=target_items,
            action_details=action_text
        )
        msg = use_result[1] if isinstance(use_result, tuple) else str(use_result)
        success = use_result[0] if isinstance(use_result, tuple) else True
        
        return JSONResponse(content={"success": success, "message": msg})
    except Exception as e:
        game_logger.error(f"Lỗi dùng vật phẩm: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/inventory/equip")
async def equip_item(item_name: str = Form(...)):
    """API để Unity ra lệnh trang bị vũ khí"""
    try:
        orc = app.state.orchestrator
        item_obj = orc.player_state.get_item_by_name(item_name)
        if not item_obj or item_obj.item_type != "weapon":
            return JSONResponse(content={"success": False, "message": "Không thể trang bị vật phẩm này."})
        orc.player_state.equip_weapon(item_obj) 
        return JSONResponse(content={"success": True, "message": f"Đã trang bị {item_name}!"})
    except Exception as e:
        game_logger.error(f"Lỗi trang bị: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/inventory/craft")
async def craft_item(items_str: str = Form(...), action_detail: str = Form(...)):
    """
    API để Unity ra lệnh chế tạo. 
    - items_str: chuỗi các tên vật phẩm cách nhau bằng dấu phẩy
    - action_detail: mô tả ý định ghép
    """
    try:
        orc = app.state.orchestrator
        target_items = []
        
        # Tách chuỗi để lấy ra các Object Item thật từ Balo
        for name in items_str.split(","):
            if not name.strip(): continue
            item_obj = orc.player_state.get_item_by_name(name.strip())
            if item_obj:
                target_items.append(item_obj)

        if len(target_items) < 1:
            return JSONResponse(content={"success": False, "message": "⚠️ Vật phẩm không tồn tại trong túi đồ!"})

        craft_result = await orc.item_sys.craft(
            item_list=target_items,
            action_details=action_detail,
            image_manager=orc.image_manager
        )
        return JSONResponse(content={"success": True, "message": craft_result})
    except Exception as e:
        game_logger.error(f"Lỗi chế tạo: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
if __name__ == "__main__":
    import uvicorn
    # QUAN TRỌNG: Phải set reload=False khi đóng gói hoặc chạy qua Unity để tránh lỗi vòng lặp tiến trình
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="warning")