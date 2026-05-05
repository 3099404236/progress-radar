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
                return json.dumps({"status": "ok", "action": "skip", "reason": "重复内容（已提交过）"}, ensure_ascii=False)

            result = ai_processor.process(text, data)

            if result.get("status") == "ok" and result.get("action") in ("update", "create"):
                seen.append(text_hash)
                if len(seen) > 500:
                    del seen[: len(seen) - 500]

            data_store.save(data)
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
        dims_out = []
        for dim_id, dim in data["dimensions"].items():
            entries = dim.get("entries", [])
            cur_cycle = dim.get("current_cycle", 1)
            if cycle_filter == "current":
                visible = [e for e in entries if e.get("cycle", 1) == cur_cycle]
            else:
                visible = entries

            recent_entries = []
            for e in reversed(visible[-10:]):
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
                "total_entries": len(visible),
                "all_total": len(entries),
                "heat": _heat_grid(visible),
                "created_by": dim.get("created_by", "preset"),
                "milestones": dim.get("milestones", []),
            })
        meta = data.get("meta", {})
        return json.dumps({
            "dimensions": dims_out,
            "meta": {
                "total_entries": meta.get("total_entries", 0),
                "last_updated": meta.get("last_updated"),
                "cycle_filter": cycle_filter,
            },
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
