# -*- coding: utf-8 -*-
"""原始粘贴归档：每次 submit 都把原文 + AI 输出追加到 data/raw_submissions.jsonl

每行一个 JSON：
{
  "id": "<md5(text+ts)前12位>",
  "timestamp": "2026-05-06T12:34:56",
  "text": "<原文>",
  "text_hash": "<md5>",
  "result": {"action": "...", "dimension_id": "...", ...}
}

JSONL 单行不会被截断。文件只追加不修改，便于以后重放或重构。
"""
import hashlib
import json
import os
import threading
from datetime import datetime

import config

ARCHIVE_FILE = os.path.join(config.DATA_DIR, "raw_submissions.jsonl")
_lock = threading.Lock()


def _slim_result(r):
    """只保留对未来重构有意义的字段，剔除冗长内部字段"""
    if not isinstance(r, dict):
        return r
    keep = ("status", "action", "dimension_id", "dimension_label", "summary",
            "phase_index", "phase_name", "tag", "key_progress", "next_steps",
            "cross_dimensions", "cycle", "cycle_event", "reason",
            "evolution_id", "confirm_id", "phases",
            "insight", "unlocked")
    return {k: r[k] for k in keep if k in r}


def append(text, result):
    text = text or ""
    ts = datetime.now().isoformat(timespec="seconds")
    text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
    record = {
        "id": hashlib.md5((text_hash + ts).encode("utf-8")).hexdigest()[:12],
        "timestamp": ts,
        "text": text,
        "text_hash": text_hash,
        "result": _slim_result(result),
    }
    with _lock:
        os.makedirs(os.path.dirname(ARCHIVE_FILE), exist_ok=True)
        with open(ARCHIVE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record["id"]


def read_all(limit=None):
    if not os.path.exists(ARCHIVE_FILE):
        return []
    out = []
    with open(ARCHIVE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except Exception:
                continue
    if limit:
        out = out[-int(limit):]
    return out


def stats():
    if not os.path.exists(ARCHIVE_FILE):
        return {"count": 0, "size_bytes": 0, "first": None, "last": None, "path": ARCHIVE_FILE}
    items = read_all()
    return {
        "count": len(items),
        "size_bytes": os.path.getsize(ARCHIVE_FILE),
        "first": items[0]["timestamp"] if items else None,
        "last": items[-1]["timestamp"] if items else None,
        "path": ARCHIVE_FILE,
    }


def export_to(dst_path):
    """把 jsonl 复制到指定路径（桌面/U盘等），返回 (count, dst_path)"""
    items = read_all()
    os.makedirs(os.path.dirname(dst_path) or ".", exist_ok=True)
    with open(dst_path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
    return len(items), dst_path
