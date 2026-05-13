# -*- coding: utf-8 -*-
"""JS Bridge：前端 window.pywebview.api.xxx() 直接调到这里，无需 HTTP"""
import functools
import os
import json
import logging
import hashlib
from datetime import datetime, timedelta, date

import threading

import config
import data_store
import ai_processor
import achievement_store
import achievement_checker
import raw_archive
import image_generator
import notes_store

log = logging.getLogger("progressradar.api")

# 全局互斥锁：所有改 progress.json 的入口共用，保证 load → 改 → save 原子
# pywebview js_api 每次调用一个独立线程，必须串行化对 progress 的写入
_submit_lock = threading.RLock()


def _notify_after(fn):
    """装饰器：方法跑完后通知 dashboard 立即重 load
    用 evaluate_js 跨窗口发 'progress-changed' 事件，dashboard.js 监听刷新。
    如果返回的 JSON 含 unlocked / insight，再派 'chest-show' 事件触发开箱动画。"""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        result = fn(self, *args, **kwargs)
        try:
            if self._main_window:
                self._main_window.evaluate_js(
                    "window.dispatchEvent(new Event('progress-changed'));"
                )
                # 解析返回值收集解锁项目
                try:
                    parsed = json.loads(result) if isinstance(result, str) else result
                    chest_items = _collect_chest_items(parsed)
                    if chest_items:
                        items_js = json.dumps(chest_items, ensure_ascii=False)
                        self._main_window.evaluate_js(
                            f"window.dispatchEvent(new CustomEvent('chest-show', {{detail: {items_js}}}));"
                        )
                except Exception:
                    pass
        except Exception:
            log.exception("notify dashboard 失败")
        return result
    return wrapper


def _collect_chest_items(result):
    """从 submit/replay 的返回里抽出"待开宝箱"列表 — milestone unlocked + insight"""
    if not isinstance(result, dict):
        return []
    items = []
    seen_titles = set()
    for u in (result.get("unlocked") or []):
        if not u.get("title"): continue
        key = (u.get("scope", "dimension"), u["title"])
        if key in seen_titles: continue
        seen_titles.add(key)
        items.append({
            "title": u.get("title", ""),
            "description": u.get("description", ""),
            "rarity": u.get("rarity", "common"),
            "scope": u.get("scope", "dimension"),
            "image_id": u.get("image_id"),
            "visual_concept": u.get("visual_concept", ""),
            "kind": "milestone",
        })
    ins = result.get("insight")
    if isinstance(ins, dict) and ins.get("title"):
        key = ("dimension", ins["title"])
        if key not in seen_titles:
            seen_titles.add(key)
            items.append({
                "title": ins.get("title", ""),
                "description": ins.get("description", ""),
                "rarity": ins.get("rarity", "uncommon"),
                "scope": "dimension",
                "image_id": ins.get("image_id"),
                "visual_concept": ins.get("visual_concept", ""),
                "kind": "insight",
            })
    # multi action：每个 sub 的 insight 也要收
    for r in (result.get("results") or []):
        ins = r.get("insight") if isinstance(r, dict) else None
        if isinstance(ins, dict) and ins.get("title"):
            key = ("dimension", ins["title"])
            if key in seen_titles: continue
            seen_titles.add(key)
            items.append({
                "title": ins["title"],
                "description": ins.get("description", ""),
                "rarity": ins.get("rarity", "uncommon"),
                "scope": "dimension",
                "image_id": ins.get("image_id"),
                "visual_concept": ins.get("visual_concept", ""),
                "kind": "insight",
            })
    return items


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


def _today_summary(data):
    """统计今天的活跃情况 + 给一句最优先的提醒"""
    today_iso = date.today().isoformat()
    by_track = {"must": 0, "main": 0, "side": 0}
    active_dims_today = set()
    must_pending = []
    timeline_today = []
    total = 0
    for did, dim in data.get("dimensions", {}).items():
        if dim.get("state", "active") != "active":
            continue
        track = dim.get("track", "main")
        had_today = False
        for e in dim.get("entries", []):
            ts = e.get("timestamp", "")
            try:
                if datetime.fromisoformat(ts).date().isoformat() == today_iso:
                    by_track[track] = by_track.get(track, 0) + 1
                    active_dims_today.add(did)
                    total += 1
                    had_today = True
            except Exception:
                continue
        if track == "must" and not had_today:
            must_pending.append({"id": did, "label": dim.get("label", "")})
        for ev in dim.get("timeline", []):
            if ev.get("date") == today_iso:
                timeline_today.append({
                    "dim": dim.get("label", ""),
                    "label": ev.get("label", ""),
                    "note": ev.get("note", ""),
                })

    # 多条并发信号（每条独立一种颜色 / 严重度）
    signals = []
    m_cnt, s_cnt, mu_cnt = by_track["main"], by_track["side"], by_track["must"]

    # urgent — 今天到期的 timeline
    if timeline_today:
        labels = "、".join(e["label"] for e in timeline_today[:3])
        more = f"（共 {len(timeline_today)}）" if len(timeline_today) > 3 else ""
        signals.append({"level": "urgent", "kind": "timeline",
                        "text": f"今天有「{labels}」{more}，记得安排时间"})

    # info — 完全没动
    if total == 0:
        signals.append({"level": "info", "kind": "idle",
                        "text": "还没记录今天的事，要不要从最轻松的一件开始？"})
    else:
        # info — 日常基本盘可以补
        if must_pending:
            labels = " / ".join(m["label"] for m in must_pending[:3])
            more = f" 等 {len(must_pending)} 项" if len(must_pending) > 3 else ""
            signals.append({"level": "info", "kind": "must",
                            "text": f"建议补一下日常：{labels}{more}"})

        # info — 主线 / 支线比例
        if s_cnt >= 2 and s_cnt > m_cnt * 2:
            signals.append({"level": "info", "kind": "ratio",
                            "text": f"支线已经 {s_cnt} 条，主线方向也可以分一点注意力"})
        elif m_cnt == 0 and (s_cnt + mu_cnt) >= 2:
            signals.append({"level": "info", "kind": "main_zero",
                            "text": "推荐挑一件主线上的事推进一下"})
        elif m_cnt >= 2 and s_cnt == 0 and mu_cnt == 0:
            signals.append({"level": "info", "kind": "main_only",
                            "text": "今天主线状态不错，记得也照顾下日常基本盘"})

        # good — 主线已动 + 必做都覆盖（且没有其他建议）
        has_other = any(sg["level"] in ("warn", "info") for sg in signals)
        if not has_other and m_cnt >= 1 and not must_pending:
            signals.append({"level": "good", "kind": "balanced",
                            "text": "节奏不错，主线和必做都覆盖到了"})

    # 排序：urgent > warn > info > good
    order = {"urgent": 0, "warn": 1, "info": 2, "good": 3}
    signals.sort(key=lambda x: order.get(x.get("level", "info"), 5))

    # 兼容字段（旧 UI 用）
    hint = signals[0]["text"] if signals else "—"
    hint_kind = signals[0]["level"] if signals else "info"
    if hint_kind == "urgent": hint_kind = "warn"  # 旧 UI 没有 urgent

    return {
        "total_today": total,
        "active_dims_today": len(active_dims_today),
        "by_track": by_track,
        "must_pending": must_pending[:5],
        "timeline_today": timeline_today[:5],
        "signals": signals,
        "hint": hint,
        "hint_kind": hint_kind,
    }


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

    @_notify_after
    def submit(self, text):
        # 全局串行化：避免并发提交时 load→改→save 互相覆盖
        with _submit_lock:
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

                written = (
                    result.get("status") == "ok"
                    and result.get("action") in ("update", "create", "multi")
                )
                if written:
                    seen.append(text_hash)
                    if len(seen) > 500:
                        del seen[: len(seen) - 500]

                data_store.save(data)

                if written:
                    try:
                        if result.get("action") == "multi":
                            all_unlocked = []
                            for r in result.get("results", []):
                                if r.get("status") == "ok" and r.get("action") in ("update", "create"):
                                    newly, _ = achievement_checker.check(data, r.get("dimension_id"))
                                    if newly:
                                        r["unlocked"] = newly
                                        all_unlocked.extend(newly)
                            if all_unlocked:
                                result["unlocked"] = all_unlocked
                        else:
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

    @_notify_after
    def confirm_evolution(self, evolution_id, accepted):
        with _submit_lock:
            data = data_store.load()
            result = ai_processor.confirm_evolution(data, evolution_id, bool(accepted))
            data_store.save(data)
            return json.dumps(result, ensure_ascii=False)

    @_notify_after
    def resolve_confirm(self, confirm_id, dimension_id):
        with _submit_lock:
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
                "created_at": dim.get("created_at", ""),
                "milestones": dim.get("milestones", []),
                "achievements": ach_summary,
                "track": dim.get("track", "main"),
                "rank": dim.get("rank", 9999),
                "state": dim.get("state", "active"),
                "state_changed_at": dim.get("state_changed_at"),
                "timeline": sorted(dim.get("timeline", []), key=lambda x: x.get("date", "")),
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
            "today": _today_summary(data),
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
        """显示粘贴窗口并强制置顶 + 抢焦点"""
        if not self._paste_window:
            return json.dumps({"ok": True})
        try:
            self._paste_window.show()
            # restore() 会调 SetForegroundWindow 把窗口拉到前面（pywebview 5.4 无 focus()）
            try: self._paste_window.restore()
            except Exception: pass
            # 兜底：用 ctypes 调 Win32 SetForegroundWindow / BringWindowToTop
            try:
                import ctypes
                user32 = ctypes.windll.user32
                hwnd = user32.FindWindowW(None, "快速粘贴")
                if hwnd:
                    user32.ShowWindow(hwnd, 5)         # SW_SHOW
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
            except Exception:
                pass
            # 把焦点打到 textarea
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

    @_notify_after
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
        老的 insight/custom 缺 visual_concept 的，先用 DeepSeek 给它生一个，再触发生图。
        会先清空 inflight 残留状态，确保上次进程被杀掉的图能被重新触发。"""
        try:
            import theme_generator
            image_generator.reset_inflight()  # 清掉跨进程残留
            data = data_store.load()
            ach = achievement_store.load(data)
            queued = 0
            enriched = 0
            # 同步把磁盘已有但状态不对的修正
            for s in ach.get("global", {}).get("milestones", []):
                if s.get("image_id") and image_generator.has_image(s["image_id"]):
                    s["image_status"] = "ready"
            for did, blk in ach.get("per_dimension", {}).items():
                for arr in (blk.get("milestones", []), blk.get("insights", []), blk.get("custom", [])):
                    for s in arr:
                        if s.get("image_id") and image_generator.has_image(s["image_id"]):
                            s["image_status"] = "ready"

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

    @_notify_after
    def unlock_custom_achievement(self, dimension_id, title):
        try:
            item = achievement_checker.unlock_custom(dimension_id, title)
            return json.dumps({"status": "ok", "item": item}, ensure_ascii=False)
        except Exception as e:
            log.exception("unlock_custom 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    @_notify_after
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

    @_notify_after
    def replay_raw(self, raw_id):
        """用当前 prompt 重新处理某条已归档的原文（即使之前是 skip / 重复也会重跑）。
        replay 走完后会同步等待新解锁成就的图都生成完，避免 daemon 线程被杀图丢失。"""
        _submit_lock.acquire()
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
                        # 同步等图生成完，避免脚本进程退出时 daemon 线程被杀
                        ach = achievement_store.load(data)
                        for u in newly:
                            iid = u.get("image_id")
                            if iid and not image_generator.has_image(iid):
                                slot = self._find_slot_by_image_id(ach, iid)
                                if slot and slot.get("visual_concept"):
                                    image_generator.generate(iid, slot["visual_concept"], slot.get("rarity", "common"))
                                    slot["image_status"] = "ready"
                        achievement_store.save(ach)
                except Exception:
                    log.exception("成就检查/同步生图失败")
            try:
                raw_archive.append(text, {**(result or {}), "_replay_of": raw_id})
            except Exception:
                pass
            return json.dumps(result, ensure_ascii=False)
        except Exception as e:
            log.exception("replay_raw 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)
        finally:
            _submit_lock.release()

    @staticmethod
    def _find_slot_by_image_id(ach, image_id):
        for s in ach.get("global", {}).get("milestones", []):
            if s.get("image_id") == image_id: return s
        for blk in ach.get("per_dimension", {}).values():
            for arr in (blk.get("milestones", []), blk.get("insights", []), blk.get("custom", [])):
                for s in arr:
                    if s.get("image_id") == image_id: return s
        return None

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

    # ---------- 全局竞技场天梯 ----------

    def get_arena_state(self):
        """全局成就重组成"竞技场天梯"，按门槛递增。
        cups = 总 entries 数；解锁状态仍按 milestone 自身规则判断。"""
        try:
            from achievement_templates import ARENA_ORDER
            data = data_store.load()
            ach = achievement_store.load(data)
            cups = sum(len(d.get("entries", [])) for d in data.get("dimensions", {}).values())
            ms_by_id = {m["id"]: m for m in ach.get("global", {}).get("milestones", [])}

            arenas = []
            for i, ao in enumerate(ARENA_ORDER):
                slot = ms_by_id.get(ao["id"], {})
                unlocked = bool(slot.get("unlocked_at"))
                arenas.append({
                    "id": ao["id"],
                    "title": slot.get("title", ""),
                    "description": slot.get("description", ""),
                    "rarity": slot.get("rarity", "common"),
                    "image_id": slot.get("image_id", ""),
                    "visual_concept": slot.get("visual_concept", ""),
                    "threshold": ao["threshold"],
                    "unlocked": unlocked,
                    "unlocked_at": slot.get("unlocked_at"),
                    "position": i + 1,
                })

            # current = "最近一次解锁"（按 unlocked_at 取最新；主页中央展示这阶）
            current_idx = -1
            most_recent_ts = ""
            for i, a in enumerate(arenas):
                ts = a.get("unlocked_at") or ""
                if a["unlocked"] and ts > most_recent_ts:
                    most_recent_ts = ts
                    current_idx = i

            # next = 按门槛从低到高第一个未解锁（进度条目标）
            next_idx = None
            for i, a in enumerate(arenas):
                if not a["unlocked"]:
                    next_idx = i
                    break

            if next_idx is not None:
                # 进度从"上一阶门槛"算起，没上一阶（next_idx=0）就从 0 算
                from_t = arenas[next_idx - 1]["threshold"] if next_idx > 0 else 0
                to_t = arenas[next_idx]["threshold"]
                span = max(1, to_t - from_t)
                progress = max(0.0, min(1.0, (cups - from_t) / span))
                cups_to_next = max(0, to_t - cups)
            else:
                progress = 1.0
                cups_to_next = 0

            return json.dumps({
                "status": "ok",
                "cups": cups,
                "arenas": arenas,
                "current_idx": current_idx,
                "next_idx": next_idx,
                "progress_to_next": progress,
                "cups_to_next": cups_to_next,
                "max_arena": len(arenas),
            }, ensure_ascii=False)
        except Exception as e:
            log.exception("get_arena_state 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 记事本（单个临时草稿） ----------

    def get_scratchpad(self):
        try:
            return json.dumps({"status": "ok", **notes_store.load()}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_scratchpad 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def save_scratchpad(self, content):
        try:
            meta = notes_store.save(content or "")
            return json.dumps({"status": "ok", "updated_at": meta["updated_at"]}, ensure_ascii=False)
        except Exception as e:
            log.exception("save_scratchpad 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    def get_scratchpad_history(self):
        try:
            return json.dumps({"status": "ok", "history": notes_store.list_history()}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_scratchpad_history 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 今日活动列表 ----------

    def get_today_entries(self):
        try:
            today_iso = date.today().isoformat()
            data = data_store.load()
            items = []
            for did, dim in data["dimensions"].items():
                if dim.get("state", "active") != "active":
                    continue
                phases = dim.get("phases", [])
                for e in dim.get("entries", []):
                    ts = e.get("timestamp", "")
                    try:
                        if datetime.fromisoformat(ts).date().isoformat() != today_iso:
                            continue
                    except Exception:
                        continue
                    pi = e.get("phase_index", 0)
                    pname = phases[pi]["name"] if 0 <= pi < len(phases) else ""
                    items.append({
                        "ts": ts,
                        "time": ts[11:16] if len(ts) >= 16 else ts,
                        "dim_id": did,
                        "dim_label": dim.get("label", ""),
                        "track": dim.get("track", "main"),
                        "phase_index": pi,
                        "phase_name": pname,
                        "summary": e.get("summary", ""),
                        "tag": e.get("tag", ""),
                        "key_progress": e.get("key_progress", []),
                        "cycle": e.get("cycle", 1),
                        "cross_dimensions": e.get("cross_dimensions", []),
                    })
            items.sort(key=lambda x: x["ts"], reverse=True)
            return json.dumps({"status": "ok", "items": items, "count": len(items)}, ensure_ascii=False)
        except Exception as e:
            log.exception("get_today_entries 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 时间轴 ----------

    @_notify_after
    def add_timeline_event(self, dimension_id, date, label, note=""):
        """date: YYYY-MM-DD"""
        try:
            import hashlib, re as _re
            if not _re.match(r"^\d{4}-\d{2}-\d{2}$", str(date)):
                return json.dumps({"status": "error", "message": "日期格式应为 YYYY-MM-DD"}, ensure_ascii=False)
            data = data_store.load()
            d = data["dimensions"].get(dimension_id)
            if not d:
                return json.dumps({"status": "error", "message": "维度不存在"}, ensure_ascii=False)
            timeline = d.setdefault("timeline", [])
            eid = hashlib.md5((date + "|" + label).encode("utf-8")).hexdigest()[:10]
            if any(e.get("id") == eid for e in timeline):
                return json.dumps({"status": "ok", "duplicated": True}, ensure_ascii=False)
            timeline.append({
                "id": eid, "date": date, "label": label[:24], "note": (note or "")[:80],
                "added_at": datetime.now().isoformat(timespec="seconds"),
            })
            timeline.sort(key=lambda x: x.get("date", ""))
            data_store.save(data)
            return json.dumps({"status": "ok", "id": eid}, ensure_ascii=False)
        except Exception as e:
            log.exception("add_timeline_event 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    @_notify_after
    def remove_timeline_event(self, dimension_id, event_id):
        try:
            data = data_store.load()
            d = data["dimensions"].get(dimension_id)
            if not d: return json.dumps({"status": "error", "message": "维度不存在"}, ensure_ascii=False)
            d["timeline"] = [e for e in d.get("timeline", []) if e.get("id") != event_id]
            data_store.save(data)
            return json.dumps({"status": "ok"}, ensure_ascii=False)
        except Exception as e:
            log.exception("remove_timeline_event 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 维度状态：进行中 / 荣誉 / 忽视 ----------

    @_notify_after
    def set_dim_state(self, dimension_id, state):
        """state ∈ {'active', 'honored', 'ignored'}"""
        try:
            if state not in ("active", "honored", "ignored"):
                return json.dumps({"status": "error", "message": "无效 state"}, ensure_ascii=False)
            data = data_store.load()
            d = data["dimensions"].get(dimension_id)
            if not d:
                return json.dumps({"status": "error", "message": "维度不存在"}, ensure_ascii=False)
            d["state"] = state
            d["state_changed_at"] = datetime.now().isoformat(timespec="seconds")
            data_store.save(data)
            return json.dumps({"status": "ok", "state": state}, ensure_ascii=False)
        except Exception as e:
            log.exception("set_dim_state 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 主线/支线/必做 三栏布局 ----------

    @_notify_after
    def set_track_layout(self, layout_json):
        """layout_json: '{"must":["id1","id2"],"main":["id3"],"side":["id4"]}'
        前端拖完整理出每栏的有序 ID 列表，整体覆盖。"""
        try:
            layout = json.loads(layout_json) if isinstance(layout_json, str) else layout_json
            data = data_store.load()
            updated = 0
            for track in ("must", "main", "side"):
                ids = layout.get(track) or []
                for idx, did in enumerate(ids):
                    d = data["dimensions"].get(did)
                    if d:
                        d["track"] = track
                        d["rank"] = idx
                        updated += 1
            data_store.save(data)
            return json.dumps({"status": "ok", "updated": updated}, ensure_ascii=False)
        except Exception as e:
            log.exception("set_track_layout 失败")
            return json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False)

    # ---------- 手动编辑 ----------

    @_notify_after
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

    @_notify_after
    def delete_dimension(self, dimension_id):
        data = data_store.load()
        if dimension_id in data["dimensions"]:
            del data["dimensions"][dimension_id]
            data_store.save(data)
        return json.dumps({"status": "ok"}, ensure_ascii=False)
