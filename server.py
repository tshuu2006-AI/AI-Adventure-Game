"""
Module server.py
----------------
Đây là điểm vào (entry point) chính của backend FastAPI cho game Eldoria.
Quản lý các kết nối API từ Unity, xử lý luồng trò chơi, cấu hình AI,
và điều phối các tác vụ nền (background tasks).
"""

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

import asyncio
import httpx
from groq import Groq
from google import genai


def safe_key(key: str, env_var_name: str, skip_format_check: bool = False) -> str:
    """Xử lý API Key an toàn (Tầng 1: Lọc rác bằng cấu trúc chuỗi)."""
    k = key.strip() if key else ""
    is_valid = False

    if k and k not in ["null", "None", "DUMMY_KEY_TO_PREVENT_BUG"]:
        if skip_format_check:
            is_valid = True
        elif env_var_name == "GROQ_API_KEY" and k.startswith("gsk_") and len(k) > 40:
            is_valid = True
        elif env_var_name == "GEMINI_API_KEY" and k.startswith("AIza") and len(k) > 30:
            is_valid = True

    if is_valid: return k

    fallback_key = os.getenv(env_var_name)
    if fallback_key and fallback_key.strip():
        return fallback_key.strip()

    return "DUMMY_KEY_TO_PREVENT_BUG"


app = FastAPI()

current_config = {
    "mode": "default",  # "default" hoặc "custom"
    "cloud_provider": "groq",  # Hoặc "custom_key"
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
    provider="gemini",
    groq_api_key=safe_key(os.getenv("GROQ_API_KEY", ""), "GROQ_API_KEY"),
    local_api_key=safe_key(os.getenv("GEMINI_API_KEY", ""), "GEMINI_API_KEY")
)

app.state.poll_cache = {
    "dirty": True,   # Lần gọi đầu tiên bắt buộc phải build lại dữ liệu
    "heavy": None    # Chứa payload ảnh và túi đồ
}

# Đảm bảo các thư mục cần thiết luôn tồn tại trước khi khởi tạo
os.makedirs(os.path.join(BASE_DIR, "data"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "static"), exist_ok=True)


# ==========================================
# CÁC HÀM TIỆN ÍCH (HELPER)
# ==========================================
# Gom cụm logic xuất dữ liệu runtime để ghi thành file JSON

def image_to_base64_with_default(image_path, is_item=False):
    """
    (Req 4) Chuyển đổi file ảnh vật lý sang chuỗi Base64 để gửi qua API.
    Tự động xử lý đường dẫn tuyệt đối và sử dụng ảnh mặc định nếu không tìm thấy.

    Args:
        image_path (str): Đường dẫn đến file ảnh.
        is_item (bool): Cờ xác định xem ảnh này có phải là vật phẩm không (để dùng ảnh fallback).

    Returns:
        str: Chuỗi Base64 của ảnh, hoặc chuỗi rỗng nếu thất bại.
    """
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
    """
    Đồng bộ dữ liệu túi đồ chuẩn từ Orchestrator để gửi về Client.
    Loại bỏ các vật phẩm trùng tên và định dạng thành danh sách dictionary.

    Returns:
        list: Danh sách chứa thông tin chi tiết (tên, mô tả, ảnh base64) của từng vật phẩm.
    """
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


# ==========================================
# BACKGROUND TASKS & UTILS
# ==========================================
async def verify_groq_key(api_key: str) -> bool:
    """
    Xác thực API Key của Groq bằng cách thử gọi hàm list models.

    Args:
        api_key (str): Khóa API Groq cần kiểm tra.

    Returns:
        bool: True nếu API key hợp lệ, False nếu không hợp lệ hoặc lỗi kết nối.
    """
    try:
        def test():
            client = Groq(api_key=api_key)
            client.models.list()
            return True

        return await asyncio.to_thread(test)
    except Exception:
        return False


async def verify_gemini_key(api_key: str) -> bool:
    """
    Xác thực API Key của Google Gemini bằng cách thử gọi hàm list models.

    Args:
        api_key (str): Khóa API Gemini cần kiểm tra.

    Returns:
        bool: True nếu API key hợp lệ, False nếu không hợp lệ.
    """
    try:
        def test():
            client = genai.Client(api_key=api_key)
            client.models.list()
            return True

        return await asyncio.to_thread(test)
    except Exception:
        return False

async def background_post_turn_processing(player_input, story_response, is_new_game=False):
    """
    Hàm này sẽ chạy ngầm sau khi Text đã được ném về Unity.
    Đảm nhiệm việc trích xuất state, sinh/tải ảnh, đánh giá quest và lưu VectorDB.

    Args:
        player_input (str): Lệnh hoặc câu thoại người chơi nhập.
        story_response (str): Phản hồi cốt truyện từ Game Master.
        is_new_game (bool, optional): Cờ xác định đây có phải là turn khởi tạo game không.
    """
    orc = app.state.orchestrator
    try:
        if is_new_game:
            curr_loc = orc.get_current_location()  # Dùng hàm bọc
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

                await orc.add_location_to_db(curr_loc)  # Dùng hàm bọc

                npcs = orc.get_current_npcs()
                for npc in npcs:
                    npc.location = curr_loc.name  # Ép vị trí lần nữa cho chắc chắn
                    if not getattr(npc, 'image_path', None):
                        game_logger.info(f"🎨 [Turn 0] Bắt đầu vẽ ảnh NPC: {npc.name}")
                        npc_img = await orc.image_manager.get_or_create_npc_image(
                            npc_name=npc.name,
                            description=npc.description
                        )
                        if npc_img:
                            npc.image_path = npc_img
                    await orc.add_npc_to_db(npc)

        # 🌟 GỌI QUA HÀM BỌC (Đã có chữ 'return' nên không còn bị crash NoneType)
        ep_data, scene_emotion = await orc.state_process_background_tasks(player_input, story_response)
        orc.current_emotion = scene_emotion

        await orc.quest_evaluate_turn(player_input, story_response)  # Dùng hàm bọc

        encountered = [n.name for n in orc.get_current_npcs()]  # Dùng hàm bọc
        await orc.memory_save_turn(  # Dùng hàm bọc
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
        app.state.poll_cache["dirty"] = True


# ==========================================
# UNITY SYSTEM ENDPOINTS
# ==========================================
@app.get("/api/ping")
async def ping():
    """
    Unity sẽ gọi hàm này liên tục để xem Server đã khởi động xong chưa.

    Returns:
        JSONResponse: Chứa trạng thái 'ok' và message phản hồi.
    """
    return JSONResponse(content={"status": "ok", "message": "Server is ready"})


@app.post("/api/shutdown")
async def shutdown():
    """
    Tắt Server an toàn khi Unity đóng.
    Thực thi os._exit(0) để chấm dứt ngay lập tức tiến trình FastAPI.
    """
    os._exit(0)


# ==========================================
# API ENDPOINTS CHÍNH
# ==========================================


@app.post("/api/new_game")
async def new_game(idea: str = Form(...), bg_tasks: BackgroundTasks = BackgroundTasks()):
    """
    Khởi tạo Game Loop mới siêu gọn nhẹ từ một ý tưởng của người chơi.
    Điều phối việc sinh cốt truyện mở đầu, các lựa chọn, và tạo tác vụ nền.

    Args:
        idea (str): Ý tưởng bối cảnh game do người chơi truyền lên.
        bg_tasks (BackgroundTasks): Công cụ của FastAPI để chạy hàm ngầm định.

    Returns:
        JSONResponse: Payload chứa các phân đoạn cốt truyện (segments), lựa chọn (choices) và trạng thái rỗng cho turn đầu.
    """
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
    """
    Xử lý lượt đi (Chuẩn Clean Code). Phân tích hành động của người chơi,
    kết hợp RAG Memory để sinh phản hồi cốt truyện tiếp theo.

    Args:
        action (str): Lời thoại hoặc hành động của người chơi.
        bg_tasks (BackgroundTasks): Tác vụ nền để xử lý state sau khi trả API.

    Returns:
        JSONResponse: Payload cốt truyện mới và các lựa chọn (choices).
    """
    try:
        orc = app.state.orchestrator
        orc.is_processing_bg = True

        # 1. Giao toàn bộ việc phân tích Action, gọi RAG Memory và sinh truyện cho Orchestrator
        story_response = await orc.generate_turn_narrative_api(action)

        # 2. Phân rã văn bản (Dùng Class tiện ích)
        segments = TextFormatter.parse_story_into_segments(story_response)

        current_hp = orc.get_current_hp()
        is_dead = False
        try:
            combat_result = await orc.state_sys.combat_agent.extract_combat(story_response=story_response)
            taken_damage = combat_result.get("taken_damage", 0)
            is_being_attacked = combat_result.get("is_being_attacked", False)
            if is_being_attacked and taken_damage > 0:
                orc.player_state.take_damage(amount=taken_damage)
                current_hp = orc.get_current_hp()
                is_dead = orc.player_state.is_dead()
                game_logger.info(f"[Combat] Nhận {taken_damage} sát thương. HP còn: {current_hp}. Chết: {is_dead}")
        except Exception as e:
            game_logger.error(f"[Combat] Lỗi extract combat: {e}", exc_info=True)

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
            "inventory": [],
            "hp": current_hp,
            "max_hp": orc.get_max_hp(),
            "is_dead": is_dead
        })
    except Exception as e:
        # Đã sửa lại nội dung log cho đúng ngữ cảnh
        game_logger.error("❌ LỖI CRASH TẠI LƯỢT ĐI (PLAY TURN):", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})


@app.get("/api/poll_updates")
async def poll_updates():
    """
    API Polling liên tục từ Unity để lấy dữ liệu State hiện tại.

    Chiến lược cache 2 tầng:
    - Heavy cache (bg_image, npc_images, inventory): Chỉ rebuild khi dirty=True
      (tức là sau khi background task hoàn thành). Tránh đọc file và encode
      base64 liên tục mỗi giây khi state không thay đổi.
    - Light data (hp, stats, quest, emotion): Đọc trực tiếp từ RAM mỗi poll.
      Rẻ vì chỉ là đọc attribute, không có I/O.

    Returns:
        JSONResponse: Payload tổng hợp mọi chỉ số và trạng thái game hiện tại.
    """
    try:
        orc = app.state.orchestrator
        poll_cache = app.state.poll_cache

        # ==========================================
        # TẦNG 1: HEAVY CACHE (ảnh + inventory)
        # Chỉ rebuild khi dirty=True — tức là sau mỗi background task xong
        # ==========================================
        if poll_cache["dirty"] or poll_cache["heavy"] is None:
            curr_loc = orc.get_current_location()
            bg_img = image_to_base64_with_default(curr_loc.image_path if curr_loc else None)

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

            # Lưu vào cache và đánh dấu sạch
            poll_cache["heavy"] = {
                "bg_image_b64": bg_img,
                "npc_images": npc_images_payload,
                "inventory": inv_payload,
            }
            poll_cache["dirty"] = False
            game_logger.debug("[PollCache] Rebuilt heavy cache (ảnh + inventory)")
        else:
            # Dùng lại cache cũ — không đọc file, không encode base64
            bg_img = poll_cache["heavy"]["bg_image_b64"]
            npc_images_payload = poll_cache["heavy"]["npc_images"]
            inv_payload = poll_cache["heavy"]["inventory"]

        # ==========================================
        # TẦNG 2: LIGHT DATA (đọc RAM trực tiếp)
        # Luôn fresh mỗi poll — rẻ vì chỉ là attribute access
        # ==========================================
        emotion = getattr(orc, "current_emotion", "bình thường")
        current_hp = orc.get_current_hp()
        max_hp = orc.get_max_hp()
        equipped_weapon = orc.get_equipped_weapon()
        weapon_name = equipped_weapon.name if equipped_weapon else "Tay không"
        weapon_img_b64 = image_to_base64_with_default(getattr(equipped_weapon, 'image_path', None) if equipped_weapon else None, is_item=True)

        t_stats = orc.player_state.stats.total_stats
        strength_val = t_stats.get("strength", 0)
        agility_val = t_stats.get("agility", 0)
        defense_val = t_stats.get("defense", 0)
        intelligence_val = t_stats.get("intelligence", 0)

        active_quest = orc.get_active_quest()
        quest_payload = None
        print(f"Số lượng máu hiện tại: {orc.player_state.get_current_hp()}")
        if active_quest:
            raw_obj = getattr(active_quest, 'objectives', getattr(active_quest, 'objective', []))

            if isinstance(raw_obj, str): raw_obj = [raw_obj]
            raw_is_fin = getattr(active_quest, 'is_finished', [0] * len(raw_obj))
            is_fin = [1 if bool(x) else 0 for x in raw_is_fin]
            quest_payload = {
                "name": active_quest.name,
                "objectives": raw_obj,
                "is_finished": is_fin,
                "status": active_quest.status
            }



        return JSONResponse(content={
            "bg_image_b64": bg_img,
            "npc_images": npc_images_payload,
            "inventory": inv_payload,
            "hp": current_hp,
            "max_hp": max_hp,
            "weapon": weapon_name,
            "weapon_image_b64": weapon_img_b64,
            "strength": strength_val,
            "agility": agility_val,
            "defense": defense_val,
            "intelligence": intelligence_val,
            "emotion": emotion,
            "active_quest": quest_payload,
            "is_processing_bg": getattr(orc, "is_processing_bg", False)
        })
    except Exception as e:
        game_logger.error(f"Lỗi poll_updates: {e}", exc_info=True)
        return JSONResponse(content={"bg_image_b64": "", "npc_images": [], "inventory": []})


@app.get("/api/diary")
async def get_diary():
    """
    (Req 3) Hoàn thiện API Diary - Có thêm Nhiệm Vụ.
    Truy xuất toàn bộ cơ sở dữ liệu về NPC, Location và Quests đã gặp/nhận được.

    Returns:
        JSONResponse: Danh sách tóm tắt toàn bộ dữ liệu từ sổ tay (Diary).
    """
    try:
        orc = app.state.orchestrator
        npcs = await orc.get_all_npcs()
        locations = await orc.get_all_locations()

        npc_list = [{"name": n.name, "personality": getattr(n, 'personality', 'Chưa rõ'),
                     "description": getattr(n, 'description', ''),
                     "affectionate": getattr(n, 'affectionate', 0), "location": getattr(n, 'location', 'Chưa rõ'),
                     "status": getattr(n, 'status', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(n.image_path)} for n in npcs]

        loc_list = [{"name": l.name, "description": getattr(l, 'description', ''),
                     "atmosphere": getattr(l, 'atmosphere', 'Bình thường'),
                     "image_b64": image_to_base64_with_default(l.image_path)} for l in locations]

        quests_payload = []
        all_quests = orc.get_all_quests()
        for q in all_quests:
            raw_obj = getattr(q, 'objectives', getattr(q, 'objective', []))
            if isinstance(raw_obj, str): raw_obj = [raw_obj]

            raw_is_fin = getattr(q, 'is_finished', [0] * len(raw_obj))
            is_fin = [1 if bool(x) else 0 for x in raw_is_fin]

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
    """
    API để Unity ra lệnh chuyển đổi Nhiệm vụ đang theo dõi (Active Quest).
    Kích hoạt việc sinh lời dẫn chuyển cảnh mượt mà từ hệ thống.

    Args:
        quest_name (str): Tên nhiệm vụ muốn chuyển sang.

    Returns:
        JSONResponse: Trạng thái chuyển và văn bản chuyển tiếp cốt truyện.
    """
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
    """
    API để Unity lấy tiến trình Loading (Thanh Progress bar) khi xử lý tác vụ dài.

    Returns:
        JSONResponse: Chứa thông điệp và phần trăm (0.0 đến 1.0) để render UI.
    """
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
    """
    Endpoint xử lý nút Check cấu hình từ Menu của Unity.
    Xác minh tính hợp lệ của các API key trước khi lưu.

    Args:
        cloud_key (str): Khóa API Cloud (Groq).
        local_model_or_key (str): Khóa API Local (Gemini) hoặc tên model Ollama.
        is_ollama (str): Cờ boolean kiểm tra dạng text ('true'/'false').

    Returns:
        JSONResponse: Kết quả kiểm tra kèm câu thông báo.
    """
    if not cloud_key.strip() or not local_model_or_key.strip():
        return JSONResponse(content={"success": False, "message": "Vui lòng nhập đầy đủ cả 2 trường thông tin!"})

    cloud_ok = await verify_groq_key(cloud_key.strip())
    if not cloud_ok:
        return JSONResponse(
            content={"success": False, "message": "❌ Cloud API Key (Groq) không hợp lệ hoặc không kết nối được!"})

    if is_ollama.lower() == "true":
        return JSONResponse(content={
            "success": True,
            "message": "💚 Tuyệt vời! Cả hai cấu hình đều hợp lệ và sẵn sàng sử dụng."
        })
    else:
        local_ok = await verify_gemini_key(local_model_or_key.strip())
        if not local_ok:
            return JSONResponse(
                content={"success": False, "message": "❌ Local API Key (Gemini) không hợp lệ hoặc không kết nối được!"})

    return JSONResponse(
        content={"success": True, "message": "💚 Tuyệt vời! Cả hai cấu hình đều hợp lệ và sẵn sàng sử dụng."})


@app.post("/api/settings")
async def update_settings(
        mode: str = Form(None),  # Đổi Form(...) thành Form(None) để làm tham số tùy chọn
        cloud_key: str = Form(None),
        local_model_or_key: str = Form(None),
        is_ollama: str = Form(None),
        enable_image: str = Form(None),  # Bổ sung nhận lệnh bật/tắt ảnh từ Unity
        quality: str = Form(None)  # Bổ sung nhận lệnh chất lượng ảnh từ Unity
):
    """
    Cập nhật cài đặt động của game (AI Model, Quality, Generate Image).
    Khởi tạo lại Orchestrator nếu thay đổi Provider.

    Tham số (Tất cả đều Optional):
        mode, cloud_key, local_model_or_key, is_ollama, enable_image, quality.

    Returns:
        JSONResponse: Xác nhận cài đặt đã được áp dụng thành công.
    """

    orc = app.state.orchestrator
    # 1. NẾU UNITY CHỈ GỬI LỆNH ĐỔI CHẤT LƯỢNG ẢNH
    is_ollama_bool = str(is_ollama).lower() == "true"
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
        current_config["local_provider"] = "ollama" if is_ollama_bool else "gemini"

        # Khởi tạo lại AI nhưng PHẢI GIỮ LẠI trạng thái bật/tắt ảnh trước đó
        old_enable_image = getattr(orc.image_manager.api, 'enable_image', True)
        old_quality = getattr(orc.image_manager.api, 'quality', 'medium')

        if mode == "custom":
            app.state.orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                provider=current_config["local_provider"],
                groq_api_key=safe_key(current_config["cloud_key"], "GROQ_API_KEY"),
                local_api_key="" if is_ollama_bool else safe_key(
                    current_config["local_model_or_key"], "GEMINI_API_KEY"
                )
            )
        else:
            app.state.orchestrator = GameOrchestrator(
                db_path=os.path.join(SAVE_DIR, "eldoria.db"),
                db_folder=SAVE_DIR,
                vector_model_path="all-MiniLM-L6-v2",
                provider="ollama" if is_ollama_bool else "gemini",
                groq_api_key=safe_key(os.getenv("GROQ_API_KEY", ""), "GROQ_API_KEY"),
                local_api_key="" if is_ollama_bool else safe_key(
                    os.getenv("GEMINI_API_KEY", ""), "GEMINI_API_KEY"
                )
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
        await orc.save_game(slot_name=slot)
        return JSONResponse(content={"success": True, "message": f"Đã đồng bộ AI vào {slot}"})
    except Exception as e:
        game_logger.error(f"Lỗi Save API: {e}")
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/load_game")
async def load_game(slot: str = Form(...)):
    """API ghi đè Database và Memory từ file save lên hệ thống"""
    try:
        orc = app.state.orchestrator
        success, msg = await orc.load_game(slot_name=slot)
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
        item_obj = orc.get_item_by_name(item_name)
        
        if not item_obj:
            return JSONResponse(content={"success": False, "message": "Vật phẩm không tồn tại trong túi đồ!"})
        
        if item_obj.item_type == "consumable" and not action_detail.strip():
            # Gọi trực tiếp qua PlayerState để nó cộng Máu và Stats
            orc.use_consumables(item_obj)
            return JSONResponse(content={"success": True, "message": f"Bạn đã sử dụng {item_name} thành công!"})
        
        target_items = [item_obj]
        action_text = action_detail if action_detail.strip() else f"Sử dụng {item_name}"
        use_result = await orc.use(item_list=target_items,action_details=action_text)

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
        item_obj = orc.get_item_by_name(item_name)
        if not item_obj or item_obj.item_type != "weapon":
            return JSONResponse(content={"success": False, "message": "Không thể trang bị vật phẩm này."})

        orc.equip_weapon(item_obj)
        return JSONResponse(content={"success": True, "message": f"Đã trang bị {item_name}!"})
    except Exception as e:
        game_logger.error(f"Lỗi trang bị: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
@app.post("/api/inventory/unequip")
async def unequip_item():
    """API để Unity ra lệnh tháo vũ khí đang trang bị"""
    try:
        orc = app.state.orchestrator
        # Gọi thẳng vào hệ thống quản lý túi đồ để gỡ vũ khí
        if hasattr(orc.player_state.inventory_manager, 'equipped_weapon'):
            orc.player_state.inventory_manager.equipped_weapon = None
            
        return JSONResponse(content={"success": True, "message": "Đã tháo trang bị thành công!"})
    except Exception as e:
        game_logger.error(f"Lỗi tháo trang bị: {e}", exc_info=True)
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
            item_obj = orc.get_item_by_name(name.strip())
            if item_obj:
                target_items.append(item_obj)

        if len(target_items) < 1:
            return JSONResponse(content={"success": False, "message": "⚠️ Vật phẩm không tồn tại trong túi đồ!"})

        craft_result = await orc.craft(
            item_list=target_items,
            action_details=action_detail,
        )
        return JSONResponse(content={"success": True, "message": craft_result})

    except Exception as e:
        game_logger.error(f"Lỗi chế tạo: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": str(e)})
    
if __name__ == "__main__":
    import uvicorn
    # QUAN TRỌNG: Phải set reload=False khi đóng gói hoặc chạy qua Unity để tránh lỗi vòng lặp tiến trình
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False, log_level="warning")