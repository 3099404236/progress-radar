# -*- coding: utf-8 -*-
"""ProgressRadar 配置

API key 来源（按优先级）：
  1. 环境变量 DEEPSEEK_API_KEY
  2. 同目录下 secrets.local.py 里的 DEEPSEEK_API_KEY（已 gitignore，不会进 git）

复制 secrets.example.py 为 secrets.local.py，把你的 key 写进去。
"""
import os

def _load_secrets():
    """从环境或 secrets.local.py 加载秘钥"""
    secrets = {}
    try:
        import importlib.util
        _here = os.path.dirname(os.path.abspath(__file__))
        _spec = importlib.util.spec_from_file_location(
            "secrets_local", os.path.join(_here, "secrets.local.py")
        )
        if _spec and _spec.loader:
            _mod = importlib.util.module_from_spec(_spec)
            _spec.loader.exec_module(_mod)
            for k in ("DEEPSEEK_API_KEY", "SILICONFLOW_API_KEY"):
                v = getattr(_mod, k, None)
                if v:
                    secrets[k] = v
    except Exception:
        pass
    return secrets

_SECRETS = _load_secrets()

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY") or _SECRETS.get("DEEPSEEK_API_KEY", "")
SILICONFLOW_API_KEY = os.environ.get("SILICONFLOW_API_KEY") or _SECRETS.get("SILICONFLOW_API_KEY", "")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_IMAGE_MODEL = "Tongyi-MAI/Z-Image-Turbo"
SILICONFLOW_IMAGE_SIZE = "1024x1024"
SILICONFLOW_NUM_STEPS = 8

HOST = "127.0.0.1"
PORT = 5000
DEBUG = True

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "progress.json")
WEEKLY_DIR = os.path.join(DATA_DIR, "weekly")
IMAGES_DIR = os.path.join(DATA_DIR, "achievement_images")
