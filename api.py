# -*- coding: utf-8 -*-
"""JS Bridge：前端 window.pywebview.api.xxx() 直接调到这里，无需 HTTP"""
import os
import json
import logging
import hashlib
from datetime import datetime, timedelta, date

import config
import data_store
import ai_processor
import achievement_store
import achievement_checker
import raw_archive

log = logging.getLogger("progressradar.api")


def _heat_grid(entries, days=35):
    today = date.today()
    start = today - timedelta(days=days - 1)
    counts = {}
    for e in entries:
        ts = e.get("timestamp", "")
        try:
            d = datetime.fromisoformat(ts).date()
        except Exception:
            continue
        if d < start or d > today:
            continue
        counts[d] = counts.get(d, 0) + 1
    return [counts.get(start + timedelta(days=i), 0) for i in range(days)]


def _summarize_block(block):
    """成就块概览（每个维度页 + 全局都需要）"""
    ms = block.get("milestones", [])
    ins = block.get("insights", [])
    cust = block.get("custom", [])
    unlocked_ms = [m for m in ms if m.get("unlocked_at")]
    unlocked_cust = [c for c in cust if c.get("unlocked_at")]
    next_locked = next((m for m in ms if not m.get("unlocked_at")), None)
    return {
        "milestones": ms,
        "insights": ins,
        "custom": cust,
        "milestone_unlocked": len(unlocked_ms),
        "milestone_total": len(ms),
        "insight_unlocked": len(ins),
        "custom_unlocked": len(unlocked_cust),
        "custom_total": len(cust),
        "total_unlocked": len(unlocked_ms) + len(ins) + len(unlocked_cust),
        "next_milestone": next_locked,
    }


class API:
    def __init__(self):
        self._main_window = None
        self._paste_window = None

    def set_windows(self, main_window, paste_window):
        self._main_window = main_window
        self._paste_window = paste_window

    def ping(self):
        return json.dumps({"ok": True, "methods": [m for m in dir(self) if not m.startswith("_") and callable(getattr(self, m))]}, ensure_ascii=False)

    # ---------- 写入 ----------

    def submit(self, text):
        try:
            text = (text or "").strip()
            if not text:
                return json.dumps({"status": "error", "message": "内容为空"}, ensure_ascii=False)

            data = data_store.load()
            text_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
            seen = data.setdefault("meta", {}).setdefault("seen_hashes", [])
            if text_hash in seen:
                result = {"status": "ok", "action": "skip", "reason": "重复内容（已提交过）"}
                try: raw_archive.append(text, result)
                except Exception: log.exception("归档失败")
                return json.dumps(result, ensure_ascii=False)

            result = ai_processor.process(text, data)

            if result.get("status") == "ok" and result.get("action") in ("update", "create"):
                seen.append(text_hash)
                if len(seen) > 500:
                    del seen[: len(seen) - 500]

            data_store.save(data)

            if result.get("status") == "ok" and result.get("action") in ("update", "create"):
                try:
                    newly, _ = achievement_checker.check(data, result.get("dimension_id"))
                    if newly:
                        result["unlocked"] = newly
                except Exception:
                    log.exception("成就检查失败")

            try:
                raw_archive.append(text, result)
            except Exception:
                log.exception("归档失败")

            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log.exception("submit 崩溃")
            return json.dumps({"status": "error", "message": f"submit 异常: {type(e).__name__}: {e}"}, ensure_ascii=False)

    def confirm_evolution(self, evolution_id, accepted):
        data = data_store.load()
        result = ai_processor.confirm_evolution(data, evolution_id, bool(accepted))
        data_store.save(data)
        return json.dumps(result, ensure_ascii=False)

    def resolve_confirm(self, confirm_id, dimension_id):
        data = data_store.load()
        result = ai_processor.resolve_confirm(data, confirm_id, dimension_id)
        data_store.save(data)
        return json.dumps(result, ensure_ascii=False)

    # ---------- 读取 ----------

    def get_dimensions(self, cycle_filter="current"):
        """cycle_filter: 'current' | 'all'"""
        data = data_store.load()
        try:
            ach = achievement_store.load(data)
        except Exception:
            ach = {"per_dimension": {}, "global": {}}
        dims_out = []
        for dim_id, dim in data["dimensions"].items():
            entries = dim.get("entries", [])
            cur_cycle = dim.get("current_cycle", 1)
            if cycle_filter == "current":
                visible = [e for e in entries if e.get("cycle", 1) == cur_cycle]
            else:
                visible = entries

            recent_entries = []
            for e in reversed(visible):
                ts = e.get("timestamp", "")
                try:
                    mmdd = datetime.fromisoformat(ts).strftime("%m/%d")
                except Exception:
                    mmdd = ts[:10]
                recent_entries.append({
                    "d": mmdd,
                    "t": e.get("summary", ""),
                    "tag": e.get("tag", ""),
                    "phase_index": e.get("phase_index", 0),
                    "cycle": e.get("cycle", 1),
                })

            block = ach.get("per_dimension", {}).get(dim_id, {})
            ach_summary = _summarize_block(block)

            stats = {
                "total_entries": len(visible),
                "all_total": len(entries),
                "active_days": achievement_checker.calc_active_days(visible),
                "max_streak": achievement_checker.calc_max_streak(visible),
                "current_streak": achievement_checker.calc_streak(visible),
                "span_days": achievement_checker.calc_span_days(visible),
                "this_week": sum(1 for v in _heat_grid(visible, 35)[-7:] if v),
            }

            dims_out.append({
                "id": dim_id,
                "label": dim["label"],
                "phases": [p["name"] for p in dim["phases"]],
                "phase_descs": [p.get("desc", "") for p in dim["phases"]],
                "primary_phase": dim.get("primary_phase", dim.get("current_stage", 0)),
                "current_stage": dim.get("current_stage", 0),
                "phase_activity": dim.get("phase_activity", [0] * len(dim["phases"])),
                "recent_phases": dim.get("recent_phases", []),
                "current_cycle": cur_cycle,
                "cycles": dim.get("cycles", []),
                "phase_versions": dim.get("phase_versions", []),
                "entries": recent_entries,
                "stats": stats,
                "total_entries": len(visible),
                "all_total": len(entries),
                "heat": _heat_grid(visible),
                "heat_90": _heat_grid(visible, 90),
                "created_by": dim.get("created_by", "preset"),
                "milestones": dim.get("milestones", []),
                "achievements": ach_summary,
            })
        meta = data.get("meta", {})
        return json.dumps({
            "dimensions": dims_out,
            "meta": {
                "total_entries": meta.get("total_entries", 0),
                "last_updated": meta.get("last_updated"),
                "cycle_filter": cycle_filter,
            },
            "global_achievements": _summarize_block(ach.get("global", {})),
        }, ensure_ascii=False)

    def get_weekly_report(self):
        if not os.path.isdir(config.WEEKLY_DIR):
            return json.dumps({"status": "ok", "report": None}, ensure_ascii=False)
        files = sorted(os.listdir(config.WEEKLY_DIR), reverse=True)
        if not files:
            return json.dumps({"status": "ok", "report": None}, ensure_ascii=False)
        latest = os.path.join(config.WEEKLY_DIR, files[0])
        with open(latest, "r", encoding="utf-8") as f:
            return json.dumps({"status": "ok", "report": f.read(), "file": files[0]}, ensure_ascii=False)

    def generate_weekly_report(self):
        import weekly_report
        data = data_store.load()
        try:
            text = weekly_report.generate(data)
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        os.makedirs(config.WEEKLY_DIR, exist_ok=True)
        fname = datetime.now().strftime("%Y-%m-%d") + "_weekly.md"
        path = os.path.join(config.WEEKLY_DIR, fname)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return json.dumps({"status": "ok", "file": fname, "report": text}, ensure_ascii=False)

    # ---------- 窗口控制 ----------

    def show_dashboard(self):
        if self._main_window:
            self._main_window.show()
        return json.dumps({"ok": True})

    def show_paste(self):
        if self._paste_window:
            try:
                self._paste_window.show()
                try:
                    self._paste_window.evaluate_js(
                        "(function(){var a=document.getElementById('paste-area');"
                        "if(a){a.focus();}})();"
                    )
                except Exception:
                    pass
            except Exception as e:
                log.exception("show_paste 失败")
                return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)
        return json.dumps({"ok": True})

    def hide_paste(self):
        if self._paste_window:
            self._paste_window.hide()
        return json.dumps({"ok": True})

    def hide_dashboard(self):
        if self._main_window:
            self._main_window.hide()
        return json.dumps({"ok": True})

    # ---------- 成就 ----------

    def get_achievements(self):
        try:
            data = data_store.load()
            ach = achievement_store.load(data)
            return json.dumps({"status": "ok", "data": ach}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_achievements 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def create_custom_achievement(self, dimension_id, title, condition_text, rarity="rare"):
        try:
            data = data_store.load()
            item = achievement_checker.add_custom(dimension_id, title, condition_text, rarity, data)
            return json.dumps({"status": "ok", "item": item}, ensure_ascii=False)
        except Exception as e:
            log.exception("create_custom_achievement 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def unlock_custom_achievement(self, dimension_id, title):
        try:
            item = achievement_checker.unlock_custom(dimension_id, title)
            return json.dumps({"status": "ok", "item": item}, ensure_ascii=False)
        except Exception as e:
            log.exception("unlock_custom 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def recheck_achievements(self):
        """手动重算所有成就（调试 / 修复用）"""
        try:
            data = data_store.load()
            newly, _ = achievement_checker.check(data, None)
            return json.dumps({"status": "ok", "unlocked": newly}, ensure_ascii=False)
        except Exception as e:
            log.exception("recheck 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 原始归档 ----------

    def get_raw_stats(self):
        try:
            return json.dumps({"status": "ok", **raw_archive.stats()}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_raw_stats 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def get_raw_recent(self, limit=20):
        try:
            items = raw_archive.read_all(limit=limit)
            for it in items:
                t = it.get("text", "")
                if len(t) > 800:
                    it["text"] = t[:800] + " …[已截断，原文存于 jsonl]"
            return json.dumps({"status": "ok", "items": items}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_raw_recent 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def export_raw_to_desktop(self):
        try:
            home = os.environ.get("USERPROFILE") or os.path.expanduser("~")
            desktop = os.path.join(home, "Desktop")
            if not os.path.isdir(desktop):
                desktop = os.path.join(home, "OneDrive", "Desktop")
            if not os.path.isdir(desktop):
                desktop = home
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            dst = os.path.join(desktop, f"progressradar_raw_{ts}.jsonl")
            count, path = raw_archive.export_to(dst)
            return json.dumps({"status": "ok", "count": count, "path": path}, ensure_ascii=False)
        except Exception as e:
            log.exception("export_raw 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 手动编辑 ----------

    def edit_dimension(self, dimension_id, payload_json):
        data = data_store.load()
        dim = data["dimensions"].get(dimension_id)
        if not dim:
            return json.dumps({"status": "error", "message": "维度不存在"}, ensure_ascii=False)
        try:
            payload = json.loads(payload_json) if isinstance(payload_json, str) else (payload_json or {})
        except Exception:
            payload = {}
        if "label" in payload:
            dim["label"] = payload["label"]
        if "current_stage" in payload:
            dim["current_stage"] = max(0, min(int(payload["current_stage"]), len(dim["phases"]) - 1))
        if "phases" in payload and isinstance(payload["phases"], list):
            new_phases = []
            for p in payload["phases"]:
                if isinstance(p, dict):
                    new_phases.append({"name": p.get("name", "?"), "desc": p.get("desc", "")})
                else:
                    new_phases.append({"name": str(p), "desc": ""})
            dim["phases"] = new_phases
        data_store.save(data)
        return json.dumps({"status": "ok"}, ensure_ascii=False)

    def delete_dimension(self, dimension_id):
        data = data_store.load()
        if dimension_id in data["dimensions"]:
            del data["dimensions"][dimension_id]
            data_store.save(data)
        return json.dumps({"status": "ok"}, ensure_ascii=False)
