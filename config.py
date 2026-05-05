# -*- coding: utf-8 -*-
"""ProgressRadar 配置

API key 来源（按优先级）：
  1. 环境变量 DEEPSEEK_API_KEY
  2. 同目录下 secrets.local.py 里的 DEEPSEEK_API_KEY（已 gitignore，不会进 git）

复制 secrets.example.py 为 secrets.local.py，把你的 key 写进去。
"""
import os

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

if not DEEPSEEK_API_KEY:
    try:
        from secrets_local import DEEPSEEK_API_KEY as _LOCAL_KEY  # type: ignore
        DEEPSEEK_API_KEY = _LOCAL_KEY
    except Exception:
        try:
            import importlib.util
            _here = os.path.dirname(os.path.abspath(__file__))
            _spec = importlib.util.spec_from_file_location(
                "secrets_local", os.path.join(_here, "secrets.local.py")
            )
            if _spec and _spec.loader:
                _mod = importlib.util.module_from_spec(_spec)
                _spec.loader.exec_module(_mod)
                DEEPSEEK_API_KEY = getattr(_mod, "DEEPSEEK_API_KEY", "")
        except Exception:
            pass

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-flash"

HOST = "127.0.0.1"
PORT = 5000
DEBUG = True

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
DATA_FILE = os.path.join(DATA_DIR, "progress.json")
WEEKLY_DIR = os.path.join(DATA_DIR, "weekly")
