# -*- coding: utf-8 -*-
"""报告组装：纯函数，不读写磁盘，服务端与浏览器（Pyodide）共用。"""

from datetime import datetime
import time
import uuid

from . import breeds as breed_db
from . import triage as triage_engine
from . import nutrition as nutrition_engine
from . import litter as litter_engine
from . import care as care_engine
from . import vision

DISCLAIMER = (
    "本工具是家庭观察辅助工具，不是兽医诊断。所有“可能方向”都只是提示，"
    "确诊需要面诊、化验与影像学检查。任何用药（包括人用药、驱虫药、保健品）"
    "都必须由执业兽医决定；出现急症信号请立即就医。"
)


def build_report(payload, version="1.2.0", brand="云矿猫砂"):
    profile = dict(payload.get("profile") or {})
    observations = payload.get("observations") or {}
    photos = payload.get("photos") or []
    notes = (profile.get("notes") or "")[:1000]

    profile["sex_label"] = {"male": "公猫", "female": "母猫"}.get(profile.get("sex"), "性别未填")
    breed = breed_db.get(profile.get("breed_id", "")) or None
    profile["_breed"] = breed
    if breed:
        profile["breed_zh"] = breed["zh"]

    triage = triage_engine.evaluate(profile, observations)
    nutrition = nutrition_engine.build(profile, triage)
    litter = litter_engine.evaluate(profile, triage)
    care = care_engine.build(profile, triage, nutrition, litter)

    qc = payload.get("photo_qc")
    if qc is None and photos:
        try:
            qc = vision.analyze(photos)
        except Exception as e:  # noqa: BLE001
            qc = {"photos": [], "overall": None, "available": False, "error": str(e)}

    rid = time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
    created = datetime.now().astimezone()

    pub_profile = {k: v for k, v in profile.items() if not k.startswith("_")}
    return {
        "id": rid,
        "created_at": created.isoformat(),
        "created_label": created.strftime("%Y-%m-%d %H:%M"),
        "version": version,
        "brand": brand,
        "profile": pub_profile,
        "breed": breed_db.public(breed) if breed else None,
        "notes": notes,
        "photo_qc": qc,
        "vision_ai": payload.get("vision") or None,
        "triage": triage,
        "nutrition": nutrition,
        "litter": litter,
        "care": care,
        "disclaimer": DISCLAIMER,
    }
