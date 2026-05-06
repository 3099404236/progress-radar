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


def _refresh_from_template(slots, templates, themed_overrides=None):
    """同 id 的 slot 刷新 rarity（保留 unlocked_at + 已 themed 的 title/description）
       themed_overrides: {id: {title, description}}, 优先覆盖
       如果 slot 有 themed=True 标记，title/description 不再被模板覆盖。
    """
    by_id = {s["id"]: s for s in slots if "id" in s}
    out = []
    seen = set()
    for t in templates:
        s = by_id.get(t["id"])
        if s is None:
            s = make_dim_slot(t)
        # rarity 永远跟模板（避免错过新规则）
        s["rarity"] = t["rarity"]
        # title/desc：优先 override，其次保留 themed，最后用模板
        if themed_overrides and t["id"] in themed_overrides:
            ov = themed_overrides[t["id"]]
            s["title"] = ov.get("title", s.get("title", t["title"]))
            s["description"] = ov.get("description", s.get("description", t["description"]))
            s["themed"] = True
        elif not s.get("themed"):
            s["title"] = t["title"]
            s["description"] = t["description"]
        out.append(s)
        seen.add(t["id"])
    for s in slots:
        if s.get("id") and s["id"] not in seen:
            out.append(s)
    return out


def _ensure_global(data):
    g = data.setdefault("global", {})
    g.setdefault("milestones", [])
    g.setdefault("insights", [])
    g.setdefault("custom", [])
    g["milestones"] = _refresh_from_template(g["milestones"], GLOBAL_MILESTONE_TEMPLATES)


def ensure_dimension_block(data, dim_id, themed_overrides=None):
    """为新维度创建 13 个空 milestone 槽；存在则按模板刷新；可传 themed_overrides 覆盖文案"""
    pd = data.setdefault("per_dimension", {})
    block = pd.setdefault(dim_id, {"milestones": [], "insights": [], "custom": []})
    block.setdefault("milestones", [])
    block.setdefault("insights", [])
    block.setdefault("custom", [])
    block["milestones"] = _refresh_from_template(block["milestones"], DIM_MILESTONE_TEMPLATES, themed_overrides)
    return block


def apply_themed_milestones(dim_id, themed_overrides, progress_data=None):
    """为某维度套用 themed 命名（可后期 regenerate）"""
    data = load(progress_data)
    ensure_dimension_block(data, dim_id, themed_overrides)
    save(data)
    return data["per_dimension"][dim_id]


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
