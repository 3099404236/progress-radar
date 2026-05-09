# -*- coding: utf-8 -*-
"""极简临时记事本：单个 txt + 历史版本数组"""
import json
import os
import threading
from datetime import datetime

import config

PAD_FILE = os.path.join(config.DATA_DIR, "scratchpad.txt")
META_FILE = os.path.join(config.DATA_DIR, "scratchpad.meta.json")
HIST_FILE = os.path.join(config.DATA_DIR, "scratchpad.history.json")
_lock = threading.Lock()

HIST_MAX = 100


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


def _read_history():
    if not os.path.exists(HIST_FILE):
        return []
    try:
        with open(HIST_FILE, "r", encoding="utf-8") as f:
            return (json.load(f) or {}).get("history", [])
    except Exception:
        return []


def _write_history(history):
    if len(history) > HIST_MAX:
        history = history[-HIST_MAX:]
    os.makedirs(os.path.dirname(HIST_FILE), exist_ok=True)
    tmp = HIST_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"history": history}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, HIST_FILE)


def save(content):
    """保存当前内容 + 把旧内容存进历史（旧 != 新且旧非空时）"""
    with _lock:
        os.makedirs(os.path.dirname(PAD_FILE), exist_ok=True)
        # 读旧
        old = ""
        if os.path.exists(PAD_FILE):
            with open(PAD_FILE, "r", encoding="utf-8") as f:
                old = f.read()
        if old != (content or "") and old.strip():
            history = _read_history()
            history.append({
                "ts": datetime.now().isoformat(timespec="seconds"),
                "content": old,
            })
            _write_history(history)
        # 写新
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


def list_history():
    """返回历史列表（最近的在前）"""
    h = _read_history()
    h.reverse()
    return h
