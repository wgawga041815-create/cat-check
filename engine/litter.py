# -*- coding: utf-8 -*-
"""猫砂与猫砂盆方案引擎。

打分维度（1–5，粉尘/带出/误食风险为“越低越好”，计算时取反）：
结团 clump / 低尘 dust / 少带出 tracking / 除臭 odor / 轻便 light /
可冲厕 flush / 误食风险 ingest / 脚感 paw / 吸水 absorb / 性价比 cost

同一套逻辑既能推荐类型，也能解释“为什么是它”。
"""

TYPES = [
    {
        "id": "mineral", "zh": "矿砂 / 膨润土结团砂", "short": "矿砂",
        "attrs": {"clump": 5, "dust": 3, "tracking": 3, "odor": 4, "light": 2,
                  "flush": 1, "ingest": 1, "paw": 2, "absorb": 5, "cost": 2},
        "grain": "1.5–3 mm 圆粒",
        "pros": ["结团最硬，铲屎轻松、尿团完整易观察", "除臭与吸水强，多猫家庭友好", "单位成本低"],
        "cons": ["重量大，搬运与冲厕所都不方便", "低价产品粉尘明显，长期吸入刺激呼吸道"],
        "note": "选“低尘、圆粒、无香精”的矿砂；结团太硬粘盆底的反而难铲。",
    },
    {
        "id": "tofu", "zh": "豆腐砂（植物砂）", "short": "豆腐砂",
        "attrs": {"clump": 3, "dust": 1, "tracking": 3, "odor": 3, "light": 3,
                  "flush": 5, "ingest": 2, "paw": 3, "absorb": 3, "cost": 4},
        "grain": "2–3 mm 条状",
        "pros": ["可冲厕所、轻便", "粉尘极低，对呼吸道和皮肤友好", "误食少量相对安全"],
        "cons": ["结团偏软、易粘底", "潮湿环境易霉变生虫", "品质差异大，便宜款易碎成粉"],
        "note": "潮湿地区要小包装 + 密封；结团软就铺厚一点（6–8cm）。",
    },
    {
        "id": "mixed", "zh": "混合砂（矿砂 + 植物砂）", "short": "混合砂",
        "attrs": {"clump": 5, "dust": 3, "tracking": 3, "odor": 4, "light": 3,
                  "flush": 2, "ingest": 2, "paw": 3, "absorb": 5, "cost": 3},
        "grain": "1.5–3 mm 混合",
        "pros": ["兼顾结团力与低粉尘", "比纯矿砂轻，比纯豆腐砂好铲", "自动猫砂盆适配度高"],
        "cons": ["成分比例不透明，质量看厂家", "多数不可冲厕"],
        "note": "看矿砂/植物砂比例；植物砂占比高的更轻但结团弱。",
    },
    {
        "id": "pine", "zh": "松木砂（木屑颗粒）", "short": "松木砂",
        "attrs": {"clump": 1, "dust": 2, "tracking": 2, "odor": 3, "light": 3,
                  "flush": 1, "ingest": 1, "paw": 2, "absorb": 4, "cost": 3},
        "grain": "6 mm 颗粒（双层盆专用）",
        "pros": ["天然木香、除臭好", "用量省，尿后变粉落到底层", "适合双层猫砂盆"],
        "cons": ["不结团，无法观察尿团大小", "颗粒硬、脚感一般，部分猫抗拒", "劣质松木含酚类气味刺激"],
        "note": "泌尿高风险猫不建议，因为看不到尿团变化。",
    },
    {
        "id": "paper", "zh": "纸砂", "short": "纸砂",
        "attrs": {"clump": 1, "dust": 1, "tracking": 1, "odor": 2, "light": 5,
                  "flush": 1, "ingest": 1, "paw": 4, "absorb": 3, "cost": 4},
        "grain": "5–8 mm 纸粒",
        "pros": ["几乎无粉尘、极轻", "脚感软，术后/幼猫/老年猫友好", "误食风险最低"],
        "cons": ["除臭弱、需勤换", "不结团、无法观察尿量", "价格偏高"],
        "note": "最适合术后、呼吸道敏感、刚到家不敢用砂的猫做过渡。",
    },
    {
        "id": "crystal", "zh": "水晶砂（硅胶）", "short": "水晶砂",
        "attrs": {"clump": 2, "dust": 2, "tracking": 2, "odor": 4, "light": 4,
                  "flush": 1, "ingest": 5, "paw": 1, "absorb": 5, "cost": 4},
        "grain": "2–5 mm 透明颗粒",
        "pros": ["吸味强、耐用、轻", "尿后变色，便于判断次数"],
        "cons": ["颗粒硬、扎脚，很多猫不喜欢", "误食后吸水膨胀，有肠梗阻风险", "无法结团，尿量判断粗糙"],
        "note": "幼猫、异食癖、术后猫不要用。",
    },
    {
        "id": "walnut", "zh": "核桃砂 / 植物颗粒砂", "short": "核桃砂",
        "attrs": {"clump": 3, "dust": 3, "tracking": 3, "odor": 3, "light": 3,
                  "flush": 1, "ingest": 2, "paw": 3, "absorb": 3, "cost": 4},
        "grain": "2–4 mm",
        "pros": ["天然材质、可降解", "结团中等、重量轻"],
        "cons": ["除臭一般", "受潮易霉", "品牌少、稳定性差"],
        "note": "对坚果过敏的家庭慎用。",
    },
]

TYPE_INDEX = {t["id"]: t for t in TYPES}

SOP = [
    {"t": "每天", "d": "铲屎 2 次（早晚各一次），尿团和便便当天清走。"},
    {"t": "每天", "d": "补砂到 5–7cm 深；砂太浅会粘底，太难铲猫就不爱用。"},
    {"t": "每周", "d": "整盆换砂 1 次（多猫家庭 2 次），盆体用无香皂清洗并彻底晾干。"},
    {"t": "每月", "d": "检查盆体划痕：划痕多的塑料盆会藏菌，建议 12–18 个月换新盆。"},
    {"t": "随时", "d": "猫砂盆数量 = 猫的数量 + 1，且分散摆放，不要并排。"},
]

BOX_RULES = [
    "尺寸：盆长 ≥ 猫体长（鼻尖到尾根）的 1.5 倍，多数成猫需要 ≥60cm。",
    "高度：幼猫/短腿/老年猫入口 ≤10cm；健康成猫高边防刨出。",
    "位置：安静、通风、远离食盆与水碗，不要放在洗衣机/冰箱旁。",
    "盖子：多数猫偏好开放式；全封闭盆会积氨气，呼吸道敏感的猫更不适合。",
    "深度：砂层 5–7cm；长毛猫 6–8cm 防粘毛。",
    "过渡：换砂时新旧各半混 7 天，别一次全换。",
]


def _priorities(profile, triage):
    """根据画像与评估结果生成维度权重。"""
    w = {"clump": 1.0, "dust": 1.0, "tracking": 0.7, "odor": 0.8,
         "light": 0.4, "flush": 0.2, "ingest": 1.0, "paw": 0.8,
         "absorb": 1.0, "cost": 0.5}
    breed = profile.get("_breed") or {}
    age_m = float(profile.get("age_months") or 24)
    reasons = []

    if breed.get("face") == "flat":
        w["dust"] += 2.2
        w["tracking"] += 0.3
        reasons.append("扁脸品种的鼻泪管与上气道更敏感，低粉尘是第一优先级。")
    if breed.get("coat") in ("long", "semi"):
        w["tracking"] += 1.8
        w["paw"] += 0.3
        reasons.append("长毛猫会把砂粒带进毛发，低带出与圆粒更省心。")
    color = breed.get("color") or ""
    if ("白" in color or "黑" in color) and breed.get("group") == "tianyuan":
        w["dust"] += 0.9
        reasons.append("浅色毛会把粉尘显成灰，深色毛会把粉尘显成白点，低粉尘砂更耐看、也少被舔进肚子。")
    if breed.get("coat") == "hairless":
        w["dust"] += 2.0
        w["paw"] += 1.2
        reasons.append("无毛猫皮肤直接接触猫砂，粉尘与尖锐颗粒都容易引起刺激。")
    if age_m < 6:
        w["ingest"] += 2.5
        w["dust"] += 1.0
        reasons.append("幼猫有舔爪、误食猫砂的风险，优先低误食风险材质。")
    if age_m >= 132:
        w["paw"] += 1.4
        w["light"] += 1.0
        w["dust"] += 0.8
        reasons.append("老年猫关节退化，浅盆、软脚感、轻便换砂更友好。")
    if breed.get("id") in ("munchkin", "scottish-fold", "manx"):
        w["paw"] += 1.4
        w["ingest"] += 0.5
        reasons.append("短腿/关节问题品种需要低入口，抬腿跨盆会加重疼痛。")
    if int(profile.get("multicat") or 0) >= 2:
        w["odor"] += 1.6
        w["clump"] += 0.6
        reasons.append("多猫家庭除臭与结团强度直接决定你多久要整盆换砂。")

    ids = [d["id"] for d in triage.get("differentials", [])[:3]]
    if "flutd" in ids or "urolith" in ids:
        w["clump"] += 1.8
        w["absorb"] += 1.0
        reasons.append("有泌尿风险时，能形成完整尿团的砂才看得出“尿量在变少”。")
    if "asthma" in ids or "uri" in ids:
        w["dust"] += 2.5
        reasons.append("已出现呼吸道症状，粉尘会直接加重咳嗽与喷嚏。")
    if "arthritis" in ids or "ocd" in ids:
        w["paw"] += 1.6
        w["light"] += 0.8
        reasons.append("关节疼痛期要减少跨盆与刨砂的负担。")

    if profile.get("flush") == "yes":
        w["flush"] += 1.8
        reasons.append("你有冲厕所的习惯，可冲厕材质能省掉每天拎垃圾。")
    if profile.get("budget") == "low":
        w["cost"] += 1.6
        reasons.append("按预算优先，矿砂/混合砂的单位成本更低。")
    if profile.get("auto_box") == "yes":
        w["clump"] += 1.2
        w["tracking"] += 0.8
        reasons.append("自动猫砂盆对结团强度和颗粒大小更挑，细颗粒矿砂/混合砂更稳。")
    return w, reasons


def _score(t, w):
    a = t["attrs"]
    score = 0.0
    total = 0.0
    for k, weight in w.items():
        v = a.get(k, 3)
        if k in ("dust", "tracking", "ingest"):
            v = 6 - v
        score += weight * v
        total += weight * 5
    return round(score / total, 3)


def evaluate(profile, triage):
    w, reasons = _priorities(profile, triage)
    scored = sorted(TYPES, key=lambda t: -_score(t, w))
    best = scored[0]
    alts = scored[1:3]

    # 幼猫 / 术后 / 呼吸道 → 硬性提示
    cautions = []
    age_m = float(profile.get("age_months") or 24)
    if age_m < 6 and best["id"] in ("mineral", "mixed"):
        cautions.append("幼猫期建议先用非结团或大颗粒砂过渡到 6 月龄，降低误食结团砂的风险。")
    if best["id"] == "crystal":
        cautions.append("水晶砂误食后会吸水膨胀，家有幼猫或异食癖猫不要用。")

    if len(reasons) < 2:
        reasons.append(
            "单猫室内、没有特殊呼吸道或关节问题：优先选结团稳定、粉尘可控的类型，"
            "日常铲屎和观察尿团都更省事。"
        )

    num_cats = max(1, int(profile.get("multicat") or 1))
    boxes = num_cats + 1
    if int(profile.get("bcs") or 5) >= 7 or age_m >= 132:
        box_size = "超大号（≥65cm，建议 70cm）"
    elif (profile.get("_breed") or {}).get("size") == "large":
        box_size = "XXL（≥70cm）"
    else:
        box_size = "大号（≥60cm）"

    entry = "≤10cm"
    if age_m >= 132 or (profile.get("_breed") or {}).get("id") in ("munchkin", "scottish-fold", "manx"):
        entry = "≤8cm，盆前加缓坡/台阶"
    if age_m < 6:
        entry = "≤10cm，方便进出"

    return {
        "primary": {
            "id": best["id"], "zh": best["zh"], "short": best["short"],
            "score": _score(best, w), "grain": best["grain"],
            "pros": best["pros"], "cons": best["cons"], "note": best["note"],
        },
        "alternatives": [
            {"id": t["id"], "zh": t["zh"], "short": t["short"],
             "score": _score(t, w), "why": t["pros"][0], "note": t["note"]}
            for t in alts
        ],
        "reasons": reasons,
        "cautions": cautions,
        "weights": w,
        "box": {
            "count": boxes, "size": box_size, "entry": entry,
            "litter_depth": "6–8cm" if (profile.get("_breed") or {}).get("coat") in ("long", "semi") else "5–7cm",
            "type": "开放式（多数猫偏好）" if not profile.get("auto_box") == "yes" else "自动盆 + 备用开放式盆",
        },
        "sop": SOP,
        "box_rules": BOX_RULES,
        "brand": MINERAL_BRAND_NOTE if best["id"] in ("mineral", "mixed") else "",
    }


MINERAL_BRAND_NOTE = (
    "矿砂类可关注“低尘圆粒 + 结团强度”两项硬指标；本工具由云矿猫砂支持，"
    "但推荐逻辑只基于类型，不构成品牌背书。"
)
