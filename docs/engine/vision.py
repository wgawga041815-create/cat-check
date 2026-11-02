# -*- coding: utf-8 -*-
"""照片分析：本地画质质检（PIL + numpy） + 可选的多模态模型视觉评估。

设计原则：
- 没有配置视觉模型时，工具依然完整可用（问卷驱动），照片只做质检与主色提取。
- 视觉模型的输出一律标记为“AI 预填”，必须由主人确认后才进入评估。
- 模型不参与诊断，只负责“看图描述体征”，避免幻觉式诊断。
"""

import base64
import io
import json
import os
import urllib.request
import urllib.error

try:
    import numpy as np
    from PIL import Image, ImageFilter, ImageStat
    PIL_OK = True
except ImportError:  # 没装 Pillow/numpy 时，照片分析降级为不可用
    PIL_OK = False

MAX_SIDE = 900

VLM_SYSTEM = """你是一名猫科临床助理，只做“图片可见体征”的客观描述，不做诊断、不给药。
必须严格输出 JSON，不要输出任何解释文字。字段如下：
{
  "cat_visible": true/false,
  "photo_quality": "好|一般|差",
  "body_condition": {"estimate": "偏瘦|理想|超重|无法判断", "confidence": 0.0-1.0, "cue": "你看到的依据"},
  "eyes": {"finding": "...", "severity": 0-3, "confidence": 0.0-1.0},
  "nose_mouth": {"finding": "...", "severity": 0-3, "confidence": 0.0-1.0},
  "ears": {"finding": "...", "severity": 0-3, "confidence": 0.0-1.0},
  "coat": {"finding": "...", "severity": 0-3, "confidence": 0.0-1.0},
  "posture": {"finding": "...", "severity": 0-3, "confidence": 0.0-1.0},
  "breathing_visible": "无法从静态图判断",
  "red_flags": ["只写图片上确实能看到的"],
  "suggested_observations": {"eyes": 0-3, "nose": 0-3, "ears": 0-3, "coat": 0-3, "mood": 0-3},
  "summary": "一句话客观描述",
  "limits": "这张图看不出来什么"
}
severity 定义：0=正常，1=轻微，2=明显异常，3=急症外观。
看不到的部位必须写“无法判断”，severity 填 0，confidence 填 0。不要猜测品种。"""


def _load(data_url):
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    raw = base64.b64decode(data_url)
    im = Image.open(io.BytesIO(raw))
    return im.convert("RGB")


def _laplacian_var(gray):
    a = np.asarray(gray, dtype=np.float64)
    lap = (
        -4 * a
        + np.roll(a, 1, 0) + np.roll(a, -1, 0)
        + np.roll(a, 1, 1) + np.roll(a, -1, 1)
    )
    return float(lap[2:-2, 2:-2].var())


def _color_label(rgb):
    r, g, b = [v / 255.0 for v in rgb]
    mx, mn = max(r, g, b), min(r, g, b)
    v = mx
    s = 0 if mx == 0 else (mx - mn) / mx
    if mx == mn:
        h = 0
    elif mx == r:
        h = (60 * ((g - b) / (mx - mn)) + 360) % 360
    elif mx == g:
        h = 60 * ((b - r) / (mx - mn)) + 120
    else:
        h = 60 * ((r - g) / (mx - mn)) + 240
    if v < 0.25:
        return "深色 / 黑色系"
    if s < 0.12 and v > 0.78:
        return "白色 / 浅色系"
    if s < 0.15:
        return "灰色系"
    if 15 <= h <= 45:
        return "橘色 / 黄色系"
    if 45 < h <= 75:
        return "黄褐 / 奶油色系"
    if h < 15 or h >= 340:
        return "棕红 / 巧克力色系"
    return "花色 / 混合"


def analyze_one(data_url, role="侧面"):
    im = _load(data_url)
    w, h = im.size
    scale = min(1.0, MAX_SIDE / max(w, h))
    if scale < 1.0:
        im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
    gray = im.convert("L")

    stat = ImageStat.Stat(gray)
    brightness = stat.mean[0]
    contrast = stat.stddev[0]
    sharpness = _laplacian_var(gray)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_density = ImageStat.Stat(edges).mean[0] / 255.0

    # 中心区域 vs 四角：粗略判断主体是否居中/是否拍到猫
    gw, gh = gray.size
    cx0, cx1 = int(gw * 0.25), int(gw * 0.75)
    cy0, cy1 = int(gh * 0.2), int(gh * 0.8)
    center = gray.crop((cx0, cy0, cx1, cy1))
    center_edges = ImageStat.Stat(center.filter(ImageFilter.FIND_EDGES)).mean[0] / 255.0
    subject_ratio = round(min(1.0, center_edges / 0.18), 2)

    # 主色
    small = im.resize((80, 80))
    q = small.quantize(colors=5, method=Image.Quantize.MEDIANCUT)
    pal = q.getpalette()
    counts = sorted(q.getcolors(), reverse=True)
    total = sum(c for c, _ in counts) or 1
    colors = []
    for cnt, idx in counts[:4]:
        rgb = tuple(pal[idx * 3: idx * 3 + 3])
        colors.append({"hex": "#%02X%02X%02X" % rgb, "pct": round(cnt / total * 100)})
    main_rgb = tuple(int(colors[0]["hex"][i:i + 2], 16) for i in (1, 3, 5))

    score = 100
    tips = []
    if sharpness < 40:
        score -= 30
        tips.append("画面偏糊，尤其是眼睛和毛发边缘——把手机拿稳、对焦点在猫脸上再拍一张。")
    elif sharpness < 90:
        score -= 12
        tips.append("清晰度一般，逆光或手抖会糊，尽量在自然光下拍。")
    if brightness < 55:
        score -= 20
        tips.append("偏暗：色素、结痂、黄疸这些细节在暗光下看不出来，白天靠近窗户拍。")
    elif brightness > 215:
        score -= 15
        tips.append("过曝：白色猫容易被拍成一片白，降低曝光补偿 -1EV 再拍。")
    if contrast < 18:
        score -= 15
        tips.append("对比度低，画面发灰，可能没对准主体。")
    if subject_ratio < 0.35:
        score -= 18
        tips.append("猫在画面里占得太小，细节不足；靠近一点，让头部或身体占满画面 1/2。")
    if edge_density < 0.03:
        score -= 20
        tips.append("几乎看不到边缘细节，可能拍到了墙面/地板，确认猫在取景框里。")

    score = max(10, min(100, score))
    grade = "优秀" if score >= 82 else ("可用" if score >= 62 else "建议重拍")

    return {
        "role": role,
        "width": w, "height": h,
        "brightness": round(brightness), "contrast": round(contrast),
        "sharpness": round(sharpness, 1), "edge_density": round(edge_density, 3),
        "subject_ratio": subject_ratio,
        "colors": colors, "color_label": _color_label(main_rgb),
        "score": score, "grade": grade, "tips": tips,
    }


def analyze(photos):
    """photos: [{data_url, role}]"""
    if not PIL_OK:
        return {"photos": [], "overall": None, "available": False,
                "reason": "未安装 Pillow / numpy，已跳过照片质检（不影响报告生成）"}
    results = []
    for p in photos[:4]:
        try:
            results.append(analyze_one(p["data_url"], p.get("role", "侧面")))
        except Exception as e:  # noqa: BLE001
            results.append({"role": p.get("role"), "error": str(e), "score": 0, "grade": "无法解析", "tips": ["这张图读不出来，换一张 JPG/PNG 试试。"]})
    if not results:
        return {"photos": [], "overall": None, "available": False}
    scores = [r.get("score", 0) for r in results]
    best = max(results, key=lambda r: r.get("score", 0))
    return {
        "photos": results,
        "overall": {
            "count": len(results),
            "avg_score": round(sum(scores) / len(scores)),
            "best": best.get("role"),
            "color_label": best.get("color_label"),
            "ready": max(scores) >= 62,
        },
        "available": True,
    }


def vlm_config(overrides=None):
    cfg = {
        "base_url": os.environ.get("VISION_API_BASE", "https://api.openai.com/v1"),
        "api_key": os.environ.get("VISION_API_KEY", ""),
        "model": os.environ.get("VISION_MODEL", "gpt-4o-mini"),
        "enabled": os.environ.get("VISION_ENABLED", "auto"),
    }
    for k, v in (overrides or {}).items():
        if v:
            cfg[k] = v
    return cfg


def call_vlm(photos, profile, overrides=None):
    cfg = vlm_config(overrides)
    key = (cfg.get("api_key") or "").strip()
    if not key:
        return {"ok": False, "reason": "未配置视觉模型 API Key"}

    content = [{
        "type": "text",
        "text": (
            f"猫咪档案：品种={profile.get('breed_zh', '未知')}，年龄={profile.get('age_months', '?')}月，"
            f"体重={profile.get('weight_kg', '?')}kg，BCS={profile.get('bcs', '?')}/9，"
            f"绝育={'是' if profile.get('neutered') else '否'}。\n"
            "请只根据图片可见内容填写 JSON。看不清就写“无法判断”。"
        ),
    }]
    for p in photos[:4]:
        content.append({"type": "image_url", "image_url": {"url": p["data_url"], "detail": "low"}})

    body = json.dumps({
        "model": cfg["model"],
        "temperature": 0.1,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": VLM_SYSTEM},
            {"role": "user", "content": content},
        ],
    }).encode()

    req = urllib.request.Request(
        cfg["base_url"].rstrip("/") + "/chat/completions",
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        text = data["choices"][0]["message"]["content"].strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            text = text[4:] if text.lower().startswith("json") else text
        parsed = json.loads(text)
        return {"ok": True, "result": parsed, "model": cfg["model"]}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        return {"ok": False, "reason": f"接口返回 {e.code}：{detail}"}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "reason": f"调用失败：{type(e).__name__} {e}"}
