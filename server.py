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
    """Lấy túi đồ mới nhất trực tiếp từ RAM"""
    try:
        inv_list = orchestrator.player_state.inventory
        payload = []
        # ✅ Duyệt trực tiếp qua từng Item object trong List
        for item in inv_list:
            payload.append({
                "name": getattr(item, 'name', 'Vật phẩm'),
                "description": getattr(item, 'description', 'Vật phẩm bí ẩn.'),
                "quote": getattr(item, 'quote', ''),
                "image_b64": image_to_base64_with_default(getattr(item, 'image_path', None), is_item=True)
            })
        return payload
    except Exception as e:
        print(f"Lỗi tải túi đồ: {e}")
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

async def background_post_turn_processing(player_input, story_response):
    """(Req 1) Hàm này sẽ chạy ngầm sau khi Text đã được ném về Unity"""
    try:
        ep_data, scene_emotion = await orchestrator.state_sys.process_background_tasks(player_input, story_response)

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
        game_logger.error(f"Lỗi chạy ngầm: {e}")

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
        orchestrator.player_state.inventory = []
        orchestrator.player_state.currentNPCs = []

        await orchestrator.db.connect()
        await orchestrator.db.reset_database()
        await orchestrator.db.create_tables()
        orchestrator.image_manager.clear_image_folders()

        world_bible = await orchestrator.story_director.create_world_bible(idea)
        reqs = world_bible.get("system_requirements", {})
        orchestrator.world_state.name = reqs.get("world_name", "Vùng đất vô danh")
        
        starting_loc = await orchestrator.story_director.create_starting_location(
            orchestrator.world_state.name, "Fantasy", "Tối tăm"
        )
        orchestrator.player_state.currentLocation = starting_loc
        await orchestrator.db.add_location_to_db(starting_loc)

        # 🌟 Lấy đường dẫn tới file world_bible.json trong thư mục an toàn
        world_bible_dir = os.path.join(orchestrator.db.db_folder, "world_bible.json")
        
        story_response = ""
        # 🌟 Truyền thêm tham số world_bible_dir vào đây:
        async for chunk in orchestrator.story_director.initialize_story(starting_loc, world_bible_dir=world_bible_dir):
            story_response += chunk

        segments = parse_story_into_segments(story_response)

        choices = await orchestrator.story_director.generate_player_choices(
            current_location_name=starting_loc.name, encountered_npc_name=[], recent_story_text=story_response
        )
        orchestrator.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        bg_tasks.add_task(background_post_turn_processing, "[Bắt đầu trò chơi]", story_response)

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
            recent_story_text=story_response
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
        
        char_img = ""
        if orchestrator.player_state.currentNPCs:
            char_img = image_to_base64_with_default(orchestrator.player_state.currentNPCs[0].image_path)
            
        inv_payload = build_inventory_payload()
            
        return JSONResponse(content={
            "bg_image_b64": bg_img,
            "char_image_b64": char_img,
            "inventory": inv_payload
        })
    except Exception as e:
        print(f"Lỗi poll_updates: {e}")
        return JSONResponse(content={"bg_image_b64": "", "char_image_b64": "", "inventory": []})

@app.get("/api/diary")
async def get_diary():
    """(Req 3) Hoàn thiện API Diary"""
    try:
        npcs = await orchestrator.db.npc_manager.get_all()
        locations = await orchestrator.db.location_manager.get_all()

        npc_list = [{"name": n.name, "personality": getattr(n, 'personality', 'Chưa rõ'), "description": getattr(n, 'description', ''),
                     "affectionate": getattr(n, 'affectionate', 0), "location": getattr(n, 'location', 'Chưa rõ'), "status": getattr(n, 'status', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(n.image_path)} for n in npcs]

        loc_list = [{"name": l.name, "description": getattr(l, 'description', ''), "atmosphere": getattr(l, 'atmosphere', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(l.image_path)} for l in locations]

        return JSONResponse(content={"npcs": npc_list, "locations": loc_list})
    except Exception as e:
        print(f"❌ Lỗi tải Diary: {e}")
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
    mode: str = Form(...),
    cloud_key: str = Form(""),
    local_model_or_key: str = Form(""),
    is_ollama: str = Form("false")
):
    """Lưu và áp dụng cấu hình cài đặt bằng cách tái khởi tạo toàn bộ Engine"""
    global current_config
    global orchestrator # 🌟 Bắt buộc phải có dòng này để báo cho Python biết ta sẽ sửa biến toàn cục

    current_config["mode"] = mode
    current_config["cloud_key"] = cloud_key.strip()
    current_config["local_model_or_key"] = local_model_or_key.strip()
    current_config["local_provider"] = "ollama" if is_ollama.lower() == "true" else "gemini"

    if mode == "custom":
        orchestrator = GameOrchestrator(
            db_path=os.path.join(SAVE_DIR, "eldoria.db"),
            db_folder=SAVE_DIR,  # 🌟 THÊM DÒNG NÀY
            vector_model_path="all-MiniLM-L6-v2",
            groq_api_key=safe_key(current_config["cloud_key"]),
            gemini_api_key=safe_key(current_config["local_model_or_key"])
        )
        game_logger.info("⚙️ Đã áp dụng cấu hình Custom của người dùng và khởi động lại Engine.")
    else:
        orchestrator = GameOrchestrator(
            db_path=os.path.join(SAVE_DIR, "eldoria.db"),
            db_folder=SAVE_DIR,  # 🌟 THÊM DÒNG NÀY
            vector_model_path="all-MiniLM-L6-v2",
            groq_api_key=safe_key(os.getenv("GROQ_API_KEY", "")),
            gemini_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""))
        )
        game_logger.info("⚙️ Đã khôi phục về hệ thống cấu hình Mặc định (Default).")

    return JSONResponse(content={"success": True, "message": "Đã lưu và áp dụng cài đặt hệ thống!"})

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

if __name__ == "__main__":
    import uvicorn
    # QUAN TRỌNG: Phải set reload=False khi đóng gói hoặc chạy qua Unity để tránh lỗi vòng lặp tiến trình
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="warning")