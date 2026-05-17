import logging
from logging.handlers import RotatingFileHandler
import os


def setup_logger(log_folder="./logs", log_file="eldoria_game.log"):
    """Thiết lập hệ thống ghi log 2 luồng: Console và File."""

    # Tạo thư mục logs nếu chưa có
    if not os.path.exists(log_folder):
        os.makedirs(log_folder)

    log_path = os.path.join(log_folder, log_file)

    # Định dạng Log: [Thời gian] | [Cấp độ] | [Tên File:Dòng] | Tin nhắn
    formatter = logging.Formatter(
        '%(asctime)s | %(levelname)-8s | %(module)s:%(lineno)d | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Khởi tạo Logger chính
    logger = logging.getLogger("EldoriaEngine")
    logger.setLevel(logging.DEBUG)  # Lắng nghe mọi thứ từ DEBUG trở lên

    # Tránh việc add handler nhiều lần nếu module được import nhiều nơi
    if not logger.handlers:
        # 2. Luồng lưu vào File (Lưu lại TẤT CẢ mọi thứ)
        # maxBytes=5*1024*1024 (5MB), backupCount=3 (Giữ tối đa 3 file cũ)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(formatter)

        # Gắn 2 luồng này vào logger
        logger.addHandler(file_handler)

    return logger


game_logger = setup_logger()