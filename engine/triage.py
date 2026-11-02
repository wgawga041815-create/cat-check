# -*- coding: utf-8 -*-
"""状态评估引擎：急症分级 → 鉴别方向 → 检查建议。

原则：
1. 只做“分诊 + 方向提示”，不做诊断，不给剂量。
2. 任何红旗信号都优先于打分结果。
3. 输出必须能回答三个问题：现在要不要去医院？去查什么？在家能做什么？
"""

from .observations import OBS, OBS_INDEX, RED_FLAGS
from . import breeds as breed_db

LEVELS = {
    "emergency": {
        "key": "emergency", "label": "立即急诊", "short": "急诊",
        "tone": "red", "window": "现在就出发，不要等到明天",
    },
    "urgent": {
        "key": "urgent", "label": "建议 24–72 小时内就诊", "short": "尽快就诊",
        "tone": "amber", "window": "24–72 小时内预约兽医",
    },
    "monitor": {
        "key": "monitor", "label": "先居家观察 3 天", "short": "观察",
        "tone": "olive", "window": "记录变化，3 天后复评或恶化即就医",
    },
    "healthy": {
        "key": "healthy", "label": "状态良好，做好预防", "short": "健康",
        "tone": "green", "window": "按计划做年度体检与疫苗",
    },
}

# ---------------------------------------------------------------- 鉴别方向库
CLUSTERS = [
    {
        "id": "pyometra", "name": "子宫蓄脓",
        "require": {"sex": "female", "neutered": False},
        "sigs": {"lethargy": 1.2, "polydipsia": 1.0, "pu_pd": 0.9, "anorexia": 0.8, "gi": 0.4, "weight_mild": 0.2, "pain": 0.3},
        "breeds": [],
        "why": "未绝育母猫在发情后 1–2 个月内高发。闭合式子宫蓄脓没有明显分泌物，只有精神差、多饮、腹部变大，24–48 小时内可进展为败血症。",
        "tests": ["腹部超声（子宫积液、子宫壁增厚）", "血常规（白细胞升高、核左移）", "阴道分泌物细胞学", "血生化与电解质"],
        "care": ["急诊：输液稳定 + 抗生素 + 手术（卵巢子宫切除）", "闭合式禁止挤压腹部或使用缩宫素", "术后镇痛与抗感染"],
        "note": "有发情史 + 多饮 + 精神差，即使看不到分泌物也要排查闭合式。",
    },
    {
        "id": "flutd", "name": "猫下泌尿道综合征（FLUTD）",
        "sigs": {"urinary": 1.0, "urinary_block": 1.4, "urinary_mild": 0.5, "box_avoid": 0.6, "inappropriate": 0.4, "stress": 0.3},
        "breeds": ["persian", "british-shorthair", "american-shorthair", "chartreux", "russian-blue"],
        "why": "室内、绝育、纯干粮、饮水少的猫高发；其中约 6 成是“特发性膀胱炎”，与应激强相关，尿检往往没有细菌。",
        "tests": ["尿常规 + 尿沉渣（看结晶、pH、比重）", "腹部 B 超（膀胱壁、结石、泥沙）", "血生化（肾指标、钾）"],
        "care": ["止痛解痉是核心（兽医处方）", "增加饮水：湿粮、流动水、多水碗", "环境丰容、减少应激源", "处方泌尿粮按医嘱"],
        "note": "公猫一旦尿不出，就是急症，不要在家观察。",
    },
    {
        "id": "urolith", "name": "尿结石（鸟粪石 / 草酸钙）",
        "sigs": {"urinary": 0.9, "urinary_block": 1.2, "urinary_mild": 0.4},
        "breeds": ["domestic", "british-shorthair", "chartreux"],
        "why": "血尿 + 尿频 + 尿痛，X 光/超声可见结石；鸟粪石可通过处方粮溶解，草酸钙通常需要手术或碎石。",
        "tests": ["腹部 X 光 + 超声", "尿检（结晶类型、pH）", "结石成分分析（若排出）"],
        "care": ["按结石类型选处方粮，不要自行买“泌尿保健”", "保证饮水", "定期复查影像"],
        "note": "鸟粪石与草酸钙的饮食策略相反，必须先确定类型。",
    },
    {
        "id": "ckd", "name": "慢性肾病（CKD）",
        "sigs": {"polydipsia": 0.9, "pu_pd": 1.2, "weightloss": 0.9, "weightloss_severe": 1.0, "coat_poor": 0.5, "anorexia": 0.5, "oral_pain": 0.4},
        "breeds": ["persian", "exotic-shorthair", "british-shorthair", "abyssinian", "singapura", "manx"],
        "why": "中老年猫最常见的慢性病之一；早期只有“多饮多尿 + 尿比重低”，肌酐正常时 SDMA 可能已经升高。",
        "tests": ["血生化（肌酐、BUN、磷、钾）", "SDMA", "尿常规 + 尿比重 + 尿蛋白/肌酐比", "血压", "甲状腺 T4（排除甲亢）"],
        "care": ["低磷、适度优质蛋白的肾脏处方粮", "控制蛋白尿（兽医处方药）", "补液/皮下输液按医嘱", "每 3–6 个月复查"],
        "note": "不要自行“低蛋白”到不足，猫需要优质蛋白维持肌肉。",
    },
    {
        "id": "diabetes", "name": "糖尿病",
        "sigs": {"pu_pd": 1.3, "polydipsia": 0.9, "weightloss": 0.9, "lethargy": 0.4, "coat_poor": 0.3},
        "breeds": ["burmese", "domestic", "maine-coon"],
        "why": "“多饮多尿多食 + 体重下降”是经典三联征；肥胖是最大可控风险因素。",
        "tests": ["空腹血糖 + 果糖胺", "尿糖/尿酮", "血生化、T4", "血糖曲线（确诊后）"],
        "care": ["高蛋白低碳水（<10% DM）湿粮", "定时定量，与胰岛素注射时间配合", "减重（肥胖猫可显著改善）", "家庭血糖监测"],
        "note": "出现拒食 + 呕吐 + 呼吸深快，警惕酮症酸中毒，需急诊。",
    },
    {
        "id": "hyperthyroid", "name": "甲状腺功能亢进",
        "sigs": {"weightloss": 1.0, "weightloss_severe": 0.8, "lethargy_mild": 0.3, "gi": 0.5, "gi_mild": 0.3, "coat_poor": 0.5},
        "breeds": ["domestic", "siamese"],
        "why": "10 岁以上猫约 1/10 患病；典型是“吃得多却变瘦 + 话多 + 夜嚎”，也可能只表现为消瘦。",
        "tests": ["总 T4（必要时 fT4）", "血常规 + 生化", "血压、心脏超声（甲亢会加重心脏负担）"],
        "care": ["药物、放射性碘或处方粮（三种路径由兽医评估）", "治疗初期监测肾指标（甲亢会掩盖肾病）"],
        "note": "甲亢治好之后，原本被掩盖的肾病常会暴露出来。",
    },
    {
        "id": "hcm", "name": "肥厚性心肌病（HCM）/ 心衰",
        "sigs": {"resp": 1.0, "resp_distress": 1.4, "lethargy": 0.5, "saddle_thrombus": 1.5, "anorexia": 0.2},
        "breeds": ["maine-coon", "ragdoll", "british-shorthair", "american-shorthair", "sphynx", "persian", "devon-rex", "bengal"],
        "why": "猫最常见的心脏病，早期可能只有心脏杂音或完全没症状；一旦出现呼吸急促，往往已有心衰/胸水。",
        "tests": ["心脏超声（金标准）", "NT-proBNP / 心肌标志物", "胸部 X 光、血压", "基因检测（缅因、布偶）"],
        "care": ["兽医处方的心脏药物", "低应激、避免剧烈应激", "呼吸次数家庭监测（睡眠时 <30 次/分）"],
        "note": "安静睡眠呼吸 >30 次/分，是心衰最实用的家庭预警指标。",
    },
    {
        "id": "asthma", "name": "猫哮喘 / 慢性支气管炎",
        "sigs": {"resp": 1.1, "resp_mild": 0.7, "resp_distress": 0.8},
        "breeds": ["siamese", "balinese", "burmese"],
        "why": "典型表现是“母鸡蹲 + 伸脖子干咳 + 喘”，常被误认为吐毛球。",
        "tests": ["胸部 X 光", "支气管灌洗（必要时）", "排除心衰（心超）、寄生虫"],
        "care": ["避免粉尘猫砂、香水、烟", "兽医处方吸入激素（需储雾罐）", "控制体重"],
        "note": "粉尘大的猫砂会直接加重咳嗽。",
    },
    {
        "id": "uri", "name": "上呼吸道感染（疱疹病毒 / 杯状病毒）",
        "sigs": {"nasal_discharge": 1.2, "sneeze_mild": 0.8, "eye_discharge": 0.9, "anorexia": 0.4, "lethargy": 0.4},
        "breeds": ["persian", "exotic-shorthair", "himalayan", "domestic"],
        "why": "多猫/新猫家庭高发；疱疹病毒会潜伏并在应激后复发，杯状病毒可伴口腔溃疡。",
        "tests": ["PCR（疱疹/杯状/衣原体）", "眼科检查（角膜荧光染色）", "血常规"],
        "care": ["通鼻、补液、营养支持", "抗病毒/抗生素由兽医决定（抗生素对病毒无效）", "隔离新猫，减少应激"],
        "note": "扁脸猫鼻泪管短，症状往往更重。",
    },
    {
        "id": "eye", "name": "结膜炎 / 角膜溃疡",
        "sigs": {"eye_discharge": 1.2, "tearing": 0.6, "eye_emergency": 1.4},
        "breeds": ["persian", "exotic-shorthair", "himalayan", "british-shorthair"],
        "why": "眯眼 + 分泌物 + 畏光是角膜问题的典型组合；疱疹病毒和眼睑内翻是常见诱因。",
        "tests": ["荧光素染色（查溃疡）", "眼压", "泪液分泌测试"],
        "care": ["戴伊丽莎白圈", "抗生素/抗病毒眼药由兽医开具", "不要用人用含激素眼药水"],
        "note": "角膜溃疡用激素会迅速恶化，甚至穿孔。",
    },
    {
        "id": "otitis", "name": "外耳炎 / 耳螨",
        "sigs": {"ear": 1.2, "ear_wax": 0.6, "vestibular": 1.0},
        "breeds": ["devon-rex", "sphynx", "american-curl", "persian"],
        "why": "黑褐色蜡状分泌物 + 甩头抓耳，耳螨与酵母菌感染外观相似，需要镜检区分。",
        "tests": ["耳道镜检（螨虫/酵母/细菌）", "耳道内镜（慢性）"],
        "care": ["对症耳药（兽医开具）", "不要用棉签深掏", "环境驱虫（耳螨会传染）"],
        "note": "歪头 + 眼球震颤提示中耳/内耳，需影像学。",
    },
    {
        "id": "derm", "name": "猫癣 / 过敏性皮炎",
        "sigs": {"skin_lesion": 1.2, "coat_poor": 0.6, "skin_severe": 0.8},
        "breeds": ["persian", "exotic-shorthair", "sphynx", "devon-rex", "maine-coon"],
        "why": "猫癣（犬小孢子菌）常见于幼猫与免疫低下；跳蚤过敏多见于腰背部；食物过敏常伴头颈瘙痒和耳炎。",
        "tests": ["伍德氏灯 + 真菌培养", "皮肤刮片/细胞学", "跳蚤梳检查", "8–12 周排除性饮食试验"],
        "care": ["抗真菌药（口服需兽医处方并监测肝功）", "环境消毒 + 每周吸尘", "驱虫（跳蚤）"],
        "note": "猫癣会传染给人，处理时戴手套。",
    },
    {
        "id": "dental", "name": "牙周病 / 口炎 / 牙吸收",
        "sigs": {"halitosis": 0.9, "oral_pain": 1.3, "oral_emergency": 1.2, "anorexia": 0.5, "weightloss": 0.3},
        "breeds": ["domestic", "siamese", "maine-coon", "abyssinian", "british-shorthair"],
        "why": "3 岁以上猫约 7 成有牙周问题；牙吸收（FORL）极痛但外观常不明显，只表现为吃硬粮甩头。",
        "tests": ["口腔检查（需镇静）", "牙科 X 光", "血常规生化（麻醉前）"],
        "care": ["洗牙 + 拔除病灶牙（多数情况是唯一解）", "日常刷牙（宠物专用牙膏）", "术后软食"],
        "note": "口炎猫的疼痛常被误读为“挑食”。",
    },
    {
        "id": "gi_foreign", "name": "异物 / 急性胃肠炎 / 胰腺炎",
        "sigs": {"gi": 1.1, "gi_severe": 1.4, "anorexia": 0.7, "pain": 0.6, "lethargy": 0.4},
        "breeds": ["siamese", "bengal", "domestic"],
        "why": "暹罗/孟加拉爱啃线头塑料；急性呕吐 + 腹痛 + 拒食要优先排除线性异物和胰腺炎。",
        "tests": ["腹部 X 光 + 超声", "fPL（猫胰腺脂肪酶）", "血常规生化"],
        "care": ["止吐、补液、镇痛（兽医）", "异物需手术/内镜", "恢复期少量多餐"],
        "note": "线性异物（线、绳、发圈）不要拉，会割伤肠道。",
    },
    {
        "id": "hairball", "name": "毛球症 / 毛球性胃炎",
        "sigs": {"gi_mild": 1.2, "gi": 0.6, "anorexia": 0.4, "constipation": 0.3, "coat_poor": 0.3},
        "breeds": ["dsh-lion", "persian", "ragdoll", "maine-coon", "norwegian-forest", "siberian",
                   "himalayan", "birman", "balinese", "chinchilla", "exotic-shorthair", "selkirk-rex"],
        "why": "长毛猫在换毛季把大量被毛舔进胃里。多数能自己吐出，但反复干呕、食欲下降、便秘要排除毛球梗阻。",
        "tests": ["腹部触诊 + X 光 / 超声（排除肠梗阻）", "血常规生化（排除其他呕吐原因）", "粪便检查"],
        "care": ["可溶性纤维（车前子/南瓜）+ 每周 2 次化毛膏（凡士林基）", "每天梳毛，换毛季早晚各一次", "湿粮 + 多水碗，帮助毛球排出", "每周呕吐 ≥1 次或干呕无物 → 就医"],
        "note": "「吐毛球是正常的」只在换毛季偶尔发生才成立；每周都吐就不是正常。",
    },
    {
        "id": "ibd", "name": "慢性肠病（IBD）/ 食物不耐受",
        "sigs": {"gi": 0.8, "gi_mild": 0.8, "weightloss": 0.7, "coat_poor": 0.4, "chronic": 0.4},
        "breeds": ["siamese", "bengal", "domestic"],
        "why": "慢性间歇性呕吐/软便 + 体重下降，常见于中老年猫；需与淋巴瘤鉴别。",
        "tests": ["腹部超声（肠壁厚度）", "B12/叶酸", "排除性饮食试验", "肠道活检（必要时）"],
        "care": ["单一新奇蛋白或水解蛋白粮", "B12 补充（兽医）", "免疫抑制治疗按医嘱"],
        "note": "换粮要 7–10 天过渡，频繁换粮本身会加重软便。",
    },
    {
        "id": "parasite", "name": "体内寄生虫",
        "sigs": {"gi_mild": 0.7, "coat_poor": 0.5, "weightloss": 0.4, "stress": 0.1},
        "breeds": ["domestic"],
        "why": "幼猫、户外或新领养的猫常见；蛔虫、绦虫、球虫、贾第虫表现各异。",
        "tests": ["粪便浮聚/镜检", "抗原检测（贾第虫/弓形虫）"],
        "care": ["按体重驱虫（兽医指导）", "环境清洁、及时铲屎", "幼猫按月驱虫"],
        "note": "人用驱虫药剂量与猫差异极大，不要自行投喂。",
    },
    {
        "id": "arthritis", "name": "骨关节炎 / 关节疼痛",
        "sigs": {"stiffness": 1.2, "lameness": 1.1, "pain": 0.5, "pain_mild": 0.4},
        "breeds": ["scottish-fold", "munchkin", "maine-coon", "manx", "british-shorthair", "domestic"],
        "why": "老年猫 9 成以上有影像学关节炎，但猫极擅长隐藏；“跳不上床”“不再梳理后背”就是信号。",
        "tests": ["骨科检查", "X 光", "疼痛评估量表"],
        "care": ["减重（最有效）", "环境改造：低台阶、软垫、浅盆", "镇痛（兽医处方，切勿用人用止痛药）", "Omega-3"],
        "note": "猫不能用对乙酰氨基酚/布洛芬，微量即可致死。",
    },
    {
        "id": "ocd", "name": "折耳骨软骨发育不良（OCD）",
        "sigs": {"lameness": 1.3, "stiffness": 1.3, "pain": 0.5},
        "breeds": ["scottish-fold"],
        "why": "折耳基因即软骨发育异常基因，纯合个体症状更重；尾巴僵硬、后肢外八字是早期表现。",
        "tests": ["全身骨骼 X 光（尾椎、跗关节、掌骨）", "步态评估"],
        "care": ["控体重 + 关节保护", "镇痛方案由兽医制定", "避免高处跳跃"],
        "note": "没有根治手段，重点是延缓进展与疼痛管理。",
    },
    {
        "id": "lipidosis", "name": "肝脂肪沉积（脂肪肝）",
        "sigs": {"anorexia": 1.0, "anorexia_severe": 1.5, "weightloss": 0.6, "lethargy": 0.4},
        "breeds": [],
        "why": "胖猫连续 2–3 天不吃就可能启动；黄疸、呕吐、精神沉郁是进展信号。",
        "tests": ["血生化（ALT/ALP/胆红素）", "腹部超声", "凝血功能"],
        "care": ["必须尽早建立肠内营养（鼻饲/食道管）", "住院支持治疗", "严禁强行灌食（误吸风险）"],
        "note": "这是“拖出来的病”，拒食 24 小时就该联系兽医。",
    },
    {
        "id": "tumor", "name": "肿瘤 / 淋巴结肿大",
        "sigs": {"lump": 1.3, "lump_small": 0.6, "lump_severe": 1.4, "weightloss": 0.5, "lethargy": 0.3},
        "breeds": ["siamese", "burmese", "domestic"],
        "why": "猫的肿块良性比例不低，但细针抽吸（FNA）十几分钟就能给出方向，不必等。",
        "tests": ["细针抽吸细胞学", "影像学分期", "血常规生化"],
        "care": ["确诊后按类型选择手术/化疗/姑息", "疼痛管理与营养支持"],
        "note": "肿块 >1cm 或一个月内变大，建议直接穿刺。",
    },
    {
        "id": "constipation", "name": "便秘 / 巨结肠",
        "sigs": {"constipation": 1.3, "pain": 0.4, "anorexia": 0.3},
        "breeds": ["manx", "domestic"],
        "why": "老年猫、饮水少、毛球、骨盆狭窄都可能便秘；曼岛猫有神经性肠道风险。",
        "tests": ["腹部触诊 + X 光", "血生化（钾、钙、肾）", "甲状腺"],
        "care": ["增加饮水与纤维", "必要时灌肠/手动排便（医院）", "严重者需结肠切除"],
        "note": "超过 48 小时未排便 + 呕吐，要尽快就医。",
    },
    {
        "id": "stress", "name": "应激相关行为与生理反应",
        "sigs": {"stress": 1.0, "inappropriate": 0.8, "box_avoid": 0.6, "lethargy_mild": 0.3, "hyporexia": 0.4},
        "breeds": [],
        "why": "搬家、新成员、换砂、装修都会引起应激性膀胱炎、拒食、乱尿；先排除医学问题再归因于行为。",
        "tests": ["尿检（排除炎症/结晶）", "血生化"],
        "care": ["恢复原有作息与气味", "费洛蒙、躲藏点、垂直空间", "猫砂盆 N+1、每日铲 2 次"],
        "note": "“报复性乱尿”是误解，猫没有报复这个概念。",
    },
    {
        "id": "obesity", "name": "超重 / 肥胖相关风险",
        "sigs": {},
        "breeds": ["british-shorthair", "domestic", "chartreux", "scottish-fold", "munchkin", "ragdoll"],
        "why": "体况评分 ≥7 时，糖尿病、关节炎、心脏病、脂肪肝风险都会显著上升。",
        "tests": ["血生化 + 血糖", "血压", "体况评分 BCS"],
        "care": ["按理想体重计算热量（见猫粮方案）", "每周称重，目标每月减 1–2%", "增加互动游戏"],
        "note": "猫减重必须慢，快速减重会诱发脂肪肝。",
    },
]


# 兽医可能考虑的药物类别（只写类别与用途，不含剂量；不可自行购买使用）
DRUG_CLASSES = {
    "hairball": ["化毛膏（凡士林基，兽医指导）", "可溶性纤维补充", "频繁呕吐时用止吐药（兽医处方）"],
    "pyometra": ["静脉输液与电解质", "广谱抗生素（兽医处方）", "手术：卵巢子宫切除（根本治疗）", "术后镇痛"],
    "flutd": ["镇痛：阿片类 / NSAID（兽医处方）", "解除尿道痉挛：α 受体阻滞剂", "抗焦虑与信息素辅助", "抗生素仅在尿检证实感染时使用"],
    "urolith": ["解痉与镇痛", "鸟粪石：处方溶解粮（非药物）", "草酸钙：手术 / 碎石", "术后抗生素按需"],
    "ckd": ["磷结合剂（随餐）", "ACEI / ARB 控制蛋白尿", "止吐药（如马罗匹坦）", "钾补充 / 促红细胞生成素（按需）"],
    "diabetes": ["胰岛素（种类与剂量由兽医确定）", "血糖曲线监测", "酮症酸中毒需住院输液"],
    "hyperthyroid": ["甲巯咪唑 / 卡比马唑", "放射性碘治疗", "甲状腺处方粮（碘限制）"],
    "hcm": ["呋塞米（肺水肿/胸水）", "匹莫苯丹", "氯吡格雷（预防血栓）", "ACEI / 其他心衰用药"],
    "asthma": ["吸入糖皮质激素（氟替卡松）", "支气管扩张剂（急救）", "短期口服激素（急性期）"],
    "uri": ["抗病毒（如泛昔洛韦，疱疹病毒）", "抗生素仅用于继发细菌感染", "通鼻滴剂 / 雾化（生理盐水）"],
    "eye": ["抗生素眼药（细菌性）", "抗病毒眼药（疱疹）", "角膜修复滴眼液", "禁：溃疡时使用含激素眼药"],
    "otitis": ["耳道清洁剂", "抗真菌 / 抗菌耳药", "耳螨：塞拉菌素 / 莫昔克丁类"],
    "derm": ["抗真菌：伊曲康唑 / 特比萘芬", "药浴（氯己定/咪康唑）", "跳蚤/螨驱虫", "短期抗组胺或激素（瘙痒控制）"],
    "dental": ["麻醉下洁牙与拔牙（主要手段）", "围手术期抗生素", "术后镇痛", "口腔凝胶 / 漱口水（辅助）"],
    "gi_foreign": ["止吐（马罗匹坦）", "胃黏膜保护剂", "补液与电解质", "异物：内镜或手术取出"],
    "ibd": ["糖皮质激素（泼尼松龙 / 布地奈德）", "维生素 B12 补充", "免疫抑制剂（苯丁酸氮芥等）", "水解蛋白处方粮"],
    "parasite": ["按虫种选择：吡喹酮 / 芬苯达唑 / 塞拉菌素等", "环境同步清洁", "幼猫按月驱虫"],
    "arthritis": ["NSAID（美洛昔康 / 罗贝纳考昔）", "加巴喷丁（神经痛/镇痛辅助）", "单克隆抗体（夫卢马单抗）", "关节补充剂（证据有限）"],
    "ocd": ["镇痛（NSAID / 加巴喷丁）", "体重控制（最基础）", "物理治疗与关节保护", "无根治药物"],
    "lipidosis": ["肠内营养（鼻饲/食道管）", "止吐与肝支持（SAMe / 水飞蓟素）", "维生素 K1（凝血异常时）", "严禁强行灌食"],
    "tumor": ["按病理类型：手术 / 化疗 / 靶向", "姑息镇痛", "营养支持"],
    "constipation": ["乳果糖（软化粪便）", "促动力药（西沙必利）", "灌肠（医院操作）", "膳食纤维与饮水调整"],
    "stress": ["费洛蒙（环境信息素）", "行为与环境改造", "抗焦虑药（仅兽医评估后）"],
}

# 严重度信号 → 基础分
SEV_W = {0: 0, 1: 0.35, 2: 0.85, 3: 1.5}

SIG_LABEL = {
    "lethargy_mild": "精神略差", "lethargy": "精神沉郁", "neuro": "神经症状",
    "pain_mild": "轻度疼痛表现", "pain": "疼痛表现", "pain_severe": "剧烈疼痛",
    "hyporexia": "食欲下降", "anorexia": "明显厌食", "anorexia_severe": "长时间拒食",
    "polydipsia_mild": "饮水略多", "polydipsia": "饮水增多", "pu_pd": "多饮多尿",
    "weight_mild": "体重轻微变化", "weightloss": "体重下降", "weightloss_severe": "快速消瘦",
    "tearing": "泪溢", "eye_discharge": "眼分泌物", "eye_emergency": "眼科急症",
    "sneeze_mild": "偶发喷嚏", "nasal_discharge": "脓性鼻分泌物", "epistaxis": "鼻出血",
    "halitosis": "口臭", "oral_pain": "口腔疼痛", "oral_emergency": "口腔急症",
    "ear_wax": "耳垢", "ear": "耳道异常", "vestibular": "前庭症状",
    "coat_poor": "被毛粗糙", "skin_lesion": "皮肤病灶", "skin_severe": "严重皮肤/黄疸",
    "lump_small": "小肿块", "lump": "肿块增大", "lump_severe": "肿块破溃",
    "gi_mild": "轻度胃肠症状", "gi": "呕吐/腹泻", "gi_severe": "消化道急症",
    "stool_mild": "排便性状改变", "constipation": "便秘", "melena": "便血/黑便",
    "urinary_mild": "排尿次数增多", "urinary": "排尿异常", "urinary_block": "排尿困难/尿闭",
    "inappropriate": "盆外排泄", "box_avoid": "回避猫砂盆",
    "resp_mild": "轻度呼吸道症状", "resp": "呼吸异常", "resp_distress": "呼吸困难",
    "stiffness": "僵硬/跳跃犹豫", "lameness": "跛行", "saddle_thrombus": "后肢瘫痪",
    "stress": "近期应激", "chronic": "慢性病在治", "toxin": "误食/外伤",
}

HIGH_PRIORITY = {
    "urinary", "urinary_block", "eye_discharge", "eye_emergency", "oral_pain",
    "gi", "constipation", "resp", "resp_distress", "lameness", "weightloss",
    "polydipsia", "pu_pd", "ear", "skin_lesion", "lump", "nasal_discharge",
    "lethargy", "pain", "anorexia",
}


def _collect(observations):
    """observations: {obs_id: option_index} → 列表 + 信号表"""
    picked, signals = [], {}
    for o in OBS:
        idx = observations.get(o["id"])
        if idx is None:
            continue
        idx = max(0, min(len(o["options"]) - 1, int(idx)))
        opt = o["options"][idx]
        picked.append({
            "id": o["id"], "label": o["label"], "answer": opt["label"],
            "sev": opt["sev"], "sig": opt["sig"],
        })
        if opt["sig"]:
            signals[opt["sig"]] = max(signals.get(opt["sig"], 0), opt["sev"])
    return picked, signals


def _score(cluster, signals, breed, age_months, bcs):
    score, evidence = 0.0, []
    for sig, w in cluster["sigs"].items():
        if sig in signals:
            add = w * (0.55 + 0.35 * signals[sig])
            score += add
            evidence.append(SIG_LABEL.get(sig, sig))
    matched_breed = bool(breed and breed["id"] in cluster["breeds"])
    if matched_breed:
        score += 0.55
    if cluster["id"] == "obesity" and bcs and bcs >= 7:
        score += 1.2
        evidence.append(f"体况评分 {bcs}/9")
    if cluster["id"] == "lipidosis" and bcs and bcs >= 7:
        score += 0.3
    if cluster["id"] == "hyperthyroid" and age_months and age_months >= 96:
        score += 0.35
    if cluster["id"] == "ckd" and age_months and age_months >= 84:
        score += 0.3
    if cluster["id"] == "arthritis" and age_months and age_months >= 96:
        score += 0.3
    return score, evidence, matched_breed


def breed_advisories(profile, breed):
    """品种/毛色层面的前置提醒：不依赖症状也会显示。"""
    if not breed:
        return []
    out = []
    neutered = bool(profile.get("neutered"))
    sex = profile.get("sex")
    for a in breed.get("advisories", []):
        when = a.get("when")
        if when == "always":
            ok = True
        elif when == "unneutered":
            ok = not neutered
        elif when == "unneutered_female":
            ok = (not neutered) and sex == "female"
        elif when == "male":
            ok = sex == "male"
        else:
            ok = False
        if ok:
            out.append({"level": a.get("level", "info"), "title": a["title"], "text": a["text"]})
    return out


def evaluate(profile, observations):
    breed = breed_db.get(profile.get("breed_id", ""))
    age_m = float(profile.get("age_months") or 24)
    bcs = int(profile.get("bcs") or 5)
    picked, signals = _collect(observations)

    # ---------------- 1. 红旗 ----------------
    red = []
    seen = set()
    for p in picked:
        if p["sev"] >= 3 and p["sig"] in RED_FLAGS and p["sig"] not in seen:
            seen.add(p["sig"])
            red.append(dict(RED_FLAGS[p["sig"]], sig=p["sig"]))
    # 胖猫拒食 → 脂肪肝红旗
    if bcs >= 7 and any(p["sig"] == "anorexia_severe" for p in picked) and "anorexia_severe" not in seen:
        red.append(dict(RED_FLAGS["anorexia_severe"], sig="anorexia_severe"))

    highs = [p for p in picked if p["sev"] >= 2]
    eights = [p for p in picked if p["sev"] == 3]
    if eights:
        level = "emergency"
    elif len(highs) >= 2:
        level = "urgent"
    elif len(highs) == 1:
        level = "urgent"
    elif any(p["sev"] == 1 for p in picked):
        level = "monitor"
    else:
        level = "healthy"

    # ---------------- 2. 鉴别方向 ----------------
    ranked = []
    for c in CLUSTERS:
        req = c.get("require")
        if req:
            if req.get("sex") and profile.get("sex") != req["sex"]:
                continue
            if req.get("neutered") is False and profile.get("neutered"):
                continue
            if req.get("neutered") is True and not profile.get("neutered"):
                continue
        s, ev, mb = _score(c, signals, breed, age_m, bcs)
        if s <= 0.28:
            continue
        if not ev and not (c["id"] == "obesity" and bcs >= 7):
            continue
        ranked.append((s, c, ev, mb))
    ranked.sort(key=lambda x: -x[0])

    differentials = []
    for s, c, ev, mb in ranked[:4]:
        conf = min(0.92, 0.28 + s * 0.19)
        differentials.append({
            "id": c["id"], "name": c["name"], "confidence": round(conf, 2),
            "why": c["why"], "tests": c["tests"], "care": c["care"],
            "note": c["note"], "evidence": ev,
            "drugs": DRUG_CLASSES.get(c["id"], []),
            "breed_related": mb,
            "label": "高度相关" if conf >= 0.7 else ("需要排查" if conf >= 0.5 else "可能性较低"),
        })

    # ---------------- 3. 品种关注点 ----------------
    breed_focus = []
    if breed:
        for n, r, note in breed["predis"]:
            if r in ("极高", "高"):
                breed_focus.append({"name": n, "risk": r, "note": note})

    # ---------------- 4. 给医生的问题 ----------------
    questions = []
    skip = ("体况评分", "疼痛评估", "步态评估", "环境")
    for d in differentials[:3]:
        tests = [t for t in d["tests"] if not t.startswith(skip)]
        if not tests:
            continue
        q = f"是否需要做「{tests[0]}」来排查{d['name']}？"
        if q not in questions:
            questions.append(q)
    if red:
        questions.insert(0, "现在最优先要排除的急症是什么？")
    if bcs >= 7:
        questions.append("以它目前的体况，安全的减重目标和速度是多少？")
    if age_m >= 96:
        questions.append("这个年龄需要补做哪些年度筛查（T4、SDMA、血压）？")

    # ---------------- 5. 结论文案 ----------------
    level_info = dict(LEVELS[level])
    if level == "emergency":
        headline = red[0]["title"] if red else "存在急症信号，请立即就医"
        summary = "观察到至少一项急症级别的信号。这类情况在家处理的收益很低，延误的风险很高。"
    elif level == "urgent":
        names = "、".join(dict.fromkeys(p["label"] for p in highs))
        headline = f"有 {len(highs)} 项信号需要专业评估：{names}"
        summary = "目前不一定是急症，但已经超出“再观察看看”的范围，建议 24–72 小时内就诊。"
    elif level == "monitor":
        names = "、".join(dict.fromkeys(p["label"] for p in picked if p["sev"] == 1)) or "轻微变化"
        headline = f"整体尚可，有轻微变化：{names}"
        summary = "先做 3 天居家观察并记录，如果出现恶化（拒食、精神变差、排尿异常）就升级为就医。"
    else:
        headline = "各项观察未见异常"
        summary = "当前状态良好。接下来的重点是体重管理、饮水、口腔和环境丰容这些“平时看不出、老了才要命”的事。"

    return {
        "level": level,
        "level_label": level_info["label"],
        "level_short": level_info["short"],
        "tone": level_info["tone"],
        "window": level_info["window"],
        "headline": headline,
        "summary": summary,
        "red_flags": red,
        "differentials": differentials,
        "breed_focus": breed_focus,
        "breed_advisories": breed_advisories(profile, breed),
        "vet_questions": questions[:6],
        "picked": picked,
        "signals": [SIG_LABEL.get(k, k) for k in signals.keys()],
        "counts": {
            "total": len(picked),
            "sev3": len(eights),
            "sev2": len([p for p in picked if p["sev"] == 2]),
            "sev1": len([p for p in picked if p["sev"] == 1]),
            "normal": len([p for p in picked if p["sev"] == 0]),
        },
    }
