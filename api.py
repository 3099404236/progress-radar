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
import image_generator

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


def _annotate_image_status(slots):
    """根据磁盘存在情况修正 image_status（防止后台线程崩溃后状态不一致）"""
    for s in slots:
        iid = s.get("image_id")
        if iid and image_generator.has_image(iid):
            s["image_status"] = "ready"
        elif s.get("image_status") == "ready":
            s["image_status"] = "missing"


def _summarize_block(block):
    """成就块概览（每个维度页 + 全局都需要）"""
    ms = block.get("milestones", [])
    ins = block.get("insights", [])
    cust = block.get("custom", [])
    _annotate_image_status(ms)
    _annotate_image_status(ins)
    _annotate_image_status(cust)
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

    def create_custom_achievement(self, dimension_id, title, condition_text, rarity="rare", visual_concept=""):
        try:
            data = data_store.load()
            item = achievement_checker.add_custom(dimension_id, title, condition_text, rarity, visual_concept, data)
            return json.dumps({"status": "ok", "item": item}, ensure_ascii=False)
        except Exception as e:
            log.exception("create_custom_achievement 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 卡面图 ----------

    def get_card_image(self, image_id):
        """返回 data URL；图不存在返回空字符串"""
        try:
            url = image_generator.read_as_data_url(image_id)
            return json.dumps({"status": "ok", "data_url": url or "", "ready": bool(url)}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_card_image 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def regenerate_card_image(self, image_id, visual_concept, rarity="common"):
        """强制重新生成（覆盖旧图）"""
        try:
            path = image_generator.generate(image_id, visual_concept, rarity, force=True)
            url = image_generator.read_as_data_url(image_id) if path else None
            return json.dumps({"status": "ok" if path else "error", "data_url": url or ""}, ensure_ascii=False)
        except Exception as e:
            log.exception("regenerate_card_image 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def warm_card_images(self):
        """对已解锁但还没图的成就，批量补生成（异步触发）。
        老的 insight/custom 缺 visual_concept 的，先用 DeepSeek 给它生一个，再触发生图。"""
        try:
            import theme_generator
            data = data_store.load()
            ach = achievement_store.load(data)
            queued = 0
            enriched = 0

            def dim_label_of(scope_id):
                d = data.get("dimensions", {}).get(scope_id)
                return d["label"] if d else ""

            def kick(slot, dim_label=""):
                nonlocal queued, enriched
                if not slot.get("unlocked_at"):
                    return
                if not slot.get("image_id"):
                    return
                if image_generator.has_image(slot["image_id"]):
                    slot["image_status"] = "ready"
                    return
                # 缺 vc 的：调 DeepSeek 单独生成
                if not slot.get("visual_concept"):
                    vc = theme_generator.generate_vc_for_one(
                        slot.get("title", ""), slot.get("description") or slot.get("condition_text", ""),
                        dim_label, slot.get("rarity", "uncommon"),
                    )
                    if vc:
                        slot["visual_concept"] = vc
                        enriched += 1
                    else:
                        return
                slot["image_status"] = "inflight"
                image_generator.generate_async(slot["image_id"], slot["visual_concept"], slot.get("rarity", "common"))
                queued += 1

            for slot in ach.get("global", {}).get("milestones", []):
                kick(slot, "")
            for did, block in ach.get("per_dimension", {}).items():
                lbl = dim_label_of(did)
                for slot in block.get("milestones", []):
                    kick(slot, lbl)
                for slot in block.get("insights", []):
                    kick(slot, lbl)
                for slot in block.get("custom", []):
                    kick(slot, lbl)
            achievement_store.save(ach)
            return json.dumps({"status": "ok", "queued": queued, "enriched": enriched}, ensure_ascii=False)
        except Exception as e:
            log.exception("warm_card_images 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def unlock_custom_achievement(self, dimension_id, title):
        try:
            item = achievement_checker.unlock_custom(dimension_id, title)
            return json.dumps({"status": "ok", "item": item}, ensure_ascii=False)
        except Exception as e:
            log.exception("unlock_custom 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def regenerate_themed_milestones(self, dimension_id):
        """重新为某维度按主题生成 13 个 milestone 名（覆盖现有 themed）"""
        try:
            import theme_generator
            data = data_store.load()
            dim = data["dimensions"].get(dimension_id)
            if not dim:
                return json.dumps({"status": "error", "message": "维度不存在"}, ensure_ascii=False)
            overrides = theme_generator.generate_for_dimension(
                dim["label"],
                [p["name"] for p in dim["phases"]],
                [p.get("desc", "") for p in dim["phases"]],
            )
            if not overrides:
                return json.dumps({"status": "error", "message": "AI 未返回有效命名"}, ensure_ascii=False)
            achievement_store.apply_themed_milestones(dimension_id, overrides, data)
            return json.dumps({"status": "ok", "count": len(overrides), "items": overrides}, ensure_ascii=False)
        except Exception as e:
            log.exception("regenerate_themed 失败")
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

    def replay_raw(self, raw_id):
        """用当前 prompt 重新处理某条已归档的原文（即使之前是 skip / 重复也会重跑）"""
        try:
            items = raw_archive.read_all()
            item = next((x for x in items if x.get("id") == raw_id), None)
            if not item:
                return json.dumps({"status": "error", "message": "未找到该归档记录"}, ensure_ascii=False)
            text = item["text"]
            data = data_store.load()
            seen = data.setdefault("meta", {}).setdefault("seen_hashes", [])
            text_hash = item.get("text_hash") or ""
            if text_hash in seen:
                seen.remove(text_hash)
            result = ai_processor.process(text, data)
            if result.get("status") == "ok" and result.get("action") in ("update", "create"):
                if text_hash and text_hash not in seen:
                    seen.append(text_hash)
            data_store.save(data)
            if result.get("status") == "ok" and result.get("action") in ("update", "create"):
                try:
                    newly, _ = achievement_checker.check(data, result.get("dimension_id"))
                    if newly:
                        result["unlocked"] = newly
                except Exception:
                    log.exception("成就检查失败")
            try:
                raw_archive.append(text, {**(result or {}), "_replay_of": raw_id})
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log.exception("replay_raw 失败")
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
