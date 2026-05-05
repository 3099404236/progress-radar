# -*- coding: utf-8 -*-
"""achievements.json 读写 + 模板补齐"""
import json
import os
import threading
from datetime import datetime

import config
from achievement_templates import (
    DIM_MILESTONE_TEMPLATES,
    GLOBAL_MILESTONE_TEMPLATES,
    make_dim_slot,
    make_global_slot,
)

ACHIEVEMENTS_FILE = os.path.join(config.DATA_DIR, "achievements.json")

_lock = threading.Lock()


def _ensure_global(data):
    g = data.setdefault("global", {})
    g.setdefault("milestones", [])
    g.setdefault("insights", [])
    g.setdefault("custom", [])

    existing_ids = {m["id"] for m in g["milestones"]}
    for t in GLOBAL_MILESTONE_TEMPLATES:
        if t["id"] not in existing_ids:
            g["milestones"].append(make_global_slot(t))


def ensure_dimension_block(data, dim_id):
    """为新维度创建 13 个空 milestone 槽"""
    pd = data.setdefault("per_dimension", {})
    block = pd.setdefault(dim_id, {"milestones": [], "insights": [], "custom": []})
    block.setdefault("milestones", [])
    block.setdefault("insights", [])
    block.setdefault("custom", [])

    existing_ids = {m["id"] for m in block["milestones"]}
    for t in DIM_MILESTONE_TEMPLATES:
        if t["id"] not in existing_ids:
            block["milestones"].append(make_dim_slot(t))
    return block


def load(progress_data=None):
    """读取并自动补齐：所有 progress 中的维度都要有对应槽位"""
    with _lock:
        if not os.path.exists(ACHIEVEMENTS_FILE):
            data = {"global": {}, "per_dimension": {}}
        else:
            with open(ACHIEVEMENTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

        _ensure_global(data)

        if progress_data:
            for dim_id in progress_data.get("dimensions", {}):
                ensure_dimension_block(data, dim_id)

        return data


def save(data):
    with _lock:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        tmp = ACHIEVEMENTS_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, ACHIEVEMENTS_FILE)


def now_date():
    return datetime.now().strftime("%Y-%m-%d")
