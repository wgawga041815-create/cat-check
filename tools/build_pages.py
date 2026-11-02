#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 web/ + engine/ 组装成可直接由 GitHub Pages 托管的静态站点（输出到 docs/）。

用法： python3 tools/build_pages.py
"""
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs"

def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir()
    for item in (ROOT / "web").iterdir():
        if item.name.startswith("."):
            continue
        shutil.copytree(item, OUT / item.name) if item.is_dir() else shutil.copy2(item, OUT / item.name)
    shutil.copytree(ROOT / "engine", OUT / "engine",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (OUT / "mode.js").write_text(
        "/* GitHub Pages 静态版：由 tools/build_pages.py 生成 */\nwindow.__STATIC_MODE__ = true;\n",
        encoding="utf-8")
    (OUT / ".nojekyll").write_text("", encoding="utf-8")
    files = sum(1 for _ in OUT.rglob("*") if _.is_file())
    print(f"docs/ 已生成：{files} 个文件")
    for p in sorted(OUT.iterdir()):
        print("  ", p.name)

if __name__ == "__main__":
    main()
