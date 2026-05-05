# -*- coding: utf-8 -*-
"""成就检查器：每次 submit 后调用 check()
计算 13 个 dim_milestone + 7 个 global milestone，返回新解锁列表
"""
import logging
from datetime import datetime, timedelta, date

import achievement_store

log = logging.getLogger("progressradar.achv")


def _entry_dates(entries):
    """[date, ...] 升序去重"""
    out = set()
    for e in entries:
        ts = e.get("timestamp", "")
        try:
            out.add(datetime.fromisoformat(ts).date())
        except Exception:
            continue
    return sorted(out)


def calc_streak(entries):
    """以"今天/昨天起最长向前连续天数"为口径"""
    dates = _entry_dates(entries)
    if not dates:
        return 0
    today = date.today()
    cur = today if today in dates else (today - timedelta(days=1) if (today - timedelta(days=1)) in dates else None)
    if cur is None:
        return 0
    streak = 1
    while (cur - timedelta(days=1)) in dates:
        cur -= timedelta(days=1)
        streak += 1
    return streak


def calc_max_streak(entries):
    dates = _entry_dates(entries)
    if not dates:
        return 0
    best = 1
    cur = 1
    for i in range(1, len(dates)):
        if (dates[i] - dates[i-1]).days == 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def calc_span_days(entries):
    dates = _entry_dates(entries)
    if not dates:
        return 0
    return (dates[-1] - dates[0]).days


def calc_active_days(entries):
    return len(_entry_dates(entries))


def _check_dim(progress_data, ach_data, dim_id):
    """返回该维度新解锁的 milestone（id list）"""
    dim = progress_data["dimensions"].get(dim_id)
    if not dim:
        return []
    block = achievement_store.ensure_dimension_block(ach_data, dim_id)

    entries = dim.get("entries", [])
    n = len(entries)
    n_phases = max(1, len(dim.get("phases", [])))
    primary = dim.get("primary_phase", 0)
    cycle = dim.get("current_cycle", 1)
    versions = len(dim.get("phase_versions", []))
    streak = calc_streak(entries)
    span = calc_span_days(entries)

    checks = {
        "dim_first":    n >= 1,
        "dim_10":       n >= 10,
        "dim_deep":     n >= 20,
        "dim_50":       n >= 50,
        "dim_hatch":    primary > 0,
        "dim_mid":      primary >= n_phases // 2 and n_phases >= 2,
        "dim_finale":   primary >= n_phases - 1 and n_phases >= 2,
        "dim_cycle2":   cycle >= 2,
        "dim_streak3":  streak >= 3,
        "dim_streak7":  streak >= 7,
        "dim_active30": span >= 30,
        "dim_active90": span >= 90,
        "dim_reshape":  versions >= 2,
    }

    today = achievement_store.now_date()
    newly = []
    for slot in block["milestones"]:
        if slot.get("unlocked_at"):
            continue
        if checks.get(slot["id"]):
            slot["unlocked_at"] = today
            newly.append({
                "scope": "dimension",
                "dimension_id": dim_id,
                "id": slot["id"],
                "title": slot["title"],
                "description": slot["description"],
                "rarity": slot["rarity"],
            })
    return newly


def _check_global(progress_data, ach_data):
    g = ach_data["global"]
    dims = progress_data.get("dimensions", {})
    all_entries = []
    saw_cross = False
    for dim in dims.values():
        for e in dim.get("entries", []):
            all_entries.append(e)
            if e.get("cross_dimensions"):
                saw_cross = True

    total = len(all_entries)
    n_dims = len(dims)
    streak = calc_streak(all_entries)

    week_ago = date.today() - timedelta(days=7)
    active_dims_week = 0
    for dim in dims.values():
        for e in dim.get("entries", []):
            try:
                d = datetime.fromisoformat(e.get("timestamp", "")).date()
            except Exception:
                continue
            if d >= week_ago:
                active_dims_week += 1
                break

    has_evolve_history = any(len(d.get("phase_versions", [])) >= 2 for d in dims.values())

    checks = {
        "g_three_dims":    active_dims_week >= 3,
        "g_new_continent": n_dims >= 5,
        "g_crossover":     saw_cross,
        "g_streak30":      streak >= 30,
        "g_first_evolve":  has_evolve_history,
        "g_total_50":      total >= 50,
        "g_total_200":     total >= 200,
    }

    today = achievement_store.now_date()
    newly = []
    for slot in g["milestones"]:
        if slot.get("unlocked_at"):
            continue
        if checks.get(slot["id"]):
            slot["unlocked_at"] = today
            newly.append({
                "scope": "global",
                "id": slot["id"],
                "title": slot["title"],
                "description": slot["description"],
                "rarity": slot["rarity"],
            })
    return newly


def check(progress_data, dimension_id=None):
    """传 progress 数据；返回 (新解锁列表, 当前 achievements 数据)。如传 dimension_id 只检查该维度，否则检查全部维度。
    会就地写 achievements.json。"""
    ach = achievement_store.load(progress_data)
    newly = []
    if dimension_id:
        newly.extend(_check_dim(progress_data, ach, dimension_id))
    else:
        for did in progress_data.get("dimensions", {}):
            newly.extend(_check_dim(progress_data, ach, did))
    newly.extend(_check_global(progress_data, ach))
    if newly:
        log.info("新解锁: %s", [f"{x.get('scope')}:{x['id']}" for x in newly])
    achievement_store.save(ach)
    return newly, ach


def add_insight(dimension_id, title, description, rarity="uncommon", progress_data=None):
    """AI 颁发的维度专属洞察成就，去重写入"""
    ach = achievement_store.load(progress_data)
    block = achievement_store.ensure_dimension_block(ach, dimension_id)
    for ins in block["insights"]:
        if ins.get("title") == title:
            return None
    item = {
        "title": title,
        "description": description,
        "rarity": rarity,
        "unlocked_at": achievement_store.now_date(),
    }
    block["insights"].append(item)
    achievement_store.save(ach)
    return {"scope": "dimension", "dimension_id": dimension_id, "kind": "insight", **item}


def add_custom(dimension_id, title, condition_text, rarity="rare", progress_data=None):
    """用户自定义成就 — 默认锁定，由用户/AI 判断是否解锁"""
    ach = achievement_store.load(progress_data)
    if dimension_id == "__global__":
        block = ach["global"]
    else:
        block = achievement_store.ensure_dimension_block(ach, dimension_id)
    item = {
        "title": title,
        "condition_text": condition_text,
        "rarity": rarity,
        "unlocked_at": None,
        "created_at": achievement_store.now_date(),
    }
    block.setdefault("custom", []).append(item)
    achievement_store.save(ach)
    return item


def unlock_custom(dimension_id, title):
    ach = achievement_store.load(None)
    block = ach["global"] if dimension_id == "__global__" else ach.get("per_dimension", {}).get(dimension_id, {})
    for c in block.get("custom", []):
        if c.get("title") == title and not c.get("unlocked_at"):
            c["unlocked_at"] = achievement_store.now_date()
            achievement_store.save(ach)
            return c
    return None
