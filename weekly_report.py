# -*- coding: utf-8 -*-
"""周报生成：汇总本周entries→DeepSeek 生成中文周报"""
import os
import json
from datetime import datetime, timedelta
from openai import OpenAI

import httpx

import config
import data_store as storage  # v2 起 storage 模块改名为 data_store


def collect_week_entries(data, days=7):
    cutoff = datetime.now() - timedelta(days=days)
    by_dim = {}
    for dim_id, dim in data["dimensions"].items():
        recent = []
        for e in dim.get("entries", []):
            try:
                ts = datetime.fromisoformat(e["timestamp"])
            except Exception:
                continue
            if ts >= cutoff:
                recent.append(e)
        by_dim[dim_id] = {
            "label": dim["label"],
            "current_stage": dim["current_stage"],
            "phases": [p["name"] for p in dim["phases"]],
            "entries": recent,
        }
    return by_dim


def build_prompt(by_dim):
    lines = []
    for dim_id, info in by_dim.items():
        cur = info["phases"][info["current_stage"]] if info["phases"] else "?"
        lines.append(f"\n## {info['label']} （当前阶段：{cur}）")
        if not info["entries"]:
            lines.append("- 本周无记录")
            continue
        for e in info["entries"]:
            ts = e.get("timestamp", "")[:10]
            lines.append(f"- [{ts}] {e.get('summary', '')} (tag: {e.get('tag', '')})")
    return "\n".join(lines)


SYSTEM = """你是一位个人项目教练。给定用户本周在各个维度上的进展记录，生成一份简洁、有洞察力的中文周报。

要求：
1. 标题：本周回顾（YYYY-MM-DD ~ YYYY-MM-DD）
2. 各维度本周做了什么（如果某维度本周无记录，要诚实指出"未推进"）
3. 哪些维度被忽略了（连续多天没动静）
4. 整体观察与建议（控制在3条以内）
5. 风格：克制、直接，不加感叹号、不喊加油
6. Markdown 格式输出
"""


def generate(data):
    by_dim = collect_week_entries(data)
    prompt = build_prompt(by_dim)
    client = OpenAI(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        http_client=httpx.Client(trust_env=False, timeout=60.0),
    )
    today = datetime.now().strftime("%Y-%m-%d")
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    user = f"日期范围：{week_ago} 到 {today}\n\n本周各维度进展：\n{prompt}\n\n请输出周报。"
    resp = client.chat.completions.create(
        model=config.DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=2000,
    )
    return resp.choices[0].message.content


def main():
    data = storage.load()
    report = generate(data)
    os.makedirs(config.WEEKLY_DIR, exist_ok=True)
    fname = datetime.now().strftime("%Y-%m-%d") + "_weekly.md"
    path = os.path.join(config.WEEKLY_DIR, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"周报已生成：{path}")
    print("---")
    print(report)


if __name__ == "__main__":
    main()
