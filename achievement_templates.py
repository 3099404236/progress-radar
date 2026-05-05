# -*- coding: utf-8 -*-
"""成就模板：每个维度的 13 个 milestone + 全局 milestone"""

DIM_MILESTONE_TEMPLATES = [
    {"id": "dim_first",     "title": "起步",       "description": "在该维度提交第一条记录",          "rarity": "common"},
    {"id": "dim_10",        "title": "站稳脚跟",   "description": "该维度累计 10 条记录",            "rarity": "common"},
    {"id": "dim_deep",      "title": "深耕",       "description": "该维度累计 20 条记录",            "rarity": "uncommon"},
    {"id": "dim_50",        "title": "专家之路",   "description": "该维度累计 50 条记录",            "rarity": "rare"},
    {"id": "dim_hatch",     "title": "破壳",       "description": "离开初始阶段",                    "rarity": "common"},
    {"id": "dim_mid",       "title": "半程",       "description": "到达中间阶段",                    "rarity": "uncommon"},
    {"id": "dim_finale",    "title": "收官",       "description": "到达最终阶段",                    "rarity": "rare"},
    {"id": "dim_cycle2",    "title": "二周目",     "description": "进入第二轮周期",                  "rarity": "uncommon"},
    {"id": "dim_streak3",   "title": "三连",       "description": "连续 3 天在该维度有记录",        "rarity": "common"},
    {"id": "dim_streak7",   "title": "周连",       "description": "连续 7 天在该维度有记录",        "rarity": "uncommon"},
    {"id": "dim_active30",  "title": "长期关注",   "description": "首条到最近一条跨度 ≥ 30 天",     "rarity": "uncommon"},
    {"id": "dim_active90",  "title": "老朋友",     "description": "持续活跃 ≥ 90 天",                "rarity": "rare"},
    {"id": "dim_reshape",   "title": "重塑",       "description": "阶段模型经历过一次演化",          "rarity": "rare"},
]

GLOBAL_MILESTONE_TEMPLATES = [
    {"id": "g_three_dims",   "title": "三维并进", "description": "一周内 ≥ 3 个维度有记录",       "rarity": "uncommon"},
    {"id": "g_new_continent","title": "新大陆",   "description": "累计创建 ≥ 5 个维度",            "rarity": "uncommon"},
    {"id": "g_crossover",    "title": "跨界选手", "description": "出现 cross_dimensions 记录",     "rarity": "rare"},
    {"id": "g_streak30",     "title": "月度坚持", "description": "连续 30 天有任意维度的提交",     "rarity": "rare"},
    {"id": "g_first_evolve", "title": "破而后立", "description": "首次接受阶段演化建议",            "rarity": "rare"},
    {"id": "g_total_50",     "title": "百记之始", "description": "累计 50 条记录",                  "rarity": "common"},
    {"id": "g_total_200",    "title": "记录大师", "description": "累计 200 条记录",                 "rarity": "rare"},
]


RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4}


def make_dim_slot(template):
    return {
        "id": template["id"],
        "title": template["title"],
        "description": template["description"],
        "rarity": template["rarity"],
        "unlocked_at": None,
    }


def make_global_slot(template):
    return make_dim_slot(template)
