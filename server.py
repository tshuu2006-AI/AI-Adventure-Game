import os
import base64
import re
from dotenv import load_dotenv
from fastapi import FastAPI, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

# Import Orchestrator từ cấu trúc mới
from engine.Orchestration import GameOrchestrator
from engine.Utils.logger import game_logger

app = FastAPI()
load_dotenv()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo Bộ não trung tâm
orchestrator = GameOrchestrator(
    db_path="data/eldoria.db", 
    vector_model_path="all-MiniLM-L6-v2", # Chỉnh lại đường dẫn nếu cần
    groq_api_key=os.getenv("GROQ_API_KEY"), 
    gemini_api_key=os.getenv("GEMINI_API_KEY")
)
# ==========================================
# CÁC HÀM TIỆN ÍCH (HELPER)
# ==========================================

def image_to_base64_with_default(image_path, is_item=False):
    """(Req 4) Chuyển ảnh sang Base64, nếu không có sẽ lấy ảnh mặc định"""
    if image_path and os.path.exists(image_path):
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    
    if is_item:
        default_item_path = "static/default_item.png" # Nhớ tạo 1 ảnh này trong thư mục static
        if os.path.exists(default_item_path):
            with open(default_item_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
    return ""

def build_inventory_payload():
    """Lấy túi đồ mới nhất trực tiếp từ RAM"""
    try:
        inv_dict = orchestrator.player_state.inventory 
        payload = []
        # SỬA Ở ĐÂY: Thêm .values() để lấy trực tiếp object Item
        for item in inv_dict.values():
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
    """(Req 2) Cắt text dựa trên \n và Ngoặc kép ("")"""
    segments = []
    # Tách theo \n trước
    paragraphs = [p.strip() for p in full_text.split('\n') if p.strip()]

    for p in paragraphs:
        # Tách mảng dựa trên ngoặc kép. Các phần tử chẵn là ngoài ngoặc (Master), lẻ là trong ngoặc (NPC)
        parts = re.split(r'(".*?")', p)
        for part in parts:
            part = part.strip()
            if not part: continue
            
            if part.startswith('"') and part.endswith('"'):
                dialogue = part[1:-1].strip() # Bỏ ngoặc kép
                if dialogue:
                    segments.append({"speaker": "NPC", "text": f'"{dialogue}"'})
            else:
                segments.append({"speaker": "Master", "text": part})
    return segments

# ==========================================
# BACKGROUND TASKS (CHẠY NGẦM KHÔNG BLOCK UI)
# ==========================================
async def background_post_turn_processing(player_input, story_response):
    """(Req 1) Hàm này sẽ chạy ngầm sau khi Text đã được ném về Unity"""
    try:
        # 1. Trích xuất State (Items, Locations, NPCs mới) & Sinh ảnh
        ep_data, scene_emotion = await orchestrator.state_sys.process_background_tasks(player_input, story_response)
        
        # 2. Lưu Ký ức
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
# API ENDPOINTS
# ==========================================

@app.post("/api/new_game")
async def new_game(idea: str = Form(...), bg_tasks: BackgroundTasks = BackgroundTasks()):
    """Khởi tạo Game Loop mới giống hệt run() trong Orchestration"""
    try:
        # 1. Dọn dẹp Database
        await orchestrator.db.connect()
        await orchestrator.db.reset_database()
        await orchestrator.db.create_tables()
        orchestrator.image_manager.clear_image_folders()

        # 2. Sinh World & Location
        world_bible = await orchestrator.story_director.create_world_bible(idea)
        reqs = world_bible.get("system_requirements", {})
        orchestrator.world_state.name = reqs.get("world_name", "Vùng đất vô danh")
        
        starting_loc = await orchestrator.story_director.create_starting_location(
            orchestrator.world_state.name, "Fantasy", "Tối tăm"
        )
        orchestrator.player_state.currentLocation = starting_loc
        await orchestrator.db.add_location_to_db(starting_loc)

        # (Lưu ý: Tạm thời không await sinh ảnh ở đây để trả Text nhanh nhất, ảnh sẽ load qua API poll)
        
        # 3. Kể chuyện (Prologue)
        story_response = ""
        async for chunk in orchestrator.story_director.initialize_story(starting_loc):
            story_response += chunk
        
        # 4. Phân rã Text thành Segments (Master & NPC)
        segments = parse_story_into_segments(story_response)
        
        # 5. Sinh Lựa chọn
        choices = await orchestrator.story_director.generate_player_choices(
            current_location_name=starting_loc.name, encountered_npc_name=[], recent_story_text=story_response
        )
        orchestrator.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        # 6. Đẩy việc Lưu DB vào chạy ngầm
        bg_tasks.add_task(background_post_turn_processing, "[Bắt đầu trò chơi]", story_response)

        return JSONResponse(content={
            "segments": segments,
            "choices": choice_texts,
            "bg_image_b64": "", # Sẽ rỗng lúc đầu, Unity sẽ call API phụ để kéo ảnh lên sau
            "char_image_b64": "",
            "inventory": []
        })
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.post("/api/play")
async def play_turn(action: str = Form(...), bg_tasks: BackgroundTasks = BackgroundTasks()):
    """Xử lý lượt đi (Giống _process_game_turn)"""
    try:
        # 1. Lấy context
        directive = await orchestrator.action_sys.get_system_directive(action)
        hybrid_ctx, npcs_ctx = await orchestrator.memory_sys.get_hybrid_context(action, orchestrator.player_state)

        # 2. Sinh Story
        story_response = ""
        async for chunk in orchestrator.story_director.narrate_turn(
                action, orchestrator.world_state, orchestrator.player_state, npcs_ctx, hybrid_ctx, directive):
            story_response += chunk
        
        segments = parse_story_into_segments(story_response)

        # 3. Sinh Choice (Phải sinh ngay để Unity có data giấu sẵn chờ bật nút)
        choices = await orchestrator.story_director.generate_player_choices(
            current_location_name=orchestrator.player_state.currentLocation.name,
            encountered_npc_name=[n.name for n in orchestrator.player_state.currentNPCs],
            recent_story_text=story_response
        )
        orchestrator.last_choices = choices
        choice_texts = [c["action_text"] for c in choices]

        # 4. Chạy StateProcessor (Tính túi đồ, Update DB, Sinh Ảnh) NGẦM!
        bg_tasks.add_task(background_post_turn_processing, action, story_response)

        return JSONResponse(content={
            "segments": segments,
            "choices": choice_texts,
            "bg_image_b64": "", 
            "char_image_b64": "",
            "inventory": [] # Không trả inventory ngay, bắt Unity poll sau
        })
    except Exception as e:
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
            
        inv_payload = build_inventory_payload() # Đã bỏ chữ await
            
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)