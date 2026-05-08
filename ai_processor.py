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

### 第四步：阶段演化检测 ⭐（要严格，宁可不触发也别误伤）
检查以下条件，任一满足则不返回 update，而返回 action="evolve"：
1. 本次内容确实属于这个维度，但不属于当前任何阶段的描述范围
2. 维度的 recent_phases 显示在3个以上阶段间频繁跳跃，且当前阶段划分难以描述
3. 用户明确说"重新组织阶段""阶段不合适"等
4. **用户主动声明整个维度终止**（仅在以下三种之一才算）：
   - "外部强制结束"：被淘汰、止步前 N 强、止步复赛、没进下一阶段（用户已经被外部判出局了）
   - "彻底退出"：这事不做了 / 退出比赛 / 这维度结束 / 这个方向我不做了
   - "进度截止"：到这就完了 / 收尾 / 后续阶段没机会再走

⚠️ **以下情况绝对不要触发 evolve，应当判 update + cycle_event**：
- "我们另找路子 / 换思路 / 换方法 / 换方向"（用户还在维度里，只是换打法）
- "原方案不行，重新评估" / "v1 没成功，搞 v2"
- "这条路放弃了，再试试别的"（"再试试"= 还在维度里继续）
- 单独的"放弃"如果后面跟着"另找/换/重做/再试"等延续动作 → 是换路线，不是退出

判断口诀：用户**还要在这个维度里继续做**吗？
- 还要 → update + cycle_event（开新一轮）
- 不再做了 → evolve

evolve 时给出 proposed_phases (3-6个) 和 entry_remapping。phase_index_after_evolve 等于新 proposed_phases 最后一项。

### 第五步：周期检测 ⭐
如果出现以下信号，在 update 中附上 cycle_event：
1. 用户在该维度的最终阶段之后又回到了早期阶段性质的工作（如论文投稿后开始改稿、考试结束后开下学期课）
2. 明确出现"重新开始""新一轮""被拒重投"等信号
3. **用户在维度内换路子/换方法/换方向（v1 方法搁置，开 v2）** ⭐
   触发语："另找路子" / "换思路" / "重新设计" / "换方法" / "v2 / 再试一版" / "原方案不行重做"
   处理：
   - reset_primary_to 应当指向该维度阶段路径中**靠前的"规划/设计/调研"类阶段**（而不是起始阶段）
     · 比如 [信息收集/方案设计/版本迭代/最终提交/等待结果]，应当回到 idx=1（方案设计）
     · 比如 [文献调研/理论框架/实验验证/论文写作/投稿修改]，应当回到 idx=1 或 2（理论框架/实验验证）
   - summary 用"v{{N}} 方案搁置，重新设计/启动新一轮"这种**积极语气**，**不要写"放弃"**
   - reason 写明"换路线/重启而非退出"

cycle_event = {{"type":"new_cycle","reason":"...","new_cycle_number":N,"reset_primary_to":phase_index}}

### 第六步：进展提取
- 提取具体的、可衡量的"做了什么/完成了什么/发现了什么"
- 包括行为类记录：早起、运动、阅读、冥想、戒糖、写日记 — 这些都算具体行为
- 也包括**声明类信号**（这是最容易被错判的一类！）：用户主动提及一个事件、机会、目标、方向，无论语气是确定还是猜测、是已发生还是即将发生 — 都意味着用户在让你帮他建立追踪。**关键不是语气是否确定，而是用户提到了一个值得追踪的对象**。
  覆盖的语气模式：
    "XX 要来了 / 体测要到了"
    "决定参加 XX / 打算考 XX / 想报 XX"
    "下学期要 XX / 下个月要 XX"
    "估计 XX 可能要开始 / 听说 XX 快了 / 应该差不多要 XX 了"  ← 模糊推测也算
    "XX 报名了 / 听到 XX 通知"
  处理方式：在已有维度中找最匹配的，没有则 **create 新维度**，落到"起步/信息收集/了解标准"阶段（initial_phase_index=0），summary 写"识别到新方向：XX"，next_steps 给 1-3 个用户可立刻做的动作（查信息、确认时间、列要求等）
- 不要提取的：纯情绪宣泄、对天气/食物的随感、与任何行为或方向无关的吐槽
- 给一个 tag：实验/代码/写作/理论/信息/行动/里程碑/发现/调试/部署/习惯/起步

⚠️ skip 判定要严格（绝大多数情况都不应该 skip）：
- 仅当内容**既无行为也无方向声明**时才 skip
- ⭐⭐ **重要原则：用户主动提交即视为想追踪。不要二次猜测"这件事重不重要/日常不日常"** —
  喝水、吃饭、睡觉、刷牙、记账、走路、坐姿矫正…都是合法维度。**只要用户在系统里写下，就说明他想追踪**。
  你不是裁判，不要否决用户。"日常琐事"不是 skip 理由 — 用户记录自己每天的常规行为正是这个系统的核心用途之一。
- 应当归类（不可 skip）的例子：
  - 行为："今天早起了" / "做了一组俯卧撑" / "读了 3 章书" / "**点了个晚饭**" / "**喝了一杯水**" / "**今天没刷牙**"（习惯类，建饮食/喝水/口腔等维度的起步阶段）
  - 方向声明："体测要到了" / "决定参加 XX 竞赛" / "下学期要研究 ZZ"
  - 模糊推测："估计保研夏令营快开始报名了" / "听说 XX 比赛要开了"
  - 计划+具体目标："打算下个月之前完成 XX"
- 真正应当 skip 的例子（纯感受、无行为无方向）：
  - "今天天气真好" / "心情不太好" / "食堂菜难吃" / "好困" / "周一好烦"
  - 但 "今天没怎么睡好" → 已涉及睡眠行为 → 归到睡眠/作息维度，不能 skip

### 第七步：下一步建议
- 1-3个具体可执行的下一步

### 第七A步：多任务分发 ⭐⭐
若一条提交包含**多个独立动作 / 涉及多个不同维度**，返回 action="multi"，把每件事拆成一个独立的 sub_action。

判断口诀：
- "做了 A 又做了 B" / "A，然后 B" / "A、B、C" 这种**并列动作** → 拆
- "今天 A 跟 B 都搞了" → 拆
- "做了 A，B 进展是 C" 当 A 和 B 是不同方向 → 拆
- 多个细节描述**同一件事** → 不拆（如"今天 conformal 跑了多资产 VaR 实验，结果优于椭球投影" 是一件事的细节）

显式例：
- "烧了水吃了早餐" → multi: [update water_intake / 烧水, update breakfast / 早餐]
- "今天看了 3 章书 + 做了俯卧撑" → multi: [update reading, update fitness]
- "完成了 conformal 实验、改了波动率论文" → multi: [update conformal_prediction, update volatility_paper]
- "v1 模型跑通了实验" → 单条 update（一件事的两个细节）

输出格式：
{{"action":"multi","sub_actions":[<完整 update 或 create JSON>, <...>]}}
每个 sub_action 必须包含完整字段（dimension_id/summary/phase_index/...）。
所有支持的字段（cycle_event、achievement、timeline_events 等）依然各自独立。

### 第七B步：时间轴事件提取 ⭐（仅当内容含具体日期或可推算的相对日期）
- 仅当用户提到"X月X日 / MM-DD / 某月某号 / 周X / N天后"这种**带具体日期**的事件预告/截止时提取
- 输出 `timeline_events` 数组（没有就给 `[]`）
- 字段：`{"date":"YYYY-MM-DD","label":"≤12字事件名","note":"可选附加信息"}`
- 相对日期需基于今天换算成 ISO 格式（今天日期会作为系统时间隐含传入；如果没把握就跳过）
- 示例：
  - "操作系统期末 6 月 15 日 B404 教室" → `[{"date":"2026-06-15","label":"操作系统期末","note":"B404 教室"}]`
  - "牙医约的周五（5月8号）下午 3 点" → `[{"date":"2026-05-08","label":"看牙医","note":"下午 3 点"}]`
  - "下学期开学要好好准备" → `[]`（无具体日期）
  - "今天早起了" → `[]`（是行为不是预告）
- 可一次提取多条事件（如"6月8 高数、6月10 计组"）

### 第八步：维度专属洞察成就（高度可选，绝大多数 update 应为 null）⭐
- 每个维度有自己的"洞察"成就池。如果本次提交在所属维度内代表一个真正的转折点（不是普通进展），才颁发
- 类型参考：方法突破 / 质量跃迁 / 关键发现 / 瓶颈突破 / 意外连接 / 边界拓展
- **title: 4 个字诗化中文短语**，画面感优先：「破茧」「燎原」「开光」「凿空」「化境」「破壁」「炼骨」「拨云」
- description: 一句话文学化口吻（"踏上 XX 之径"），不要平铺直叙
- rarity: common / uncommon / rare / epic
- **visual_concept**（英文）⭐：一段 30 词内的英文，描述能代表该洞察的画面（具体物体 + 场景 + 光影），将用于驱动文生图 API 生成卡面
  - 不要含字 / 字母 / 数字 / 文字
  - 围绕该维度的主题：CP 研究 → "geometric crystal lattice expanding"，吉他练习 → "fingers dancing on glowing fretboard"
- 已颁发过的洞察会列在维度摘要里，**绝对不要换汤不换药地重复**
- create 维度时也可以附 achievement

## 输出格式
严格 JSON，以下场景之一：

A0. 多动作分发 → multi（一条提交包含多个独立动作）：
{{"action":"multi","sub_actions":[<完整 update 或 create JSON>,<...>]}}

A. 匹配已有维度 → update：
{{"action":"update","dimension_id":"...","summary":"...","key_progress":["..."],"tag":"...","phase_index":N,"progress_delta":"...","next_steps":["..."],"cross_dimensions":[],"cycle_event":null,"achievement":null,"timeline_events":[]}}
（如颁发: "achievement":{{"title":"四字","description":"一句话","rarity":"...","visual_concept":"english scene 30 words"}}）

B. 创建新维度 → create：
{{"action":"create","dimension_id":"snake_case","dimension_label":"中文标签","reason":"为什么不属于已有维度","phases":[{{"name":"...","desc":"..."}}],"initial_phase_index":0,"summary":"...","key_progress":["..."],"tag":"...","next_steps":["..."],"achievement":null,"timeline_events":[]}}

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
    today_hint = f"\n\n（系统当前日期：{datetime.now().strftime('%Y-%m-%d')}，如需将相对日期转 ISO 请基于此）"
    client = get_client()
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": system + today_hint},
            {"role": "user", "content": user_text},
        ],
        response_format={"type": "json_object"},
        max_tokens=2500,
    )
    raw = resp.choices[0].message.content or ""
    return _extract_json(raw)


def _merge_timeline_events(dim, events):
    """把 AI 提取的事件 append 到 dim.timeline，按 date+label 去重，按 date 升序排"""
    if not events or not isinstance(events, list):
        return []
    import hashlib
    timeline = dim.setdefault("timeline", [])
    existing_ids = {e.get("id") for e in timeline if e.get("id")}
    added = []
    for ev in events:
        if not isinstance(ev, dict):
            continue
        date = (ev.get("date") or "").strip()
        label = (ev.get("label") or "").strip()
        note = (ev.get("note") or "").strip()
        if not date or not label:
            continue
        # 简单 ISO 校验
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
            continue
        eid = hashlib.md5((date + "|" + label).encode("utf-8")).hexdigest()[:10]
        if eid in existing_ids:
            continue
        item = {
            "id": eid,
            "date": date,
            "label": label[:24],
            "note": note[:80],
            "added_at": datetime.now().isoformat(timespec="seconds"),
        }
        timeline.append(item)
        existing_ids.add(eid)
        added.append(item)
    timeline.sort(key=lambda x: x.get("date", ""))
    return added


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

    # 异步先不做，直接同步生成 themed milestone（一次额外 API 调用）
    try:
        import theme_generator
        overrides = theme_generator.generate_for_dimension(
            new_dim["label"],
            [p["name"] for p in phase_objs],
            [p.get("desc", "") for p in phase_objs],
        )
        if overrides:
            import achievement_store
            achievement_store.apply_themed_milestones(dim_id, overrides, data)
            log.info("themed milestones 已生成 dim=%s n=%d", dim_id, len(overrides))
    except Exception:
        log.exception("themed milestones 生成失败（不影响主流程）")

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
    vc = (ach.get("visual_concept") or "").strip()
    if not title or not desc:
        return None
    rarity = ach.get("rarity", "uncommon")
    if rarity not in ("common", "uncommon", "rare", "epic", "legendary"):
        rarity = "uncommon"
    try:
        return achievement_checker.add_insight(dim_id, title, desc, rarity, vc, progress_data)
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

    return _dispatch(result, data, text)


def _apply_one(sub, data):
    """一个 sub_action（update 或 create）的完整 apply：含 insight + timeline_events"""
    a = sub.get("action")
    if a == "update":
        out = apply_update(data, sub)
    elif a == "create":
        out = apply_create(data, sub)
    else:
        return {"status": "error", "message": f"sub_action 不支持 {a}", "raw": sub}
    if out.get("status") == "ok":
        ins = _maybe_grant_insight(out["dimension_id"], sub, data)
        if ins:
            out["insight"] = ins
        dim = data["dimensions"].get(out["dimension_id"])
        if dim:
            added = _merge_timeline_events(dim, sub.get("timeline_events"))
            if added:
                out["timeline_added"] = added
    return out


def _dispatch(result, data, text):
    action = result.get("action")
    if action in ("update", "create"):
        return _apply_one(result, data)
    if action == "skip":
        return apply_skip(result)
    if action == "evolve":
        return stash_evolve(data, result, text)
    if action == "confirm":
        return stash_confirm(data, result, text)
    if action == "multi":
        subs = result.get("sub_actions") or []
        if not subs:
            return {"status": "error", "message": "multi 但 sub_actions 为空", "raw": result}
        results = []
        for sub in subs:
            r = _apply_one(sub, data)
            results.append(r)
        ok_count = sum(1 for r in results if r.get("status") == "ok")
        return {
            "status": "ok",
            "action": "multi",
            "count": len(results),
            "ok_count": ok_count,
            "results": results,
        }
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
