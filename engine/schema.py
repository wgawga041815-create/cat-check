# -*- coding: utf-8 -*-
"""给前端的元数据（服务端与 Pyodide 静态版共用）。"""

from . import breeds as breed_db
from .observations import OBS, GROUPS
from .nutrition import CONDITIONS
from .litter import TYPES
from .triage import LEVELS
from .vision import vlm_config


def build_schema(version="1.2.0", brand="云矿猫砂", public=False, disclaimer="", static_mode=False):
    cfg = vlm_config()
    return {
        "version": version,
        "brand": brand,
        "public_mode": public,
        "static_mode": static_mode,
        "breeds": [breed_db.public(b) for b in breed_db.BREEDS],
        "groups": GROUPS,
        "observations": OBS,
        "conditions": CONDITIONS,
        "litter_types": [
            {"id": t["id"], "zh": t["zh"], "short": t["short"],
             "grain": t["grain"], "pros": t["pros"], "cons": t["cons"], "note": t["note"]}
            for t in TYPES
        ],
        "levels": LEVELS,
        "vision_configured": bool(cfg["api_key"]),
        "vision_model": cfg["model"],
        "disclaimer": disclaimer,
    }
