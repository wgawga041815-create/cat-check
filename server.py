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
from engine import vision                       # noqa: E402
from engine.observations import OBS, GROUPS     # noqa: E402
from engine.report import build_report, DISCLAIMER   # noqa: E402
from engine.schema import build_schema          # noqa: E402

VERSION = "1.1.0"
BRAND = os.environ.get("BRAND_NAME", "云矿猫砂")
# 公网模式：不落盘、不提供历史报告接口、限制请求频率
PUBLIC = os.environ.get("PUBLIC_MODE", "").lower() in ("1", "true", "yes")

# 简易限流：同一 IP 10 分钟内最多 40 次分析类请求
RATE_WINDOW, RATE_MAX = 600, 40
_RATE = {}
_RATE_LOCK = threading.Lock()


def rate_ok(ip):
    now = time.time()
    with _RATE_LOCK:
        q = _RATE.setdefault(ip, [])
        q[:] = [t for t in q if now - t < RATE_WINDOW]
        if len(q) >= RATE_MAX:
            return False
        q.append(now)
        if len(_RATE) > 5000:                     # 防内存膨胀
            for k in [k for k, v in _RATE.items() if not v][:1000]:
                _RATE.pop(k, None)
        return True
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

def make_report(payload, save=True):
    """组装报告，并按配置落盘。"""
    report = build_report(payload, VERSION, BRAND)
    if save and not payload.get("preview") and not PUBLIC:
        (REPORTS / f"{report['id']}.json").write_text(
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
                return self._send(200, build_schema(VERSION, BRAND, PUBLIC, DISCLAIMER))
            if p.startswith("/api/report/"):
                if PUBLIC:
                    return self._send(404, {"error": "公网演示模式不提供历史报告"})
                rid = re.sub(r"[^0-9a-zA-Z\-]", "", p.rsplit("/", 1)[-1])
                f = REPORTS / f"{rid}.json"
                if not f.is_file():
                    return self._send(404, {"error": "报告不存在"})
                return self._send(200, json.loads(f.read_text(encoding="utf-8")))
            if p == "/api/reports":
                if PUBLIC:
                    return self._send(200, {"items": [], "public": True})
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
        ip = self.headers.get("CF-Connecting-IP") or self.client_address[0]
        if p in ("/api/analyze", "/api/vision", "/api/photo-qc") and not rate_ok(ip):
            return self._send(429, {"error": "请求太频繁了，休息几分钟再试。"})
        try:
            body = self._json_body()
            if p == "/api/analyze":
                report = make_report(body)
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
    print(f"  报告目录   {'（公网模式：不落盘）' if PUBLIC else REPORTS}")
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
