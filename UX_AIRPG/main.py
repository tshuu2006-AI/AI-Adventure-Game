import base64, json, asyncio, httpx, os
from fastapi import FastAPI, Form
from fastapi.responses import JSONResponse
from groq import Groq
import uvicorn
import psutil

def kill_port(port):
    """Tìm và tiêu diệt bất kỳ tiến trình nào đang chiếm dụng cổng được chỉ định"""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            # Kiểm tra các kết nối mạng của tiến trình
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    print(f"⚠️ Phát hiện cổng {port} đang bị chiếm bởi {proc.info['name']} (PID: {proc.info['pid']})")
                    print(f"🧹 Đang giải phóng cổng {port}...")
                    proc.kill() # Tiêu diệt tiến trình cũ
                    return
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

app = FastAPI()

KAGGLE_IMAGE_API = "https://unspelt-nonbrutally-eleanore.ngrok-free.dev/api/image"
SAVE_FILE = "savegame.json"

client = Groq(api_key=GROQ_API_KEY)
current_state = {}
# 🌟 BỘ NHỚ CỦA GAME (Quyển nhật ký)
game_memory = []

async def fetch_image_from_kaggle(client_httpx, prompt: str, is_char: bool):
    if not prompt: return ""
    try:
        response = await client_httpx.post(KAGGLE_IMAGE_API, data={"prompt": prompt, "is_char": str(is_char).lower()}, timeout=30.0)
        if response.status_code == 200:
            return base64.b64encode(response.content).decode('utf-8')
    except Exception as e: print(f"Lỗi Kaggle: {e}")
    return ""

async def process_turn(action: str):
    global game_memory, current_state
    
    system_prompt = """You are a Game Master in a visual novel text RPG. 
    Based on the story history and the player's action, reply ONLY in JSON format with these exactly 5 keys:
    - "speaker": The name of the NPC speaking, OR "Game Master" if it's general narration.
    - "story": The dialogue or narration in Vietnamese (2-3 sentences).
    - "choices": A list of exactly 3 short options for the player's next action (in Vietnamese).
    - "bg_prompt": English prompt describing the background environment.
    - "char_prompt": English prompt describing the NPC. (CRITICAL: Leave empty "" if "speaker" is "Game Master")."""
    
    messages = [{"role": "system", "content": system_prompt}] + game_memory
    messages.append({"role": "user", "content": action})
    
    try:
        chat_completion = client.chat.completions.create(
            messages=messages, model="llama-3.1-8b-instant", response_format={"type": "json_object"}
        )
        ai_response = json.loads(chat_completion.choices[0].message.content)
        
        # Bóc tách dữ liệu
        speaker = ai_response.get("speaker", "Game Master")
        story_text = ai_response.get("story", "")
        choices = ai_response.get("choices", ["Tiếp tục", "Quay lại", "Kiểm tra"])
        bg_prompt = ai_response.get("bg_prompt", "")
        char_prompt = ai_response.get("char_prompt", "")
        
        # Lưu vào trí nhớ chat
        game_memory.append({"role": "user", "content": action})
        game_memory.append({"role": "assistant", "content": story_text})

        # 🌟 LƯU TRẠNG THÁI HIỆN TẠI (Để chuẩn bị cho việc Save Game)
        current_state = {
            "speaker": speaker,
            "story": story_text,
            "choices": choices,
            "bg_prompt": bg_prompt,
            "char_prompt": char_prompt
        }
        
    except Exception as e:
        return {"error": f"Lỗi Groq: {str(e)}"}

    async with httpx.AsyncClient() as client_httpx:
        bg_b64, char_b64 = await asyncio.gather(
            fetch_image_from_kaggle(client_httpx, bg_prompt, False),
            fetch_image_from_kaggle(client_httpx, char_prompt, True)
        )

    return {
        "speaker": speaker, "story": story_text, "choices": choices,
        "bg_image_b64": bg_b64, "char_image_b64": char_b64
    }

# --- API CHO MAIN MENU ---
@app.post("/api/new_game")
async def new_game():
    global game_memory
    game_memory = [] # Xóa trí nhớ
    # Gọi AI sinh ra cảnh mở màn ngay lập tức
    result = await process_turn("Hãy bắt đầu trò chơi. Miêu tả cảnh tôi vừa thức dậy ở một nơi xa lạ.")
    return JSONResponse(content=result)

@app.post("/api/save_game")
async def save_game():
    save_data = {
        "memory": game_memory,
        "state": current_state
    }
    with open(SAVE_FILE, "w", encoding="utf-8") as f:
        json.dump(save_data, f, ensure_ascii=False, indent=4)
    return {"message": "Đã lưu game và các lựa chọn!"}

@app.post("/api/load_game")
async def load_game():
    global game_memory, current_state
    if os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, "r", encoding="utf-8") as f:
            save_data = json.load(f)
            
            # Cấu trúc an toàn lỡ bạn load nhầm file save cũ
            if isinstance(save_data, dict):
                game_memory = save_data.get("memory", [])
                current_state = save_data.get("state", {})
            else:
                return {"error": "File save quá cũ, vui lòng chơi New Game!"}

        # 🌟 Gọi Kaggle vẽ lại bức ảnh lúc bạn vừa Save
        bg_prompt = current_state.get("bg_prompt", "")
        char_prompt = current_state.get("char_prompt", "")
        
        async with httpx.AsyncClient() as client_httpx:
            bg_b64, char_b64 = await asyncio.gather(
                fetch_image_from_kaggle(client_httpx, bg_prompt, False),
                fetch_image_from_kaggle(client_httpx, char_prompt, True)
            )

        # Trả về toàn bộ dữ liệu y như lúc đang chơi
        return {
            "speaker": current_state.get("speaker", ""),
            "story": current_state.get("story", "Đã tải game thành công."),
            "choices": current_state.get("choices", ["Tiếp tục"]),
            "bg_image_b64": bg_b64,
            "char_image_b64": char_b64
        }
    return {"error": "Không tìm thấy file save!"}

# --- API CHƠI GAME CHÍNH ---
@app.post("/api/play")
async def play_turn(action: str = Form(...)):
    result = await process_turn(action)
    return JSONResponse(content=result)

@app.get("/api/health")
async def health_check():
    return {"status": "online"}

if __name__ == "__main__":
    kill_port(8000)
    uvicorn.run(app, host="0.0.0.0", port=8000)