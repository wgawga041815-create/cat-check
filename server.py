#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""猫况 CatCheck —— 本地零依赖服务。

用法：
    python3 server.py            # http://127.0.0.1:8787
    python3 server.py --open     # 启动并自动打开浏览器
    PORT=9000 python3 server.py

可选环境变量（视觉模型）：
    VISION_API_BASE=https://api.openai.com/v1
    VISION_API_KEY=sk-...
    VISION_MODEL=gpt-4o-mini
"""

import argparse
import json
import os
import re
import sys
import threading
import time
import uuid
import webbrowser
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, unquote

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from engine import breeds as breed_db          # noqa: E402
from engine import triage as triage_engine      # noqa: E402
from engine import nutrition as nutrition_engine  # noqa: E402
from engine import litter as litter_engine      # noqa: E402
from engine import care as care_engine          # noqa: E402
from engine import vision                       # noqa: E402
from engine.observations import OBS, GROUPS     # noqa: E402

VERSION = "1.0.0"
BRAND = os.environ.get("BRAND_NAME", "云矿猫砂")
WEB = ROOT / "web"
DATA = ROOT / "data"
REPORTS = DATA / "reports"
REPORTS.mkdir(parents=True, exist_ok=True)

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}

DISCLAIMER = (
    "本工具是家庭观察辅助工具，不是兽医诊断。所有“可能方向”都只是提示，"
    "确诊需要面诊、化验与影像学检查。任何用药（包括人用药、驱虫药、保健品）"
    "都必须由执业兽医决定；出现急症信号请立即就医。"
)


# ------------------------------------------------------------------ 报告生成
def build_report(payload, save=True):
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

    vision_ai = payload.get("vision") or None
    qc = None
    if photos:
        try:
            qc = vision.analyze(photos)
        except Exception as e:  # noqa: BLE001
            qc = {"photos": [], "overall": None, "available": False, "error": str(e)}

    rid = time.strftime("%Y%m%d") + "-" + uuid.uuid4().hex[:6]
    created = datetime.now().astimezone()

    pub_profile = {k: v for k, v in profile.items() if not k.startswith("_")}
    report = {
        "id": rid,
        "created_at": created.isoformat(),
        "created_label": created.strftime("%Y-%m-%d %H:%M"),
        "version": VERSION,
        "brand": BRAND,
        "profile": pub_profile,
        "breed": breed_db.public(breed) if breed else None,
        "notes": notes,
        "photo_qc": qc,
        "vision_ai": vision_ai,
        "triage": triage,
        "nutrition": nutrition,
        "litter": litter,
        "care": care,
        "disclaimer": DISCLAIMER,
    }

    if save and not payload.get("preview"):
        (REPORTS / f"{rid}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return report


# ------------------------------------------------------------------ HTTP 服务
class Handler(BaseHTTPRequestHandler):
    server_version = f"CatCheck/{VERSION}"

    def log_message(self, fmt, *args):  # 静音默认日志，只留错误
        if args and str(args[1]).startswith(("4", "5")):
            sys.stderr.write("[%s] %s\n" % (self.log_date_time_string(), fmt % args))

    # ---------------------------------------------------------- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False)
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _json_body(self, limit=24 * 1024 * 1024):
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        if length > limit:
            raise ValueError("请求体过大")
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _static(self, path):
        rel = unquote(path.lstrip("/")) or "index.html"
        target = (WEB / rel).resolve()
        if not str(target).startswith(str(WEB.resolve())) or not target.is_file():
            return self._send(404, {"error": "not found"})
        ctype = MIME.get(target.suffix.lower(), "application/octet-stream")
        self._send(200, target.read_bytes(), ctype)

    # ---------------------------------------------------------- routes
    def do_GET(self):
        u = urlparse(self.path)
        p = u.path
        try:
            if p in ("/", "/index.html"):
                return self._static("index.html")
            if p == "/api/schema":
                return self._send(200, {
                    "version": VERSION,
                    "brand": BRAND,
                    "breeds": [breed_db.public(b) for b in breed_db.BREEDS],
                    "groups": GROUPS,
                    "observations": OBS,
                    "conditions": nutrition_engine.CONDITIONS,
                    "litter_types": [
                        {"id": t["id"], "zh": t["zh"], "short": t["short"],
                         "grain": t["grain"], "pros": t["pros"], "cons": t["cons"], "note": t["note"]}
                        for t in litter_engine.TYPES
                    ],
                    "levels": triage_engine.LEVELS,
                    "vision_configured": bool(vision.vlm_config()["api_key"]),
                    "vision_model": vision.vlm_config()["model"],
                    "disclaimer": DISCLAIMER,
                })
            if p.startswith("/api/report/"):
                rid = re.sub(r"[^0-9a-zA-Z\-]", "", p.rsplit("/", 1)[-1])
                f = REPORTS / f"{rid}.json"
                if not f.is_file():
                    return self._send(404, {"error": "报告不存在"})
                return self._send(200, json.loads(f.read_text(encoding="utf-8")))
            if p == "/api/reports":
                items = []
                for f in sorted(REPORTS.glob("*.json"), reverse=True)[:30]:
                    try:
                        d = json.loads(f.read_text(encoding="utf-8"))
                        items.append({"id": d["id"], "at": d["created_label"],
                                      "breed": (d.get("breed") or {}).get("zh", ""),
                                      "level": d["triage"]["level_short"],
                                      "tone": d["triage"]["tone"],
                                      "headline": d["triage"]["headline"]})
                    except Exception:  # noqa: BLE001
                        continue
                return self._send(200, {"items": items})
            if p == "/health":
                return self._send(200, {"ok": True, "version": VERSION, "reports": len(list(REPORTS.glob("*.json")))})
            return self._static(p)
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        p = urlparse(self.path).path
        try:
            body = self._json_body()
            if p == "/api/analyze":
                report = build_report(body)
                return self._send(200, report)
            if p == "/api/photo-qc":
                return self._send(200, vision.analyze(body.get("photos") or []))
            if p == "/api/vision":
                profile = body.get("profile") or {}
                breedsel = breed_db.get(profile.get("breed_id", ""))
                if breedsel:
                    profile["breed_zh"] = breedsel["zh"]
                res = vision.call_vlm(body.get("photos") or [], profile, body.get("config"))
                return self._send(200 if res.get("ok") else 200, res)
            if p == "/api/feedback":
                fb = DATA / "feedback.jsonl"
                with fb.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"at": datetime.now().isoformat(), **body}, ensure_ascii=False) + "\n")
                return self._send(200, {"ok": True})
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


def main():
    ap = argparse.ArgumentParser(description="猫况 CatCheck")
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8787)))
    ap.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    ap.add_argument("--open", action="store_true", help="启动后打开浏览器")
    args = ap.parse_args()

    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print("\n  猫况 CatCheck v%s" % VERSION)
    print("  ─────────────────────────────")
    print(f"  服务地址   {url}")
    print(f"  品种库     {len(breed_db.BREEDS)} 个品种")
    print(f"  观察项     {len(OBS)} 项")
    print(f"  视觉模型   {'已配置 · ' + vision.vlm_config()['model'] if vision.vlm_config()['api_key'] else '未配置（使用问卷 + 照片质检）'}")
    print(f"  报告目录   {REPORTS}")
    print("  Ctrl+C 退出\n")

    if args.open:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  已退出。")
        srv.shutdown()


if __name__ == "__main__":
    main()
