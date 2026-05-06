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


SYSTEM = """你是个写诗的人 + 视觉概念设计师。给定一个追踪维度（标签 + 阶段路径），为它的 13 个里程碑成就量身：
(a) 写"四字中文诗化"标题
(b) 写一句中文文学化描述
(c) 写一段英文 visual_concept — 用于驱动文生图模型生成"该成就的卡牌插画"

要求：

A. 标题 (title)：
- 完全围绕该维度的具体主题，不要套通用模板。"早起"可以叫「闻鸡」「曦光」「晨拓」；"体测"叫「破汗」「试锋」；"保研夏令营"叫「窥门」「探径」
- 必须 4 个字，意境优先，可借古文/典故/自然/武侠仙侠风
- 13 个 title 互相区分，由浅入深递进

B. 描述 (description)：
- 一句话（最多 18 字），文学化口吻
- 例："踏上 XX 之径"、"推开 XX 之门"，不要平铺直叙

C. **视觉概念 (visual_concept)** ⭐ — 这是关键：
- **必须用英文写**（图模型只懂英文）
- 描述一个能代表该成就含义的具体画面：物体 + 场景 + 光影
- 不要含字 / 字母 / 数字 / 文字 / 标志 / logo
- 30 词以内
- 围绕维度主题来想：
  · 早起习惯 dim_first → "first ray of sunlight breaking over rooftops at dawn, single bird in flight"
  · 体测 dim_streak7 → "seven barbells aligned in row, stadium lights glowing on each"
  · 保研夏令营 dim_finale → "single figure standing before grand academy gates, scroll in hand"
  · Conformal Prediction dim_reshape → "geometric crystal lattice reforming into new shape, mathematical elegance"
- 不要套用千篇一律的视觉，要紧贴维度具体内容

13 个 milestone 的语义大类（id 固定）：
- dim_first: 首条记录
- dim_10/20/50: 累计 10/20/50 条
- dim_hatch: 离开初始阶段
- dim_mid: 到达中间阶段
- dim_finale: 到达最终阶段
- dim_cycle2: 进入第 2 周期
- dim_streak3/7: 连续 3/7 天
- dim_active30/90: 跨度 30/90 天
- dim_reshape: 阶段演化

输出严格 JSON：
{"items":[{"id":"dim_first","title":"…","description":"…","visual_concept":"…"}, …]}
13 项齐全。不要输出 JSON 以外的内容。"""


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
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    # 兜底：宽松正则从碎片里抓 id / title / description / visual_concept
    items = []
    pat = re.compile(
        r'\{\s*"id"\s*:\s*"(?P<id>[^"]+)"\s*,\s*'
        r'"title"\s*:\s*"(?P<title>[^"]+)"\s*,\s*'
        r'"description"\s*:\s*"(?P<desc>[^"]+)"'
        r'(?:\s*,\s*"visual_concept"\s*:\s*"(?P<vc>[^"]+)")?'
        r'\s*\}'
    )
    for mm in pat.finditer(text):
        d = mm.groupdict()
        item = {"id": d["id"], "title": d["title"], "description": d["desc"]}
        if d.get("vc"):
            item["visual_concept"] = d["vc"]
        items.append(item)
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
            max_tokens=4000,
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
        vc = (it.get("visual_concept") or "").strip()
        if sid in valid_ids and title and desc:
            entry = {"title": title, "description": desc}
            if vc:
                entry["visual_concept"] = vc
            out[sid] = entry
    return out
