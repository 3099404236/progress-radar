# -*- coding: utf-8 -*-
"""极简临时记事本：单个 txt + meta 时间戳"""
import json
import os
import threading
from datetime import datetime

import config

PAD_FILE = os.path.join(config.DATA_DIR, "scratchpad.txt")
META_FILE = os.path.join(config.DATA_DIR, "scratchpad.meta.json")
_lock = threading.Lock()


def load():
    """返回 {content, updated_at}"""
    with _lock:
        content = ""
        if os.path.exists(PAD_FILE):
            with open(PAD_FILE, "r", encoding="utf-8") as f:
                content = f.read()
        meta = {}
        if os.path.exists(META_FILE):
            try:
                with open(META_FILE, "r", encoding="utf-8") as f:
                    meta = json.load(f)
            except Exception:
                meta = {}
        return {"content": content, "updated_at": meta.get("updated_at")}


def save(content):
    with _lock:
        os.makedirs(os.path.dirname(PAD_FILE), exist_ok=True)
        tmp = PAD_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content or "")
        os.replace(tmp, PAD_FILE)
        meta = {"updated_at": datetime.now().isoformat(timespec="seconds")}
        tmp2 = META_FILE + ".tmp"
        with open(tmp2, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)
        os.replace(tmp2, META_FILE)
        return meta
