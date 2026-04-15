import base64
import os
from fastapi import FastAPI, Form
import re
from fastapi.responses import JSONResponse
import uvicorn
from dotenv import load_dotenv
from engine.Orchestration import GameOrchestrator

app = FastAPI()

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")
orchestrator = GameOrchestrator(
    db_path="./data/World.db", 
    vector_model_path="all-MiniLM-L6-v2", # Cập nhật đúng model bạn đang dùng
    groq_api_key=api_key
)

def clean_ai_text(text: str) -> str:
    """Xóa bỏ chuỗi suy nghĩ <think>...</think> của AI nếu có."""
    if not text: return ""
    # Cờ re.DOTALL giúp regex khớp được cả các dấu xuống dòng (\n) bên trong thẻ think
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
    return cleaned.strip()

def image_to_base64(image_path):
    if not image_path or not os.path.exists(image_path):
        return ""
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except:
        return ""

def get_inventory_data():
    """Chuyển đổi Dictionary túi đồ thành mảng để gửi qua Unity."""
    inv_list = []
    # player_state.inventory đang là dạng: {"Tên item": "path/to/image.png"}
    if hasattr(orchestrator, 'player_state') and orchestrator.player_state.inventory:
        for name, path in orchestrator.player_state.inventory.items():
            inv_list.append({
                "name": name,
                "image_b64": image_to_base64(path)
            })
    return inv_list

@app.post("/api/new_game")
async def new_game(idea: str = Form(...)):
    try:
        orchestrator.db.reset_database()
        orchestrator.db.create_tables()
        
        await orchestrator._create_new_world(player_idea=idea)
        await orchestrator._initialize_location()
        raw_prologue = await orchestrator._initialize_story()

        prologue_text = clean_ai_text(raw_prologue)
        
        choices_data = await orchestrator._generate_choices(prologue_text)
        choices = [c['action_text'] for c in choices_data]
        
        bg_path = getattr(orchestrator.player_state.currentLocation, 'image_path', "")
        
        return {
            "speaker": "Game Master",
            "story": prologue_text,
            "choices": choices,
            "bg_image_b64": image_to_base64(bg_path),
            "char_image_b64": "",
            "inventory": get_inventory_data()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/play")
async def play(action: str = Form(...)):
    try:
        raw_story, raw_choices = await orchestrator._process_game_turn(action)
        story_response = clean_ai_text(raw_story)
        choices = [c['action_text'] for c in raw_choices]
        
        bg_path = getattr(orchestrator.player_state.currentLocation, 'image_path', "")
        char_path = getattr(orchestrator.player_state, 'current_npc_image', "")

        return {
            "speaker": "Narrator",
            "story": story_response,
            "choices": choices,
            "bg_image_b64": image_to_base64(bg_path),
            "char_image_b64": image_to_base64(char_path),
            "inventory": get_inventory_data()
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/settings")
async def update_settings(quality: str = Form(...)):
    """Cập nhật chất lượng ảnh (low, medium, high) từ Unity."""
    try:
        # Gán trực tiếp vào thuộc tính quality của ImageAPI
        orchestrator.image_manager.api.quality = quality.lower()
        print(f"[Server] Đã đổi chất lượng ảnh thành: {quality.upper()}")
        return {"message": f"Đã chuyển đồ họa sang {quality.upper()}"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/save_game")
async def save_game():
    try:
        # Tương lai bạn sẽ gọi: orchestrator.save_current_state()
        return {"message": "Đã lưu tiến trình game!"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/load_game")
async def load_game():
    try:
        # Tương lai bạn sẽ gọi logic lấy state mới nhất từ Database
        return {
            "speaker": "Hệ thống",
            "story": "Tính năng Load Game đang được hoàn thiện. Vui lòng tạo New Game.",
            "choices": ["Tiếp tục"],
            "inventory": []
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)