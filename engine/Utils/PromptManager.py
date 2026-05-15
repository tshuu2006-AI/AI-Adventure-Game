import yaml
import os


class PromptManager:
    def __init__(self, yaml_path: str = './static/prompts.yaml'):
        """
        Khởi tạo PromptManager và tự động nạp file YAML vào bộ nhớ.
        """
        self.yaml_path = yaml_path
        self.prompts = self._load_prompts()

    def _load_prompts(self) -> dict:
        """
        Hàm nội bộ để đọc file YAML một cách an toàn.
        """
        if not os.path.exists(self.yaml_path):
            raise FileNotFoundError(f"[Lỗi] Không tìm thấy file cấu hình prompt tại: {self.yaml_path}")

        with open(self.yaml_path, 'r', encoding='utf-8') as file:
            try:
                # yaml.safe_load giúp chuyển đổi nội dung file thành Python Dictionary
                return yaml.safe_load(file)
            except yaml.YAMLError as exc:
                raise ValueError(f"[Lỗi] Cú pháp file YAML không hợp lệ: {exc}")

    def get_prompt(self, agent_name: str, prompt_type: str, **kwargs) -> str:
        """
        Lấy prompt từ bộ nhớ và nhồi các biến (kwargs) vào vị trí {biến} tương ứng.

        Ví dụ:
        get_prompt('world_initiator', 'user', user_input="Cyberpunk")
        """
        # 1. Kiểm tra xem Agent và Loại prompt có tồn tại trong YAML không
        try:
            raw_prompt = self.prompts[agent_name][prompt_type]
        except KeyError:
            raise KeyError(
                f"[Lỗi] Không tìm thấy Agent '{agent_name}' hoặc loại '{prompt_type}' trong file {self.yaml_path}.")

        # 2. Nếu hàm gọi không truyền biến nào, trả về chuỗi nguyên bản
        if not kwargs:
            return raw_prompt

        # 3. Format chuỗi với các biến
        try:
            return raw_prompt.format(**kwargs)
        except KeyError as e:
            # Lỗi này xảy ra khi trong file YAML có {ten_bien} nhưng Python lại quên truyền vào
            missing_var = e.args[0]
            raise KeyError(
                f"[Lỗi Code] Prompt của '{agent_name}' cần biến {{{missing_var}}}, nhưng bạn chưa truyền vào hàm get_prompt!")