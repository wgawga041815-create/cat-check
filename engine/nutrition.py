# -*- coding: utf-8 -*-
"""猫粮方案引擎。

输出的是“营养规格 + 选购标准 + 喂养方案”，不是品牌带货。
所有数值都以干物质（DM）为基准，方便直接对照配料表/保证分析值。
"""

KCAL_DRY = 3.8      # 干粮 kcal/g（常见区间 3.5–4.2）
KCAL_WET = 1.0      # 主食湿粮 kcal/g（约 78% 水分）
CAN_G = 85          # 常见主食罐规格

CONDITIONS = [
    {"id": "ckd", "zh": "慢性肾病", "hint": "肌酐/SDMA 升高、多饮多尿"},
    {"id": "flutd", "zh": "泌尿问题", "hint": "尿频、血尿、结石史"},
    {"id": "obesity", "zh": "超重 / 需减重", "hint": "BCS ≥ 7"},
    {"id": "diabetes", "zh": "糖尿病", "hint": "血糖高、多饮多尿多食"},
    {"id": "allergy", "zh": "食物过敏 / 皮肤瘙痒", "hint": "需排除性饮食"},
    {"id": "hairball", "zh": "毛球困扰", "hint": "频繁吐毛球、长毛品种"},
    {"id": "gi", "zh": "肠胃敏感", "hint": "软便、IBD、胰腺炎史"},
    {"id": "cardiac", "zh": "心脏问题", "hint": "HCM、心衰"},
    {"id": "joint", "zh": "关节问题", "hint": "折耳、老年、跛行"},
    {"id": "dental", "zh": "口腔 / 牙病", "hint": "口炎、拔牙后"},
    {"id": "hyperthyroid", "zh": "甲亢", "hint": "T4 升高"},
    {"id": "senior", "zh": "高龄（≥11 岁）", "hint": "常规老年支持"},
]

BASE_SPEC = {
    "protein": [38, 46],
    "fat": [15, 20],
    "phosphorus": [0.7, 1.1],
    "ca_p": "1.1–1.3 : 1",
    "taurine": "≥ 0.20%",
    "carbs": "< 15%",
    "fiber": [2.5, 4.0],
    "water": "干粮 8–10%，湿粮 75–82%",
}

SPEC_OVERRIDES = {
    "ckd": {
        "protein": [26, 34], "phosphorus": [0.3, 0.55], "fat": [16, 22],
        "carbs": "< 12%", "fiber": [2.0, 3.5], "taurine": "≥ 0.25%",
        "note": "低磷优先于低蛋白；蛋白要“少而优”，不足会掉肌肉。",
    },
    "flutd": {
        "protein": [38, 46], "fat": [15, 20], "phosphorus": [0.6, 0.9],
        "carbs": "< 10%", "water": "湿粮 ≥ 50% 热量占比",
        "note": "核心是“稀释尿液”：把水分摄入做上去，比纠结某一项指标更重要。",
    },
    "obesity": {
        "protein": [40, 50], "fat": [10, 14], "phosphorus": [0.7, 1.0],
        "fiber": [8, 12], "carbs": "< 12%",
        "note": "高蛋白 + 高纤维 + 低热量密度，减脂不减肌。",
    },
    "diabetes": {
        "protein": [45, 55], "fat": [15, 22], "carbs": "< 8%",
        "fiber": [3, 6], "water": "湿粮为主",
        "note": "碳水越低越好，且必须与胰岛素时间表配合。",
    },
    "allergy": {
        "protein": [32, 42], "fat": [15, 20], "carbs": "< 15%",
        "note": "选择单一新奇蛋白或水解蛋白；排除试验需严格 8–12 周，期间不能有任何零食。",
    },
    "hairball": {
        "fiber": [8, 12], "fat": [14, 18], "protein": [36, 44],
        "note": "可溶性纤维（车前子/南瓜）+ 湿粮，比“化毛膏”更根本。",
    },
    "gi": {
        "protein": [36, 44], "fat": [14, 18], "fiber": [3, 8],
        "note": "易消化蛋白 + 益生元/益生菌，少量多餐。",
    },
    "cardiac": {
        "protein": [38, 46], "fat": [16, 20], "taurine": "≥ 0.25%",
        "note": "保证牛磺酸与 Omega-3；限钠的证据有限，不必过度紧张。",
    },
    "joint": {
        "protein": [40, 48], "fat": [14, 18],
        "note": "控体重优先；Omega-3（EPA+DHA）有中等证据支持。",
    },
    "dental": {
        "protein": [40, 48], "fat": [15, 20],
        "note": "拔牙/口炎期用湿粮或泡软粮，避免硬颗粒刺激创面。",
    },
    "hyperthyroid": {
        "protein": [42, 52], "fat": [18, 24], "phosphorus": [0.6, 1.0],
        "note": "甲亢代谢高、肌肉流失快，治疗期需要更高热量与蛋白；确诊后由兽医定碘策略。",
    },
    "senior": {
        "protein": [40, 48], "fat": [15, 20], "phosphorus": [0.5, 0.9],
        "note": "老年猫蛋白需求不降反升，同时要盯磷与肾功能。",
    },
}


def _round(x, n=0):
    return round(x, n)


def ideal_weight(weight, bcs):
    factor = {1: 1.18, 2: 1.12, 3: 1.06, 4: 1.0, 5: 1.0, 6: 0.95, 7: 0.90, 8: 0.85, 9: 0.80}
    return round(weight * factor.get(int(bcs), 1.0), 2)


def calc_energy(profile):
    weight = float(profile.get("weight_kg") or 4.0)
    bcs = int(profile.get("bcs") or 5)
    age_m = float(profile.get("age_months") or 24)
    neutered = bool(profile.get("neutered"))
    activity = profile.get("activity", "normal")
    conditions = set(profile.get("conditions") or [])

    target = ideal_weight(weight, bcs)
    rer = 70 * (target ** 0.75)

    if age_m < 4:
        factor, stage = 3.0, "幼猫（<4 月）"
    elif age_m < 12:
        factor, stage = 2.2, "幼猫（4–12 月）"
    else:
        factor = 1.2 if neutered else 1.4
        stage = "绝育成猫" if neutered else "未绝育成猫"

    if age_m >= 132:
        factor *= 0.95
    if activity == "low":
        factor *= 0.9
    elif activity == "high":
        factor *= 1.12

    losing = bcs >= 7 or "obesity" in conditions
    if losing:
        factor = 0.8
        stage = "减重期"
    elif bcs <= 3:
        factor = max(factor, 1.35)
        stage = "增重期"

    der = rer * factor
    return {
        "weight": weight, "ideal_weight": target, "bcs": bcs,
        "rer": _round(rer), "factor": round(factor, 2), "der": _round(der),
        "stage": stage, "losing": losing,
        "water_ml": _round(target * 50),
        "delta": round(weight - target, 2),
    }


PRIORITY = ["ckd", "diabetes", "flutd", "obesity", "allergy", "gi",
            "hairball", "hyperthyroid", "cardiac", "joint", "dental", "senior"]

KEY_LABEL = {"protein": "蛋白", "fat": "脂肪", "phosphorus": "磷", "fiber": "纤维", "carbs": "碳水"}


def build_spec(conditions):
    spec = {k: (list(v) if isinstance(v, list) else v) for k, v in BASE_SPEC.items()}
    notes, ranges = [], {}
    ordered = sorted([c for c in conditions if c in SPEC_OVERRIDES],
                     key=lambda c: PRIORITY.index(c) if c in PRIORITY else 99)
    for c in ordered:
        ov = SPEC_OVERRIDES[c]
        for k, v in ov.items():
            if k == "note":
                notes.append((c, v))
                continue
            if isinstance(v, list) and isinstance(spec.get(k), list):
                ranges.setdefault(k, []).append((c, v))
            else:
                spec[k] = v
    for k, items in ranges.items():
        lo = max(x[1][0] for x in items)
        hi = min(x[1][1] for x in items)
        if lo <= hi:
            spec[k] = [lo, hi]
        else:
            winner = items[0]
            spec[k] = list(winner[1])
            if k in ("protein", "phosphorus", "fat"):
                notes.append((winner[0],
                              f"{KEY_LABEL.get(k, k)}的目标和其他状况交叉后没有交集，已优先按此方向给出，"
                              f"实际配方需要兽医或营养师平衡。"))
    return spec, notes


def build_plans(profile, energy, conditions):
    breed = profile.get("_breed") or {}
    coat = breed.get("coat")
    age_m = float(profile.get("age_months") or 24)
    kcal = energy["der"]
    dry_g = _round(kcal / KCAL_DRY)
    cans = round(kcal / (KCAL_WET * CAN_G), 1)

    cset = set(conditions)
    plans = []

    if "ckd" in cset:
        plans = [
            {"tag": "首选", "title": "肾脏处方湿粮为主（热量 70%+）",
             "desc": f"每日约 {cans} 罐（85g）+ 少量肾脏处方干粮。湿粮能同时解决“低磷”和“补水”两个核心问题。",
             "look": ["磷 ≤ 0.5% DM", "蛋白 26–32% DM 且为动物源", "Omega-3（EPA+DHA）", "钾强化"],
             "watch": "处方粮适口性差时不要硬换，先与兽医讨论，必要时用喂食管过渡。"},
            {"tag": "备选", "title": "处方干粮 + 每日 1 罐湿粮",
             "desc": f"干粮约 {dry_g}g 分 3 餐，另加 1 罐湿粮补水。适合上班族，但补水效果弱于全湿粮。",
             "look": ["磷 ≤ 0.6% DM", "钠 ≤ 0.3% DM", "可溶性纤维"],
             "watch": "干粮猫必须额外布置 3 处以上水碗或流动水。"},
            {"tag": "预算", "title": "家庭自制（需兽医营养师配方）",
             "desc": "自制能精准控磷，但极容易缺牛磺酸、钙磷失衡，必须有配方与补充剂。",
             "look": ["磷结合剂（兽医处方）", "牛磺酸补充", "定期复查电解质"],
             "watch": "不要照搬网上“肾病猫饭”配方，缺钙和低牛磺酸会加速恶化。"},
        ]
    elif "flutd" in cset:
        plans = [
            {"tag": "首选", "title": "全湿粮 / 泌尿处方湿粮",
             "desc": f"每日约 {cans} 罐，分 3–4 餐，每餐额外兑 10–15ml 温水。目标尿比重 <1.035。",
             "look": ["水分 ≥ 78%", "镁 ≤ 0.08% DM", "磷 0.6–0.9% DM", "牛磺酸 ≥0.2%"],
             "watch": "有结石史时优先用处方粮，普通“泌尿保健”粮的矿物质控制往往不够。"},
            {"tag": "备选", "title": "处方干粮 + 湿粮 1:1",
             "desc": "一半热量来自湿粮，另一半处方干粮，兼顾方便与饮水。",
             "look": ["标注“结石管理/尿液酸化”", "钙磷比 1.1–1.3"],
             "watch": "草酸钙结石不能用酸化粮，必须先确认结石类型。"},
            {"tag": "环境", "title": "饮水改造（与粮同等重要）",
             "desc": "流动水碗 ×2、宽口水碗 ×2、湿粮兑水、每天换水；猫砂盆远离食盆。",
             "look": ["每日尿团 2–4 个、每个约拳头大", "尿团突然变小/变多 → 复查"],
             "watch": "只换粮不做饮水改造，复发率仍然很高。"},
        ]
    elif "diabetes" in cset:
        plans = [
            {"tag": "首选", "title": "高蛋白低碳湿粮 + 定时定量",
             "desc": f"每日 {kcal} kcal 分 2 餐，与胰岛素注射同步（注射后进食）。碳水目标 <8% DM。",
             "look": ["蛋白 ≥ 45% DM", "碳水 < 8% DM", "无糖、无焦糖色", "肉泥质地"],
             "watch": "换粮会改变胰岛素需求，必须在兽医监控下调整剂量。"},
            {"tag": "备选", "title": "糖尿病处方粮",
             "desc": "处方粮的碳水与热量更可控，适合多猫家庭无法分开喂的情况。",
             "look": ["高蛋白", "低碳水", "标注“糖尿病管理”"],
             "watch": "自由采食会让血糖曲线完全无法解读。"},
            {"tag": "减重", "title": "同步减重计划",
             "desc": "肥胖猫减重 1–2kg 常可显著改善胰岛素敏感性，甚至缓解糖尿病。",
             "look": ["每月减 1–2% 体重", "每周固定时间称重"],
             "watch": "减重期出现拒食要立即停止，脂肪肝风险高于高血糖。"},
        ]
    elif energy["losing"]:
        plans = [
            {"tag": "首选", "title": "减重处方粮 / 高蛋白低脂湿粮",
             "desc": f"按理想体重 {energy['ideal_weight']}kg 计算，每日 {kcal} kcal，分 3–4 餐增加饱腹感。",
             "look": ["蛋白 ≥ 42% DM", "脂肪 ≤ 14% DM", "纤维 ≥ 8% DM", "热量密度 ≤ 3.5 kcal/g"],
             "watch": "减重速度控制在每月 1–2%，过快会诱发脂肪肝。"},
            {"tag": "备选", "title": "定量湿粮 + 互动喂食",
             "desc": "湿粮体积大、饱腹感强；把一部分粮放进漏食球，延长进食时间。",
             "look": ["每餐称重（厨房秤，精确到 1g）", "零食 ≤ 总热量 10%"],
             "watch": "多猫家庭必须分开喂，否则减重一定失败。"},
            {"tag": "监测", "title": "体重曲线管理",
             "desc": "每周同一时间、同一秤称重，记录到手机；连续 2 周不降就要复核热量。",
             "look": ["目标体重 " + str(energy["ideal_weight"]) + " kg", "BCS 5/9 为达标"],
             "watch": "体重不降先查“偷吃”和零食，再考虑下调 10% 热量。"},
        ]
    elif age_m < 12:
        plans = [
            {"tag": "首选", "title": "幼猫粮 + 湿粮混合，少食多餐",
             "desc": f"每日 {kcal} kcal 分 4 餐；12 月龄前不限制发育所需能量，但要监测 BCS。",
             "look": ["蛋白 ≥ 36% DM", "钙 1.0–1.5% DM", "钙磷比 1.1–1.5", "DHA"],
             "watch": "幼猫粮与成猫粮的钙磷差异很大，1 岁前不要提前换成猫粮。"},
            {"tag": "备选", "title": "全湿粮幼猫配方",
             "desc": "湿粮适口性好、补水，但要注意牙齿与成本；可作为主食长期喂养。",
             "look": ["标注“全阶段/幼猫”", "水分 75–80%"],
             "watch": "湿粮在室温放置超过 30 分钟要收走。"},
            {"tag": "习惯", "title": "建立刷牙与摸身习惯",
             "desc": "幼猫期每天摸爪、摸嘴、刷牙 10 秒，成年后体检和用药会轻松很多。",
             "look": ["每周称重一次", "3 月龄起开始刷牙"],
             "watch": "换粮用 7 天过渡法，幼猫肠胃更敏感。"},
        ]
    else:
        plans = [
            {"tag": "首选", "title": "主食湿粮 50% + 高蛋白干粮 50%",
             "desc": f"湿粮约 {round(cans * 0.5, 1)} 罐 + 干粮约 {_round(dry_g * 0.5)}g/天。兼顾补水、成本与便利。",
             "look": ["蛋白 ≥ 40% DM", "动物蛋白排配料表前 3 位", "磷 0.7–1.1% DM", "牛磺酸 ≥0.2%"],
             "watch": "湿粮开封后冷藏不超过 24 小时，喂前回温到室温。"},
            {"tag": "备选", "title": "全干粮 + 主动补水",
             "desc": f"干粮 {dry_g}g/天，配 3 处水碗 + 流动水 + 每周 2 次湿粮加餐。",
             "look": ["热量密度 3.5–4.0 kcal/g", "避免“全价+化毛+美毛”全能型模糊配方"],
             "watch": "纯干粮猫的尿比重普遍偏高，是泌尿问题的温床。"},
            {"tag": "进阶", "title": "冻干 / 生骨肉（需配比）",
             "desc": "更接近猫的自然食性，但钙磷、牛磺酸、维生素必须按配方补充。",
             "look": ["有完整营养配比表", "冷冻 −18℃ 以下 ≥72 小时（生食）"],
             "watch": "免疫低下、家有幼猫/孕妇时不建议生食。"},
        ]

    # 通用补充
    schedule = []
    meals = 4 if age_m < 6 else (3 if age_m < 12 else 2)
    per = round(kcal / meals)
    for i in range(meals):
        schedule.append({"meal": f"第 {i+1} 餐", "kcal": per, "note": "湿粮优先" if i == 0 else ""})

    transition = [
        {"day": "1–2 天", "old": "75%", "new": "25%"},
        {"day": "3–4 天", "old": "50%", "new": "50%"},
        {"day": "5–6 天", "old": "25%", "new": "75%"},
        {"day": "7 天", "old": "0%", "new": "100%"},
    ]

    avoid = ["洋葱、大蒜、韭菜（破坏红细胞）", "葡萄/葡萄干（肾损伤）", "木糖醇（低血糖、肝衰）",
             "生鱼（硫胺素酶）与生鸡蛋（沙门氏菌）", "人用奶制品（乳糖不耐）", "狗粮（牛磺酸不足）"]
    if "ckd" in cset:
        avoid.append("高磷零食：肉干、蛋黄、内脏、虾皮")
    if "flutd" in cset:
        avoid.append("高镁/高灰分的廉价干粮")
    if "diabetes" in cset:
        avoid.append("含糖半湿粮、奶油、面包")
    if "obesity" in cset:
        avoid.append("自由采食与“随手一颗”的零食")

    return {
        "kcal": kcal, "dry_g": dry_g, "cans": cans, "meals": meals,
        "schedule": schedule, "plans": plans, "transition": transition,
        "avoid": avoid,
        "water_tip": f"目标饮水约 {energy['water_ml']} ml/天（含食物水）。湿粮本身可提供 60–80% 的水分。",
    }


def build(profile, triage_result):
    """confirmed = 主人勾选的确诊病；inferred = 由客观事实推出的（超重/高龄/长毛）；
    suspected = 评估里出现但未确诊的方向 —— 只提示，不改变配方。"""
    confirmed = list(profile.get("conditions") or [])
    breed = profile.get("_breed") or {}

    inferred = []
    if breed.get("coat") in ("long", "semi") and "hairball" not in confirmed:
        inferred.append("hairball")
    if int(profile.get("bcs") or 5) >= 7 and "obesity" not in confirmed:
        inferred.append("obesity")
    if float(profile.get("age_months") or 24) >= 132 and "senior" not in confirmed:
        inferred.append("senior")
    if breed.get("id") in ("scottish-fold", "munchkin", "manx") and "joint" not in confirmed:
        inferred.append("joint")

    all_conditions = list(dict.fromkeys(confirmed + inferred))

    name_of = {c["id"]: c["zh"] for c in CONDITIONS}
    plan_hint = {
        "ckd": "肾脏处方粮（低磷、适度蛋白）",
        "flutd": "泌尿处方粮 + 湿粮为主",
        "diabetes": "高蛋白低碳水处方粮",
        "cardiac": "心脏支持配方 + 牛磺酸",
        "joint": "关节支持 / 控体重配方",
    }
    suspected = []
    for d in triage_result.get("differentials", [])[:3]:
        if d["id"] in plan_hint and d["id"] not in all_conditions:
            suspected.append({
                "id": d["id"], "zh": name_of.get(d["id"], d["id"]),
                "hint": f"若确诊{d['name']}，需在兽医指导下改用{plan_hint[d['id']]}；确诊前不要自行换处方粮。",
            })

    energy = calc_energy({**profile, "conditions": all_conditions})
    spec, notes = build_spec(all_conditions)
    plans = build_plans({**profile, "_breed": breed}, energy, all_conditions)

    checklist = [
        "看前 3 位配料：应是明确的动物蛋白（鸡肉/火鸡/鱼），而不是“肉类及其制品”。",
        "算碳水：100 − 蛋白 − 脂肪 − 灰分 − 水分，NFC 超过 20% 对猫偏高。",
        "看磷：肾病猫 ≤0.6% DM；健康猫 0.7–1.1% DM 即可，不必追求极低。",
        "看牛磺酸：≥0.2% DM，猫自身不能合成。",
        "看灰分：过高往往意味着骨粉/内脏比例大，矿物质控制差。",
        "看“全价/complete”：主食必须全价，零食罐不能当主食。",
        "看生产日期与批次：猫粮脂肪氧化会产生哈喇味，闻起来刺鼻就别喂。",
        "警惕营销词：“天然”“无谷”≠低碳水，“处方”必须兽医开具。",
    ]

    cautions = []
    if "flutd" in all_conditions and energy["losing"]:
        cautions.append("同时有泌尿风险和超重：热量按减重目标执行，但湿粮占比不能降，优先选“泌尿 + 减重”双适应症的处方粮。")
    if "ckd" in all_conditions and energy["losing"]:
        cautions.append("肾病 + 减重是典型的两难：先控磷，再用高生物价蛋白保肌肉，减重速度放慢到每月 1%。")
    if "diabetes" in all_conditions and energy["losing"]:
        cautions.append("糖尿病猫减重必须在血糖曲线监控下进行，热量下调当天就要重新评估胰岛素剂量。")
    if "allergy" in all_conditions:
        cautions.append("排除性饮食期间，零食、罐头、化毛膏、牙膏味都要统一，否则试验无效。")

    return {
        "energy": energy,
        "spec": spec,
        "spec_notes": notes,
        "conditions": [{"id": c, "zh": name_of.get(c, c)} for c in all_conditions],
        "inferred": inferred,
        "suspected": suspected,
        "plans": plans["plans"],
        "schedule": plans["schedule"],
        "transition": plans["transition"],
        "avoid": plans["avoid"],
        "water_tip": plans["water_tip"],
        "dry_g": plans["dry_g"],
        "cans": plans["cans"],
        "checklist": checklist,
        "cautions": cautions,
    }
