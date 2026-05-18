import os
import ctypes
from engine.Utils.logger import game_logger 

class AudioManager:
    def __init__(self):
        self.audio_dir = "data/audio"
        self.current_emotion = None
        self.volume = 50
        self.is_enabled = True
        self.music_map = {
            "buồn": "buon.mp3",
            "chiến thắng": "chien_thang.mp3",
            "bình thường": "binh_thuong.mp3",
            "căng thẳng": "hoi_hop.mp3",
            "rùng rợn": "rung_ron.mp3"
        }

    def set_volume(self, percent):
        # Đảm bảo phần trăm nằm trong khoảng 0-100
        percent = max(0, min(100, percent))
        
        # Chuyển đổi sang thang 0-1000 của Windows MCI
        self.volume = percent * 10 
        
        # Nếu đang có nhạc phát (alias 'bgm' đang tồn tại), áp dụng ngay lập tức
        vol_cmd = f'setaudio bgm volume to {self.volume}'
        ctypes.windll.winmm.mciSendStringW(vol_cmd, None, 0, None)
        
        game_logger.info(f"[Audio] Đã chỉnh âm lượng nhạc nền thành {percent}%")

    def toggle_music(self, enable: bool):
        self.is_enabled = enable
        if not enable:
            self.stop_music()
            game_logger.info("[Audio] Đã TẮT nhạc nền.")
        else:
            game_logger.info("[Audio] Đã BẬT nhạc nền.")
            if self.current_emotion:
                temp_emotion = self.current_emotion
                self.current_emotion = None # Reset để phát lại
                self.play_music(temp_emotion)

    def play_music(self, emotion):
        if not self.is_enabled:
            return
        if not emotion:
            return
            
        emotion = emotion.lower().strip()
        
        if emotion == self.current_emotion:
            return

        file_name = self.music_map.get(emotion, self.music_map["bình thường"])
        file_path = os.path.abspath(os.path.join(self.audio_dir, file_name))

        if os.path.exists(file_path):
            try:
                self.stop_music()
                
                open_cmd = f'open "{file_path}" alias bgm'
                ctypes.windll.winmm.mciSendStringW(open_cmd, None, 0, None)
                
                vol_cmd = f'setaudio bgm volume to {self.volume}'
                ctypes.windll.winmm.mciSendStringW(vol_cmd, None, 0, None)
                
                play_cmd = 'play bgm repeat'
                ctypes.windll.winmm.mciSendStringW(play_cmd, None, 0, None)
                
                self.current_emotion = emotion
                game_logger.info(f"[Audio] Đang phát nhạc: {emotion} ({file_name})")
            except Exception as e:
                game_logger.error(f"[Audio] Lỗi khi phát nhạc (Windows API): {e}")
        else:
            game_logger.error(f"[Audio] Không tìm thấy file nhạc tại: {file_path}")

    def stop_music(self):
        try:
            ctypes.windll.winmm.mciSendStringW('stop bgm', None, 0, None)
            ctypes.windll.winmm.mciSendStringW('close bgm', None, 0, None)
        except:
            pass