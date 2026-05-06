# -*- coding: utf-8 -*-
"""成就模板：每个维度的 13 个 milestone + 全局 milestone

命名走"四字诗化"路线，描述带情绪，稀有度按难度合理分布，
让用户解锁时有"我真的做成一件事"的实感。
"""

# 维度通用 milestone（每维度独立计算）
DIM_MILESTONE_TEMPLATES = [
    # 记录数
    {"id": "dim_first",     "title": "初燃",         "description": "迈出第一步，旅程从此点燃",                     "rarity": "common",
     "visual_concept": "a single footprint glowing on fresh snow at dawn, soft golden light"},
    {"id": "dim_10",        "title": "积流成川",     "description": "十次记录汇成一条小河，方向已现",               "rarity": "uncommon",
     "visual_concept": "ten small stones stacked into a balanced cairn on a hilltop, river below"},
    {"id": "dim_deep",      "title": "百炼之初",     "description": "二十次淬炼，初见钢色",                          "rarity": "rare",
     "visual_concept": "a deep mine shaft with veins of glowing gems in stone walls, lantern light"},
    {"id": "dim_50",        "title": "炉火纯青",     "description": "五十次专注，已入化境",                          "rarity": "epic",
     "visual_concept": "master blacksmith forging glowing sword in dark forge, sparks flying"},

    # 阶段进展
    {"id": "dim_hatch",     "title": "破茧",         "description": "推开初阶之门，新天地展开",                     "rarity": "common",
     "visual_concept": "an egg cracking open with golden light pouring out, butterfly emerging"},
    {"id": "dim_mid",       "title": "过半山",       "description": "走过中道，山顶已在视野",                       "rarity": "uncommon",
     "visual_concept": "lone climber resting at mountain halfway point, summit visible above clouds"},
    {"id": "dim_finale",    "title": "问鼎",         "description": "踏上最后一阶，将与终点相会",                   "rarity": "epic",
     "visual_concept": "flag planted on snowy mountain peak, sunrise behind, dramatic sky"},

    # 周期
    {"id": "dim_cycle2",    "title": "凤凰涅槃",     "description": "一周收官，再启新轮",                            "rarity": "rare",
     "visual_concept": "phoenix rising from ashes with vibrant orange and red flames, reborn"},

    # 连续 / 跨度
    {"id": "dim_streak3",   "title": "三日不熄",     "description": "连续三日，火种未灭",                            "rarity": "common",
     "visual_concept": "three candle flames in a row burning steadily in deep darkness"},
    {"id": "dim_streak7",   "title": "七日精进",     "description": "整周不辍，节律已成",                            "rarity": "uncommon",
     "visual_concept": "seven ascending stone steps glowing softly, single path through forest"},
    {"id": "dim_active30",  "title": "月之轮回",     "description": "陪伴这件事走过完整的一个月",                   "rarity": "uncommon",
     "visual_concept": "young sapling growing into small tree under full moon, growth rings visible"},
    {"id": "dim_active90",  "title": "四时同行",     "description": "三个月的恒心，季节在变，你没变",               "rarity": "epic",
     "visual_concept": "ancient oak tree with deep roots, four seasons swirling around its canopy"},

    # 阶段演化
    {"id": "dim_reshape",   "title": "破而后立",     "description": "推翻旧的阶段框架，长出新的形状",               "rarity": "epic",
     "visual_concept": "clay pot reshaping on potter wheel, new elegant form emerging from old"},
]

# 全局 milestone（跨维度）
GLOBAL_MILESTONE_TEMPLATES = [
    {"id": "g_three_dims",   "title": "三星拱月",   "description": "一周内三个方向同时推进，气象已开",               "rarity": "rare",
     "visual_concept": "three different colored rivers merging into one powerful stream under starry sky"},
    {"id": "g_new_continent","title": "开疆扩土",   "description": "建立第五个维度，版图渐成",                       "rarity": "uncommon",
     "visual_concept": "ancient ship arriving at undiscovered island, lush vegetation, dawn light"},
    {"id": "g_crossover",    "title": "跨界破壁",   "description": "两个维度产生连接，你的世界开始相通",             "rarity": "epic",
     "visual_concept": "two glowing portals connecting through stone wall, light bridge between them"},
    {"id": "g_streak30",     "title": "日省其身",   "description": "连续三十天不间断，自律已成习",                   "rarity": "legendary",
     "visual_concept": "long bridge of stepping stones across misty lake, each stone glowing golden"},
    {"id": "g_first_evolve", "title": "破而后立",   "description": "首次接受阶段重构，敢于推翻自己",                 "rarity": "epic",
     "visual_concept": "old wooden bridge collapsing while new crystal bridge rises in same place"},
    {"id": "g_total_50",     "title": "五十里程",   "description": "五十条记录，已是认真追踪者",                     "rarity": "uncommon",
     "visual_concept": "ancient stone milestone marker on weathered path, fifty carved upon it"},
    {"id": "g_total_200",    "title": "二百盈尺",   "description": "积累两百条，回望已是长卷",                       "rarity": "legendary",
     "visual_concept": "endless library scroll unrolling into the distance, golden calligraphy strokes"},
]


# 中文稀有度标签
RARITY_LABEL = {
    "common":    "寻常",
    "uncommon":  "不凡",
    "rare":      "稀有",
    "epic":      "史诗",
    "legendary": "传奇",
}

RARITY_ORDER = {"common": 0, "uncommon": 1, "rare": 2, "epic": 3, "legendary": 4}


def make_dim_slot(template):
    return {
        "id": template["id"],
        "title": template["title"],
        "description": template["description"],
        "rarity": template["rarity"],
        "visual_concept": template.get("visual_concept", ""),
        "unlocked_at": None,
        "image_status": "missing",  # missing / inflight / ready
    }


def make_global_slot(template):
    return make_dim_slot(template)
