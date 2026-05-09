# -*- coding: utf-8 -*-
"""轻量记事本：data/notes.json 增删改查"""
import hashlib
import json
import os
import threading
from datetime import datetime

import config

NOTES_FILE = os.path.join(config.DATA_DIR, "notes.json")
_lock = threading.Lock()


def _new_id(content):
    seed = (content or "")[:120] + datetime.now().isoformat()
    return hashlib.md5(seed.encode("utf-8")).hexdigest()[:12]


def load():
    with _lock:
        if not os.path.exists(NOTES_FILE):
            return {"notes": []}
        with open(NOTES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)


def save_all(data):
    with _lock:
        os.makedirs(os.path.dirname(NOTES_FILE), exist_ok=True)
        tmp = NOTES_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, NOTES_FILE)


def list_all():
    """按 updated_at 倒序返回"""
    data = load()
    notes = list(data.get("notes", []))
    notes.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
    return notes


def upsert(note_id, title, content):
    """note_id 为空 → create；否则 update"""
    data = load()
    notes = data.setdefault("notes", [])
    now = datetime.now().isoformat(timespec="seconds")
    title = (title or "").strip()[:80]
    content = (content or "").strip()
    if not content and not title:
        return None  # 空笔记不存

    if note_id:
        for n in notes:
            if n.get("id") == note_id:
                n["title"] = title
                n["content"] = content
                n["updated_at"] = now
                save_all(data)
                return n
        # id 不存在 → 当成新建
    new_id = _new_id(content)
    item = {
        "id": new_id,
        "title": title,
        "content": content,
        "created_at": now,
        "updated_at": now,
    }
    notes.append(item)
    save_all(data)
    return item


def delete(note_id):
    data = load()
    before = len(data.get("notes", []))
    data["notes"] = [n for n in data.get("notes", []) if n.get("id") != note_id]
    save_all(data)
    return before != len(data["notes"])


def get(note_id):
    for n in load().get("notes", []):
        if n.get("id") == note_id:
            return n
    return None
