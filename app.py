import json
import time
import urllib.parse
import requests
import io
from flask import Flask, render_template_string, request, jsonify, send_file
from groq import Groq

# ==========================================
# 1. CẤU HÌNH LOCAL (CHỈNH SỬA TẠI ĐÂY)
# ==========================================
# Dán link Ngrok mới nhất từ Kaggle vào đây (Không có dấu / ở cuối)
KAGGLE_URL = "https://0340-34-13-179-133.ngrok-free.app"


# ==========================================
# 2. QUẢN LÝ TRẠNG THÁI GAME
# ==========================================
class GameState:
    def __init__(self):
        self.location = "Thị trấn Khởi Đầu"
        self.player_hp = 100
        self.power = 5

    def get_context(self):
        return {
            "location": self.location,
            "player_hp": self.player_hp,
            "power": self.power
        }


app = Flask(__name__)
game_state = GameState()
client_groq = Groq(api_key=GROQ_API_KEY)

# ==========================================
# 3. HTML UI (GIAO DIỆN GAME)
# ==========================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Eldoria AI Adventure</title>
    <style>
        body { background: #000; color: #eee; font-family: 'Segoe UI', sans-serif; margin: 0; height: 100vh; display: flex; justify-content: center; align-items: center; overflow: hidden; }
        #game-box { position: relative; width: 100%; max-width: 1280px; aspect-ratio: 16/9; background: #111; box-shadow: 0 0 30px #000; overflow: hidden; border: 1px solid #333; }
        #bg { position: absolute; width: 100%; height: 100%; object-fit: cover; z-index: 1; filter: brightness(0.6); transition: opacity 0.8s; }
        #char-sprite { position: absolute; bottom: 0; left: 50%; transform: translateX(-50%); height: 85%; z-index: 2; display: none; filter: drop-shadow(0 0 20px #000); animation: fadeUp 0.5s; }

        .stats-bar { position: absolute; top: 20px; left: 20px; z-index: 5; background: rgba(0,0,0,0.7); padding: 10px 20px; border-radius: 8px; border: 1px solid #4db8ff; display: flex; gap: 20px; font-weight: bold; }

        /* Chỗ hiển thị trạng thái tải ảnh */
        #image-status { position: absolute; top: 20px; right: 20px; z-index: 10; background: rgba(255, 152, 0, 0.8); color: #fff; padding: 8px 16px; border-radius: 8px; font-weight: bold; display: none; transition: 0.5s; border: 1px solid #ffb74d; }

        #dialogue-area { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); width: 94%; background: rgba(10,10,10,0.9); border: 1px solid #444; border-radius: 10px; padding: 30px; z-index: 4; min-height: 160px; box-sizing: border-box; cursor: pointer; }
        #speaker-name { position: absolute; top: -15px; left: 20px; background: #4db8ff; color: #000; padding: 5px 20px; font-weight: bold; border-radius: 4px; }
        #choices-container { position: absolute; top: 40%; left: 50%; transform: translate(-50%, -50%); z-index: 6; width: 50%; display: flex; flex-direction: column; gap: 10px; }

        .choice-btn { background: rgba(0,0,0,0.8); color: #fff; border: 1px solid #555; padding: 12px; border-radius: 5px; cursor: pointer; font-size: 1.1em; transition: 0.3s; }
        .choice-btn:hover { background: #4db8ff; color: #000; border-color: #fff; }
        .dialogue-text { font-size: 1.3em; line-height: 1.6; }
        .outcome-text { color: #ffeb3b; font-style: italic; margin-bottom: 10px; }

        @keyframes fadeUp { from { opacity: 0; transform: translate(-50%, 30px); } to { opacity: 1; transform: translate(-50%, 0); } }
    </style>
</head>
<body>
    <div id="start-screen" style="position: absolute; z-index: 30; background: #000; inset:0; display: flex; flex-direction: column; justify-content: center; align-items: center;">
        <h1 style="color: #4db8ff; font-size: 3em; margin-bottom: 20px;">ELDORIA AI</h1>
        <button class="choice-btn" style="width: 250px;" onclick="initGame('Thị trấn bình minh')">BẮT ĐẦU HÀNH TRÌNH</button>
    </div>

    <div id="game-box" style="display: none;">
        <img id="bg" src="">
        <img id="char-sprite" src="">

        <div id="image-status">⏳ Đang xử lý...</div>

        <div class="stats-bar">
            <span style="color:#ff5252">❤️ HP: <span id="hp">100</span></span>
            <span style="color:#ffeb3b">⚔️ POW: <span id="power">5</span></span>
            <span style="color:#4CAF50">📍 <span id="loc">...</span></span>
        </div>

        <div id="choices-container"></div>

        <div id="dialogue-area" onclick="skipTyping()">
            <div id="speaker-name">Hệ thống</div>
            <div id="outcome-text" class="outcome-text"></div>
            <div id="dialogue-text" class="dialogue-text"></div>
        </div>
    </div>

    <script>
        let typingInterval = null;
        let isTyping = false;
        let fullCurrentText = "";
        let currentChoices = [];

        async function initGame(loc) { 
            document.getElementById("start-screen").style.display="none"; 
            document.getElementById("game-box").style.display="block";
            playAction("Bắt đầu", loc);
        }

        // Bấm vào khung chữ để hiện toàn bộ lập tức
        function skipTyping() {
            if(isTyping) {
                clearInterval(typingInterval);
                document.getElementById("dialogue-text").innerHTML = fullCurrentText;
                isTyping = false;
                showChoices();
            }
        }

        function showChoices() {
            const choicesDiv = document.getElementById("choices-container");
            choicesDiv.innerHTML = "";
            currentChoices.forEach(c => {
                const b = document.createElement("button");
                b.className = "choice-btn";
                b.innerText = c.text;
                b.onclick = (e) => {
                    e.stopPropagation(); // Ngăn click nhầm vào khung dialogue
                    playAction(c.text, null, c.immediate_outcome);
                };
                choicesDiv.appendChild(b);
            });
        }

        async function playAction(action, scenario=null, immediate=null) {
            const outDiv = document.getElementById("outcome-text");
            const diagDiv = document.getElementById("dialogue-text");
            const choicesDiv = document.getElementById("choices-container");
            const imgStatus = document.getElementById("image-status");

            choicesDiv.innerHTML = ""; 
            clearInterval(typingInterval);
            isTyping = false;

            diagDiv.innerHTML = "<i style='color:#aaa'>✨ AI đang dệt tiếp số phận...</i>";
            outDiv.innerText = immediate ? "► " + immediate : "";
            imgStatus.style.display = "none"; // Ẩn thông báo ảnh lúc gen text

            try {
                const res = await fetch("/play", {
                    method: "POST", 
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({ action, scenario, cur_outcome: immediate })
                });

                if(!res.ok) throw new Error("Server Error");
                const data = await res.json();

                // Cập nhật text và chỉ số lập tức
                document.getElementById("hp").innerText = data.player_hp;
                document.getElementById("power").innerText = data.power;
                document.getElementById("loc").innerText = data.location;
                document.getElementById("speaker-name").innerText = data.speaker;

                // Chuẩn bị Text và Choices
                fullCurrentText = data.dialogue;
                currentChoices = data.choices || [];

                // Hiệu ứng đánh máy
                diagDiv.innerText = "";
                let i = 0;
                isTyping = true;
                typingInterval = setInterval(() => {
                    if(i < fullCurrentText.length) {
                        diagDiv.innerHTML += fullCurrentText.charAt(i);
                        i++;
                    } else {
                        clearInterval(typingInterval);
                        isTyping = false;
                        showChoices();
                    }
                }, 25); // Tốc độ chạy chữ

                // XỬ LÝ TRẠNG THÁI TẢI ẢNH KAGGLE
                let imagesToLoad = 0;
                let imagesLoaded = 0;

                if (data.bg_url) imagesToLoad++;
                if (data.char_url) imagesToLoad++;

                if (imagesToLoad > 0) {
                    imgStatus.style.background = "rgba(255, 152, 0, 0.8)"; // Màu cam
                    imgStatus.style.borderColor = "#ffb74d";
                    imgStatus.innerText = "⏳ Đang vẽ ảnh trên Kaggle...";
                    imgStatus.style.display = "block";
                }

                const checkImgLoad = () => {
                    imagesLoaded++;
                    if (imagesLoaded === imagesToLoad) {
                        imgStatus.style.background = "rgba(76, 175, 80, 0.9)"; // Màu xanh lá
                        imgStatus.style.borderColor = "#81c784";
                        imgStatus.innerText = "✅ Đã tải xong ảnh!";
                        setTimeout(() => { imgStatus.style.display = "none"; }, 3000); // Ẩn sau 3s
                    }
                };

                // Tải ảnh Nền
                const bgImg = document.getElementById("bg");
                bgImg.style.opacity = "0.4"; // Làm mờ lúc chờ
                bgImg.onload = () => { 
                    bgImg.style.opacity = "1"; 
                    checkImgLoad(); 
                };
                if(data.bg_url) bgImg.src = data.bg_url;

                // Tải ảnh Nhân vật
                const charImg = document.getElementById("char-sprite");
                if(data.char_url) { 
                    charImg.onload = checkImgLoad;
                    charImg.src = data.char_url; 
                    charImg.style.display = "block"; 
                } else { 
                    charImg.style.display = "none"; 
                }

            } catch (err) {
                console.error(err);
                diagDiv.innerHTML = "<span style='color:#ff5252'>[Lỗi Hệ Thống]: Mất kết nối tới máy chủ (Check lại token Kaggle/Groq).</span>";
            }
        }
    </script>
</body>
</html>
"""


# ==========================================
# 4. CÁC ROUTE XỬ LÝ (BACKEND)
# ==========================================

@app.route("/")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/proxy-image")
def proxy_image():
    prompt = request.args.get("prompt", "")
    is_char = request.args.get("is_char", "false")

    # Chỉ gọi URL gốc, không gắn parameters trên URL nữa
    target = f"{KAGGLE_URL}/api/image"

    headers = {"ngrok-skip-browser-warning": "true"}

    # Đóng gói dữ liệu dạng form-data để gửi POST
    payload = {
        "prompt": prompt,
        "is_char": is_char,
        "style_scale": "0.0"  # Tạm thời để 0.0 vì chưa gửi ảnh mồi từ UI
    }

    try:
        # Chuyển từ requests.get sang requests.post
        resp = requests.post(target, data=payload, headers=headers, timeout=60)

        if resp.status_code == 200:
            return send_file(io.BytesIO(resp.content), mimetype='image/png')
        else:
            print(f"Kaggle trả về lỗi: {resp.status_code} - {resp.text}")
            return "Error from Kaggle", resp.status_code

    except Exception as e:
        print(f"Lỗi tải ảnh Kaggle: {e}")
        return "Error", 404


@app.route("/play", methods=["POST"])
def play():
    data = request.json
    action = data.get("action", "Tiếp tục khám phá")
    cur_outcome = data.get("cur_outcome", "")

    # Đã sửa lại Prompt: Ép Groq sinh từ khóa tiếng Anh riêng để vẽ ảnh
    prompt = f"""
    GM: Hành động của người chơi là '{action}'.
    Kết quả trước đó: {cur_outcome}
    Trạng thái game: {json.dumps(game_state.get_context())}

    Hãy viết tiếp câu chuyện. Trả về DUY NHẤT một chuỗi JSON chuẩn có cấu trúc:
    {{
        "speaker": "Tên người nói (hoặc 'Hệ thống')",
        "speaker_en_prompt": "Từ khóa tiếng Anh mô tả ngoại hình người nói để vẽ ảnh (vd: a medieval knight, glowing armor). Nếu speaker là Hệ thống thì để rỗng.",
        "dialogue": "Lời thoại hoặc diễn biến câu chuyện",
        "new_location": "Tên địa điểm mới bằng tiếng Việt",
        "location_en_prompt": "Từ khóa tiếng Anh mô tả cảnh vật để vẽ nền (vd: dark forest, glowing mushrooms)",
        "player_hp_change": 0,
        "power_change": 0,
        "choices": [
            {{ "text": "Hành động A", "immediate_outcome": "Hậu quả ngắn gọn" }}
        ]
    }}
    """

    try:
        completion = client_groq.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                # Bắt buộc phải có chữ "JSON" trong Role System khi bật json_object
                {"role": "system",
                 "content": "Bạn là Game Master của một game Visual Novel. BẠN PHẢI TRẢ VỀ TOÀN BỘ KẾT QUẢ DƯỚI DẠNG JSON. Không giải thích thêm."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )

        ai_res = json.loads(completion.choices[0].message.content)

        # Cập nhật logic Game State
        game_state.player_hp += ai_res.get("player_hp_change", 0)
        game_state.power += ai_res.get("power_change", 0)
        if ai_res.get("new_location"):
            game_state.location = ai_res["new_location"]

        ts = int(time.time())
        loc_prompt = ai_res.get("location_en_prompt", "fantasy landscape")
        char_prompt = ai_res.get("speaker_en_prompt", "")
        speaker_name = ai_res.get("speaker", "Hệ thống")

        response = {
            "speaker": speaker_name,
            "dialogue": ai_res.get("dialogue", "..."),
            "choices": ai_res.get("choices", []),
            "player_hp": game_state.player_hp,
            "power": game_state.power,
            "location": game_state.location,
            # Dùng từ khóa Tiếng Anh để đưa vào URL proxy
            "bg_url": f"/proxy-image?prompt={urllib.parse.quote(loc_prompt)}&t={ts}",
            "char_url": f"/proxy-image?prompt={urllib.parse.quote(char_prompt)}&is_char=true&t={ts}" if (
                        char_prompt and speaker_name not in ["", "Hệ thống", "Người dẫn chuyện"]) else ""
        }
        return jsonify(response)

    except Exception as e:
        print(f"ERROR: {e}")
        return jsonify({"dialogue": "Lỗi AI!", "choices": []}), 500


if __name__ == "__main__":
    print("🚀 Server đang khởi động tại http://127.0.0.1:5050")
    app.run(port=5050, debug=True)