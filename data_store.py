# -*- coding: utf-8 -*-
"""progress.json 读写 + v2 schema 迁移

v2 字段：
  dimension.phase_versions: [{version, created_at, phases, retired_at}]
  dimension.phase_activity: [int...]   # 当前周期下每阶段entry数
  dimension.primary_phase:  int        # 最近5条出现最多的阶段
  dimension.recent_phases:  [int...]   # 最近5条的phase_index
  dimension.current_cycle:  int        # 当前是第几轮周期
  dimension.cycles:        [{number, started_at, ended_at}]
  entry.phase_index:        int        # 这条记录属于哪个阶段（独立判断）
  entry.cycle:              int        # 属于第几轮
  entry.cross_dimensions:   [str]
"""
import json
import os
import threading
from collections import Counter
from datetime import datetime

import config

_lock = threading.Lock()


_HABIT_KEYWORDS = ("习惯", "喝水", "吃饭", "饮食", "早起", "晚饭", "晚餐", "早餐", "睡眠",
                   "运动", "锻炼", "刷牙", "记账", "阅读", "冥想", "走路", "跑步", "节食",
                   "戒糖", "记日记", "口腔", "牙齿")


def _classify_default_track(label, phases):
    """新维度初始落在哪一栏"""
    lbl = label or ""
    if any(k in lbl for k in _HABIT_KEYWORDS):
        return "must"
    for p in phases or []:
        n = p.get("name", "") if isinstance(p, dict) else str(p)
        if "建立规律" in n or "内化自动" in n:
            return "must"
    return "main"


def _migrate_dimension(dim):
    """把 v1 dim 迁移到 v2 schema（幂等）"""
    n_phases = len(dim.get("phases", []))

    if "track" not in dim:
        dim["track"] = _classify_default_track(dim.get("label", ""), dim.get("phases", []))
    if "rank" not in dim:
        dim["rank"] = 9999  # 大值兜底，前端按 (rank, created_at) 排，新创建的会落到底端

    # 维度状态：active(默认/进行中) / honored(已完成 - 荣誉墙) / ignored(已忽视 - 垃圾箱)
    if "state" not in dim:
        dim["state"] = "active"
    if "state_changed_at" not in dim:
        dim["state_changed_at"] = None

    # 时间轴：用户提及具体日期事件（考试日期、看医生、截止等）由 AI 提取
    if "timeline" not in dim:
        dim["timeline"] = []

    if "phase_versions" not in dim:
        dim["phase_versions"] = [{
            "version": 1,
            "created_at": dim.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            "phases": [p["name"] for p in dim.get("phases", [])],
            "retired_at": None,
        }]

    if "current_cycle" not in dim:
        dim["current_cycle"] = 1
    if "cycles" not in dim:
        dim["cycles"] = [{
            "number": 1,
            "started_at": dim.get("created_at", datetime.now().strftime("%Y-%m-%d")),
            "ended_at": None,
        }]

    for e in dim.get("entries", []):
        if "phase_index" not in e:
            e["phase_index"] = e.get("stage_at_time", dim.get("current_stage", 0))
        if "cycle" not in e:
            e["cycle"] = 1
        if "cross_dimensions" not in e:
            e["cross_dimensions"] = []

    _recompute_phase_stats(dim)
    return dim


def _recompute_phase_stats(dim):
    n_phases = max(1, len(dim.get("phases", [])))
    cur_cycle = dim.get("current_cycle", 1)
    activity = [0] * n_phases
    cur_entries = [e for e in dim.get("entries", []) if e.get("cycle", 1) == cur_cycle]
    for e in cur_entries:
        idx = e.get("phase_index", 0)
        if 0 <= idx < n_phases:
            activity[idx] += 1
    dim["phase_activity"] = activity

    last5 = [e.get("phase_index", 0) for e in cur_entries[-5:]]
    dim["recent_phases"] = last5
    if last5:
        dim["primary_phase"] = Counter(last5).most_common(1)[0][0]
    else:
        dim["primary_phase"] = dim.get("current_stage", 0)

    dim["current_stage"] = max(dim.get("current_stage", 0), dim["primary_phase"])
    dim["current_stage"] = min(dim["current_stage"], n_phases - 1)


def load():
    with _lock:
        if not os.path.exists(config.DATA_FILE):
            return {
                "dimensions": {},
                "meta": {"total_entries": 0, "last_updated": None,
                         "pending_confirms": {}, "pending_evolutions": {},
                         "seen_hashes": [], "schema_version": 2},
            }
        with open(config.DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        for dim in data.get("dimensions", {}).values():
            _migrate_dimension(dim)
        meta = data.setdefault("meta", {})
        meta.setdefault("pending_confirms", {})
        meta.setdefault("pending_evolutions", {})
        meta.setdefault("seen_hashes", [])
        meta["schema_version"] = 2
        return data


def save(data):
    with _lock:
        os.makedirs(os.path.dirname(config.DATA_FILE), exist_ok=True)
        for dim in data.get("dimensions", {}).values():
            _recompute_phase_stats(dim)
        total = sum(len(d.get("entries", [])) for d in data.get("dimensions", {}).values())
        data.setdefault("meta", {})
        data["meta"]["total_entries"] = total
        data["meta"]["last_updated"] = datetime.now().isoformat(timespec="seconds")
        data["meta"]["schema_version"] = 2
        tmp = config.DATA_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config.DATA_FILE)


def evolve_phases(dim, new_phases, entry_remapping):
    """阶段演化：换 phases、归档旧版本、按 remapping 重打 entry.phase_index"""
    today = datetime.now().strftime("%Y-%m-%d")

    versions = dim.setdefault("phase_versions", [])
    if versions and versions[-1].get("retired_at") is None:
        versions[-1]["retired_at"] = today

    next_version = (versions[-1]["version"] + 1) if versions else 1
    versions.append({
        "version": next_version,
        "created_at": today,
        "phases": [p["name"] if isinstance(p, dict) else p for p in new_phases],
        "retired_at": None,
    })

    new_phase_objs = []
    for p in new_phases:
        if isinstance(p, dict):
            new_phase_objs.append({"name": p.get("name", "?"), "desc": p.get("desc", "")})
        else:
            new_phase_objs.append({"name": str(p), "desc": ""})
    dim["phases"] = new_phase_objs

    remap = {}
    for r in entry_remapping or []:
        old = r.get("old_phase")
        new = r.get("new_phase")
        if old is not None and new is not None:
            remap[int(old)] = int(new)

    n_new = len(new_phase_objs)
    for e in dim.get("entries", []):
        old_idx = e.get("phase_index", 0)
        new_idx = remap.get(old_idx, min(old_idx, n_new - 1))
        e["phase_index"] = max(0, min(new_idx, n_new - 1))

    _recompute_phase_stats(dim)


def start_new_cycle(dim, reason="", reset_phase=0):
    """开新周期：当前周期收尾，新周期从 reset_phase 起步"""
    today = datetime.now().strftime("%Y-%m-%d")
    cycles = dim.setdefault("cycles", [])
    if cycles and cycles[-1].get("ended_at") is None:
        cycles[-1]["ended_at"] = today

    new_num = (cycles[-1]["number"] + 1) if cycles else 1
    cycles.append({
        "number": new_num,
        "started_at": today,
        "ended_at": None,
        "reason": reason,
    })
    dim["current_cycle"] = new_num
    n_phases = max(1, len(dim.get("phases", [])))
    dim["current_stage"] = max(0, min(int(reset_phase), n_phases - 1))
    _recompute_phase_stats(dim)
