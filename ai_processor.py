# -*- coding: utf-8 -*-
"""DeepSeek 调用 + v2 action 处理 (update / create / evolve / confirm / skip)"""
import json
import logging
import re
import hashlib
from datetime import datetime
import httpx
from openai import OpenAI

import config
import data_store
import achievement_store
import achievement_checker

log = logging.getLogger("progressradar.ai")

_client = None


def get_client():
    global _client
    if _client is None:
        # trust_env=False: 忽略系统/环境的 HTTP(S)_PROXY，直连 DeepSeek（国内可达）
        http_client = httpx.Client(trust_env=False, timeout=60.0)
        _client = OpenAI(
            api_key=config.DEEPSEEK_API_KEY,
            base_url=config.DEEPSEEK_BASE_URL,
            http_client=http_client,
        )
        log.info("OpenAI client 已创建（trust_env=False, 不走系统代理）")
    return _client


SYSTEM_PROMPT = """你是一个个人进度追踪AI。用户会粘贴各种文本，你需要分析并返回结构化JSON。

## 已有维度（含阶段分布与最近行为模式）
{dimensions_summary}

## 你的任务

### 第一步：维度识别
- 逐一比对已有维度，判断内容是否属于某个维度
- 判断标准：内容核心主题与该维度标签和历史记录是否一致
- 如果匹配度都很低（没有一个维度的相关性超过60%）→ 创建新维度
- 如果不确定（相关性在40%-60%之间）→ 返回 confirm 让用户选

### 第二步：如果是新维度，设计阶段路径
阶段设计规则：
- 3-6个阶段，每个阶段对应至少一周至多几个月的时间尺度
- 根据领域性质选模式：
  研究类 → 调研/理论/实验/写作/投稿
  技能类 → 入门/基础/进阶/熟练/精通
  项目类 → 规划/开发/测试/上线/迭代
  考试类 → 梳理重点/基础概念/题目练习/冲刺/考试
  决策类 → 信息收集/方向评估/决策/准备/执行
  习惯/健康/生活方式类 → 起步尝试/建立规律/巩固稳定/内化自动/精进优化
  其他 → 根据内容逻辑自行设计
- 阶段名4字以内中文短语，附一句话description
- 阶段反映该领域通用进展模式

### 第三步：阶段归属（非线性）⭐
- 根据本次内容判断它属于哪个阶段（phase_index），与维度的primary_phase无关
- 用户允许任意跳跃，比如在"实验"阶段做"理论"工作，这完全正常
- phase_index 是 0-based 索引

### 第四步：阶段演化检测 ⭐
检查以下条件，任一满足则不返回 update，而返回 action="evolve"：
1. 本次内容确实属于这个维度，但不属于当前任何阶段的描述范围
2. 维度的 recent_phases 显示在3个以上阶段间频繁跳跃，且当前阶段划分难以描述
3. 用户明确说"重新组织阶段""阶段不合适"等

evolve 时给出 proposed_phases (3-6个) 和 entry_remapping（说明旧阶段索引如何映射到新阶段索引）。

### 第五步：周期检测 ⭐
如果出现以下信号，在 update 中附上 cycle_event：
1. 用户在该维度的最终阶段之后又回到了早期阶段性质的工作（如论文投稿后开始改稿、考试结束后开下学期课）
2. 明确出现"重新开始""新一轮""被拒重投"等信号

cycle_event = {{"type":"new_cycle","reason":"...","new_cycle_number":N,"reset_primary_to":phase_index}}

### 第六步：进展提取
- 提取具体的、可衡量的"做了什么/完成了什么/发现了什么"
- 包括行为类记录：早起、运动、阅读、冥想、戒糖、写日记 — 这些都算具体行为
- 不要提取的：纯情绪宣泄、对天气/食物的随感、与任何行为无关的吐槽
- 给一个 tag：实验/代码/写作/理论/信息/行动/里程碑/发现/调试/部署/习惯

⚠️ skip 判定要严格（绝大多数情况都不应该 skip）：
- 仅当内容**完全不包含**任何可观测行为或进展时才 skip
- "今天早起了" / "做了一组俯卧撑" / "读了 3 章书" — 都是行为，不能 skip，应当归类到对应维度（无对应维度则 create）
- 用户主动追踪一件事就有意义；维度没有"重要"门槛
- 反例（应当 skip）："今天天气真好"、"心情不太好"、"食堂菜难吃" — 这些是纯感受，无行为

### 第七步：下一步建议
- 1-3个具体可执行的下一步

### 第八步：维度专属洞察成就（高度可选，绝大多数 update 应为 null）⭐
- 每个维度有自己的"洞察"成就池。如果本次提交在所属维度内代表一个真正的转折点（不是普通进展），才颁发
- 类型参考：方法突破 / 质量跃迁 / 关键发现 / 瓶颈突破 / 意外连接
- title: 4-6 字中文短语；description: 一句话说原因
- rarity: common（小亮点）/ uncommon（明显进步）/ rare（突破）/ epic（罕见里程碑）
- 已颁发过的洞察会列在维度摘要里，**绝对不要换汤不换药地重复**
- create 维度时也可以附 achievement，对"开新方向"这类标记有意义

## 输出格式
严格 JSON，以下场景之一：

A. 匹配已有维度 → update：
{{"action":"update","dimension_id":"...","summary":"...","key_progress":["..."],"tag":"...","phase_index":N,"progress_delta":"...","next_steps":["..."],"cross_dimensions":[],"cycle_event":null,"achievement":null}}

B. 创建新维度 → create：
{{"action":"create","dimension_id":"snake_case","dimension_label":"中文标签","reason":"为什么不属于已有维度","phases":[{{"name":"...","desc":"..."}}],"initial_phase_index":0,"summary":"...","key_progress":["..."],"tag":"...","next_steps":["..."],"achievement":null}}

C. 阶段演化 → evolve：
{{"action":"evolve","dimension_id":"...","reason":"...","current_phases":["..."],"proposed_phases":[{{"name":"...","desc":"..."}}],"entry_remapping":[{{"old_phase":N,"new_phase":M}}],"summary":"...","key_progress":["..."],"tag":"...","phase_index_after_evolve":N}}

D. 需要确认 → confirm：
{{"action":"confirm","question":"...","options":[{{"label":"...","dimension_id":"existing_or_new_id"}}],"summary":"...","key_progress":["..."],"tag":"..."}}

E. 无实质进展 → skip：
{{"action":"skip","reason":"..."}}

只输出 JSON，dimension_id 必须 snake_case 英文。"""


def _build_dimensions_summary(data):
    dims = data.get("dimensions", {})
    if not dims:
        return "（暂无维度，首次使用）"
    try:
        ach = achievement_store.load(data)
    except Exception:
        ach = {"per_dimension": {}}
    lines = []
    for dim_id, dim in dims.items():
        phases = [p["name"] for p in dim.get("phases", [])]
        recent = dim.get("entries", [])[-3:]
        recent_text = "; ".join([e.get("summary", "") for e in recent]) or "无记录"
        primary = dim.get("primary_phase", dim.get("current_stage", 0))
        primary_name = phases[primary] if 0 <= primary < len(phases) else "?"
        activity = dim.get("phase_activity", [])
        activity_str = "/".join(str(a) for a in activity) if activity else "—"
        recent_phases = dim.get("recent_phases", [])
        cycle = dim.get("current_cycle", 1)
        block = ach.get("per_dimension", {}).get(dim_id, {})
        insights = [i.get("title", "") for i in block.get("insights", [])]
        ins_str = ("已颁发洞察: " + "/".join(insights)) if insights else "无洞察"
        lines.append(
            f"- {dim_id} ({dim['label']}) [周期{cycle}]: "
            f"阶段路径=[{' / '.join(phases)}], "
            f"主阶段={primary+1}[{primary_name}], "
            f"分布={activity_str}, "
            f"近5条阶段={recent_phases}. "
            f"{ins_str}. "
            f"最近: {recent_text}"
        )
    return "\n".join(lines)


def _extract_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            return json.loads(m.group(0))
        raise


def call_deepseek(user_text, data):
    system = SYSTEM_PROMPT.replace(
        "{dimensions_summary}", _build_dimensions_summary(data)
    )
    client = get_client()
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_object"},
        max_tokens=2500,
    )
    raw = resp.choices[0].message.content or ""
    return _extract_json(raw)


def _ensure_unique_id(proposed, existing_ids):
    if proposed not in existing_ids:
        return proposed
    i = 2
    while f"{proposed}_{i}" in existing_ids:
        i += 1
    return f"{proposed}_{i}"


def _make_entry(result, phase_index, cycle):
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "summary": result.get("summary", ""),
        "key_progress": result.get("key_progress", []),
        "tag": result.get("tag", "信息"),
        "phase_index": int(phase_index),
        "stage_at_time": int(phase_index),
        "cycle": int(cycle),
        "cross_dimensions": result.get("cross_dimensions") or [],
    }


def apply_update(data, result):
    dim_id = result["dimension_id"]
    dim = data["dimensions"].get(dim_id)
    if not dim:
        return {"status": "error", "message": f"维度 {dim_id} 不存在"}

    n_phases = len(dim["phases"])
    phase_idx = int(result.get("phase_index", dim.get("primary_phase", 0)))
    phase_idx = max(0, min(phase_idx, n_phases - 1))

    cycle_event = result.get("cycle_event")
    if cycle_event and isinstance(cycle_event, dict) and cycle_event.get("type") == "new_cycle":
        reset = cycle_event.get("reset_primary_to", 0)
        data_store.start_new_cycle(dim, cycle_event.get("reason", ""), reset)
        phase_idx = max(0, min(int(cycle_event.get("reset_primary_to", phase_idx)), n_phases - 1))

    cur_cycle = dim.get("current_cycle", 1)
    entry = _make_entry(result, phase_idx, cur_cycle)
    dim.setdefault("entries", []).append(entry)

    return {
        "status": "ok",
        "action": "update",
        "dimension_id": dim_id,
        "dimension_label": dim["label"],
        "summary": result.get("summary", ""),
        "phase_index": phase_idx,
        "phase_name": dim["phases"][phase_idx]["name"],
        "progress_delta": result.get("progress_delta", ""),
        "next_steps": result.get("next_steps", []),
        "cross_dimensions": entry["cross_dimensions"],
        "cycle": cur_cycle,
        "cycle_event": cycle_event,
    }


def apply_create(data, result):
    proposed = result.get("dimension_id") or "new_dimension"
    proposed = re.sub(r"[^a-z0-9_]", "_", proposed.lower())
    dim_id = _ensure_unique_id(proposed, set(data["dimensions"].keys()))

    phases = result.get("phases", [])
    if not isinstance(phases, list) or len(phases) < 3:
        phases = [
            {"name": "起步", "desc": "初始阶段"},
            {"name": "推进", "desc": "中间阶段"},
            {"name": "完成", "desc": "收尾阶段"},
        ]
    phase_objs = []
    for p in phases:
        if isinstance(p, dict):
            phase_objs.append({"name": p.get("name", "?"), "desc": p.get("desc", "")})
        else:
            phase_objs.append({"name": str(p), "desc": ""})

    initial = result.get("initial_phase_index", result.get("initial_stage", 0))
    initial = max(0, min(int(initial), len(phase_objs) - 1))
    today = datetime.now().strftime("%Y-%m-%d")
    new_dim = {
        "label": result.get("dimension_label", dim_id),
        "created_at": today,
        "created_by": "auto",
        "phases": phase_objs,
        "current_stage": initial,
        "entries": [],
        "milestones": [],
        "phase_versions": [{
            "version": 1,
            "created_at": today,
            "phases": [p["name"] for p in phase_objs],
            "retired_at": None,
        }],
        "current_cycle": 1,
        "cycles": [{"number": 1, "started_at": today, "ended_at": None}],
    }
    new_dim["entries"].append(_make_entry(result, initial, 1))
    data["dimensions"][dim_id] = new_dim

    return {
        "status": "ok",
        "action": "create",
        "dimension_id": dim_id,
        "dimension_label": new_dim["label"],
        "reason": result.get("reason", ""),
        "phases": [p["name"] for p in phase_objs],
        "phase_index": initial,
        "phase_name": phase_objs[initial]["name"],
        "summary": result.get("summary", ""),
        "next_steps": result.get("next_steps", []),
    }


def apply_skip(result):
    return {
        "status": "ok",
        "action": "skip",
        "reason": result.get("reason", "无实质进展"),
    }


def stash_evolve(data, result, original_text):
    """演化方案先暂存，等用户确认 → confirm_evolution"""
    dim_id = result["dimension_id"]
    if dim_id not in data["dimensions"]:
        return {"status": "error", "message": f"维度 {dim_id} 不存在"}

    eid = hashlib.md5((dim_id + datetime.now().isoformat()).encode("utf-8")).hexdigest()[:12]
    pe = data.setdefault("meta", {}).setdefault("pending_evolutions", {})
    pe[eid] = {
        "dimension_id": dim_id,
        "ai_result": result,
        "original_text": original_text,
    }

    return {
        "status": "ok",
        "action": "evolve",
        "evolution_id": eid,
        "dimension_id": dim_id,
        "dimension_label": data["dimensions"][dim_id]["label"],
        "reason": result.get("reason", ""),
        "current_phases": result.get("current_phases") or [p["name"] for p in data["dimensions"][dim_id]["phases"]],
        "proposed_phases": result.get("proposed_phases", []),
        "entry_remapping": result.get("entry_remapping", []),
        "summary": result.get("summary", ""),
    }


def stash_confirm(data, result, original_text):
    cid = hashlib.md5((original_text + datetime.now().isoformat()).encode("utf-8")).hexdigest()[:12]
    data.setdefault("meta", {}).setdefault("pending_confirms", {})[cid] = {
        "original_text": original_text,
        "ai_result": result,
    }
    return {
        "status": "ok",
        "action": "confirm",
        "confirm_id": cid,
        "question": result.get("question", "请选择归类"),
        "options": result.get("options", []),
        "summary": result.get("summary", ""),
    }


def _maybe_grant_insight(dim_id, ai_result, progress_data):
    ach = ai_result.get("achievement")
    if not ach or not isinstance(ach, dict):
        return None
    title = (ach.get("title") or "").strip()
    desc = (ach.get("description") or "").strip()
    if not title or not desc:
        return None
    rarity = ach.get("rarity", "uncommon")
    if rarity not in ("common", "uncommon", "rare", "epic", "legendary"):
        rarity = "uncommon"
    try:
        return achievement_checker.add_insight(dim_id, title, desc, rarity, progress_data)
    except Exception:
        log.exception("写入洞察失败")
        return None


def process(text, data):
    if not text or not text.strip():
        return {"status": "error", "message": "空内容"}
    log.info("submit: text_len=%d, model=%s, base=%s", len(text), config.DEEPSEEK_MODEL, config.DEEPSEEK_BASE_URL)
    try:
        result = call_deepseek(text, data)
        log.info("ai action=%s", result.get("action"))
    except Exception as e:
        log.exception("AI 调用失败")
        return {"status": "error", "message": f"AI调用失败: {type(e).__name__}: {e}"}

    action = result.get("action")
    if action == "update":
        out = apply_update(data, result)
        if out.get("status") == "ok":
            ins = _maybe_grant_insight(out["dimension_id"], result, data)
            if ins:
                out["insight"] = ins
        return out
    if action == "create":
        out = apply_create(data, result)
        if out.get("status") == "ok":
            ins = _maybe_grant_insight(out["dimension_id"], result, data)
            if ins:
                out["insight"] = ins
        return out
    if action == "skip":
        return apply_skip(result)
    if action == "evolve":
        return stash_evolve(data, result, text)
    if action == "confirm":
        return stash_confirm(data, result, text)
    return {"status": "error", "message": f"未知 action: {action}", "raw": result}


def confirm_evolution(data, evolution_id, accepted):
    pe = data.get("meta", {}).get("pending_evolutions", {})
    item = pe.get(evolution_id)
    if not item:
        return {"status": "error", "message": "演化记录不存在或已过期"}

    dim_id = item["dimension_id"]
    dim = data["dimensions"].get(dim_id)
    if not dim:
        pe.pop(evolution_id, None)
        return {"status": "error", "message": "维度已不存在"}

    ai = item["ai_result"]
    pe.pop(evolution_id, None)

    if not accepted:
        # 拒绝演化：直接当 update 落地（用 phase_index_after_evolve 或 primary_phase）
        idx = ai.get("phase_index_after_evolve", dim.get("primary_phase", 0))
        update_payload = {
            "dimension_id": dim_id,
            "summary": ai.get("summary", ""),
            "key_progress": ai.get("key_progress", []),
            "tag": ai.get("tag", "信息"),
            "phase_index": idx,
            "progress_delta": "（已拒绝阶段演化）",
            "next_steps": [],
            "cross_dimensions": [],
        }
        return apply_update(data, update_payload)

    new_phases = ai.get("proposed_phases", [])
    remapping = ai.get("entry_remapping", [])
    data_store.evolve_phases(dim, new_phases, remapping)

    new_idx = ai.get("phase_index_after_evolve", 0)
    new_idx = max(0, min(int(new_idx), len(dim["phases"]) - 1))
    cur_cycle = dim.get("current_cycle", 1)
    entry = _make_entry({
        "summary": ai.get("summary", ""),
        "key_progress": ai.get("key_progress", []),
        "tag": ai.get("tag", "里程碑"),
        "cross_dimensions": [],
    }, new_idx, cur_cycle)
    dim.setdefault("entries", []).append(entry)
    dim.setdefault("milestones", []).append({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "event": f"阶段演化：v{len(dim['phase_versions'])}",
    })

    return {
        "status": "ok",
        "action": "evolved",
        "dimension_id": dim_id,
        "dimension_label": dim["label"],
        "new_phases": [p["name"] for p in dim["phases"]],
        "phase_index": new_idx,
        "phase_name": dim["phases"][new_idx]["name"],
        "version": len(dim["phase_versions"]),
    }


def resolve_confirm(data, confirm_id, chosen_dimension_id):
    pending = data.get("meta", {}).get("pending_confirms", {})
    item = pending.get(confirm_id)
    if not item:
        return {"status": "error", "message": "确认记录不存在或已过期"}

    ai_result = item["ai_result"]
    original_text = item["original_text"]
    options = ai_result.get("options", [])
    chosen = next((o for o in options if o.get("dimension_id") == chosen_dimension_id), None)
    pending.pop(confirm_id, None)

    if chosen_dimension_id in data["dimensions"]:
        dim = data["dimensions"][chosen_dimension_id]
        return apply_update(data, {
            "dimension_id": chosen_dimension_id,
            "summary": ai_result.get("summary", original_text[:80]),
            "key_progress": ai_result.get("key_progress", []),
            "tag": ai_result.get("tag", "信息"),
            "phase_index": dim.get("primary_phase", 0),
            "progress_delta": "（用户确认归类）",
            "next_steps": [],
            "cross_dimensions": [],
        })

    try:
        result2 = call_deepseek(
            f"请为以下内容创建新维度，命名建议：{(chosen or {}).get('label', chosen_dimension_id)}\n\n内容：\n{original_text}",
            data,
        )
        if result2.get("action") == "create":
            return apply_create(data, result2)
        result2["dimension_id"] = chosen_dimension_id
        result2.setdefault("dimension_label", (chosen or {}).get("label", chosen_dimension_id))
        result2.setdefault("phases", [])
        return apply_create(data, result2)
    except Exception as e:
        return {"status": "error", "message": f"二次AI调用失败: {e}"}
