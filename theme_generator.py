# -*- coding: utf-8 -*-
"""为维度生成 themed milestone：用 DeepSeek 按该维度的主题给 13 个 milestone 量身起诗化中文名"""
import json
import logging
import re
from openai import OpenAI

import config
import ai_processor
from achievement_templates import DIM_MILESTONE_TEMPLATES

log = logging.getLogger("progressradar.theme")


SYSTEM = """你是个写诗的人。给定一个追踪维度（标签 + 阶段路径 + 简介），为它的 13 个里程碑成就量身写"四字中文诗化"标题。

要求：
1. 完全围绕该维度的具体主题来想，不要套通用模板。比如"早起习惯"维度的"第一次"可以叫「闻鸡」「曦光」「晨拓」；"体测"维度可以叫「破汗」「试锋」；"保研夏令营"可以叫「窥门」「探径」。
2. **每个 title 必须 4 个字**，意境优先，让人一看就觉得有戏。可以借古文、典故、自然意象、武侠仙侠风。
3. description 一句话（最多 18 字），文学化口吻（"踏上 XX 之径""推开 XX 之门"），不要平铺直叙。
4. 13 个 milestone 的语义大类是固定的：第一条记录 / 累计 10 / 累计 20 / 累计 50 / 离开初始阶段 / 到达中间阶段 / 到达最终阶段 / 进入第 2 周期 / 连续 3 天 / 连续 7 天 / 跨度 30 天 / 跨度 90 天 / 阶段演化。所以同一维度内 13 个 title 要互相区分，不重复，并形成由浅入深的递进感。
5. 输出严格 JSON：{"items":[{"id":"dim_first","title":"...","description":"..."}, ...]}，13 项必须齐全。
6. 不要输出 JSON 以外的内容。"""


SLOT_HINTS = {
    "dim_first":     "首次提交一条记录（第一次）",
    "dim_10":        "累计 10 条记录（小成）",
    "dim_deep":      "累计 20 条记录（深耕）",
    "dim_50":        "累计 50 条记录（专精）",
    "dim_hatch":     "离开初始阶段（迈出门槛）",
    "dim_mid":       "到达中间阶段（过半）",
    "dim_finale":    "到达最终阶段（临近终点）",
    "dim_cycle2":    "进入第 2 周期（再启）",
    "dim_streak3":   "连续 3 天有记录（短连续）",
    "dim_streak7":   "连续 7 天有记录（一周不辍）",
    "dim_active30":  "首条到最近一条跨度 ≥ 30 天（一月陪伴）",
    "dim_active90":  "持续活跃 ≥ 90 天（三月恒心）",
    "dim_reshape":   "阶段模型经历过一次演化（重塑）",
}


def _build_user_prompt(dim_label, phases, descs):
    phase_part = "\n".join(
        f"  阶段{i+1}: {p}（{d or '—'}）"
        for i, (p, d) in enumerate(zip(phases, descs or [""] * len(phases)))
    )
    slot_part = "\n".join(f"  - {sid}: {hint}" for sid, hint in SLOT_HINTS.items())
    return f"""维度标签：{dim_label}

阶段路径：
{phase_part}

要为以下 13 个 milestone 量身命名（语义和递进顺序固定，title 4 字，description 句意要紧扣这个维度的领域特色）：
{slot_part}

输出 JSON。"""


def _extract_json(text):
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 容错：截到最后一个完整的 } 或最后一个完整 item
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 最后兜底：手动从行内 regex 提取所有完整的 {"id":"...","title":"...","description":"..."}
    items = []
    for mm in re.finditer(r'\{\s*"id"\s*:\s*"([^"]+)"\s*,\s*"title"\s*:\s*"([^"]+)"\s*,\s*"description"\s*:\s*"([^"]+)"\s*\}', text):
        items.append({"id": mm.group(1), "title": mm.group(2), "description": mm.group(3)})
    if items:
        return {"items": items}
    raise json.JSONDecodeError("无法解析", text, 0)


def generate_for_dimension(dim_label, phases, descs=None):
    """返回 {id: {title, description}} 字典；失败时返回 {}（调用方回退到默认）"""
    client = ai_processor.get_client()
    user_prompt = _build_user_prompt(dim_label, phases, descs or [])
    try:
        resp = client.chat.completions.create(
            model=config.DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content or ""
        data = _extract_json(raw)
    except Exception:
        log.exception("生成 themed milestone 失败")
        return {}

    out = {}
    valid_ids = set(SLOT_HINTS.keys())
    for it in data.get("items", []):
        if not isinstance(it, dict):
            continue
        sid = it.get("id")
        title = (it.get("title") or "").strip()
        desc = (it.get("description") or "").strip()
        if sid in valid_ids and title and desc:
            out[sid] = {"title": title, "description": desc}
    return out
