
import base64
from collections import deque
from io import BytesIO
import numpy as np
import time
from PIL import ImageGrab
import threading

def pil_image_to_base64(pil_image):
    buffered = BytesIO() # 制造一个存在于内存里的“虚拟文件”
    pil_image.save(buffered, format="PNG") # 把内存里的图片对象，存进这个虚拟文件里（指定格式为 PNG）

    # 提取虚拟文件里的二进制数据，打包成 base64 文本
    return base64.b64encode(buffered.getvalue()).decode('utf-8')

def encode_image_to_base64_by_path(image_path):
    # 以二进制读取模式("rb")打开图片，并转换为 base64 文本
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

class Vision:
    def __init__(self, max_img_len=100, max_img_size=1024, capture_interval=2):
        self.max_img_len = max_img_len #存储的图片信息长度
        self.max_img_size = max_img_size #图片最大尺寸
        self.capture_interval = capture_interval #截屏间隔时间

        self.vision_data = deque(maxlen=max_img_len)
        
        self.vision_timer_flag = threading.Event()
        self.vision_timer = None

    def sudden_view(self):
        cur_time = time.time()
        cur_screenshot = ImageGrab.grab()
        width, height = cur_screenshot.size
        cur_screenshot = cur_screenshot.resize((min(width, self.max_img_size), min(height, self.max_img_size)))
        cur_screenshot = pil_image_to_base64(cur_screenshot)
        self.vision_data.append({
            'timestamp': cur_time,
            'image': cur_screenshot
        })

    def cap_loop(self):
        while True:
            if self.vision_timer_flag.is_set():
                break
            self.vision_timer_flag.wait(self.capture_interval)
            self.sudden_view()

    def start_timer(self):
        self.vision_timer = threading.Thread(target=self.cap_loop)
        self.vision_timer.start()

    def stop_timer(self):
        self.vision_timer_flag.set()
        if self.vision_timer is not None:
            self.vision_timer.join()
        self.vision_timer_flag.clear()
        self.vision_timer = None
    
if __name__ == "__main__":
    vision = Vision()
    vision.start_timer()
    time.sleep(10)  # 让它运行一段时间
    vision.stop_timer()
    print(f"Captured {len(vision.vision_data)} images.")
    print(vision.vision_data)  # 打印图片的信息