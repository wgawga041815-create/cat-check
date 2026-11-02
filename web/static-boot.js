/* 猫况 CatCheck —— 静态版（GitHub Pages）启动器
 *
 * 在浏览器里用 Pyodide 运行与服务器完全相同的 engine/*.py，
 * 并把 /api/* 请求改为本地调用。数据不出设备。
 */
(function () {
  if (!window.__STATIC_MODE__) return;

  const PYODIDE_VERSION = "v0.29.5";
  // 依次尝试：jsDelivr → Fastly 镜像 → unpkg → npmmirror（国内可达）
  const PYODIDE_BASES = [
    `https://cdn.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`,
    `https://fastly.jsdelivr.net/pyodide/${PYODIDE_VERSION}/full/`,
    "https://unpkg.com/pyodide@0.29.5/",
    "https://registry.npmmirror.com/pyodide/0.29.5/files/",
  ];
  const ENGINE_FILES = [
    "__init__.py", "breeds.py", "observations.py", "triage.py",
    "nutrition.py", "litter.py", "care.py", "report.py", "schema.py", "vision.py",
  ];

  // ---------------------------------------------------------------- 加载遮罩
  const overlay = document.createElement("div");
  overlay.className = "boot-overlay";
  overlay.innerHTML = `
    <div class="boot-card">
      <div class="boot-paw">🐈</div>
      <b>正在唤醒本地引擎</b>
      <p id="bootMsg">首次加载约 10MB，之后走浏览器缓存</p>
      <div class="boot-bar"><i id="bootBar"></i></div>
    </div>`;
  document.documentElement.appendChild(overlay);

  const msg = (t) => { const el = document.getElementById("bootMsg"); if (el) el.textContent = t; };
  const bar = (p) => { const el = document.getElementById("bootBar"); if (el) el.style.width = `${p}%`; };

  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error("无法从 CDN 加载 Pyodide，请检查网络后刷新"));
      document.head.appendChild(s);
    });
  }

  // ---------------------------------------------------------------- 启动 Python
  let pyReady = null;
  function bootPy() {
    if (pyReady) return pyReady;
    pyReady = (async () => {
      msg("下载 Python 运行时…");
      bar(15);
      let py = null, lastErr = null;
      for (const base of PYODIDE_BASES) {
        try {
          await loadScript(base + "pyodide.js");
          py = await loadPyodide({ indexURL: base });
          break;
        } catch (e) {
          lastErr = e;
        }
      }
      if (!py) throw lastErr || new Error("Python 运行时加载失败");
      bar(65);
      msg("装载猫况引擎…");
      py.FS.mkdirTree("/engine");
      for (let i = 0; i < ENGINE_FILES.length; i++) {
        const name = ENGINE_FILES[i];
        const res = await fetch(new URL(`engine/${name}`, location.href).href);
        if (!res.ok) throw new Error(`engine/${name} 读取失败 (${res.status})`);
        py.FS.writeFile(`/engine/${name}`, await res.text());
      }
      bar(85);
      py.runPython(`
import sys, json
sys.path.insert(0, "/")
from engine.report import build_report, DISCLAIMER
from engine.schema import build_schema

def _schema():
    return json.dumps(build_schema(public=True, static_mode=True), ensure_ascii=False)

def _analyze(payload):
    return json.dumps(build_report(json.loads(payload)), ensure_ascii=False)
`);
      bar(100);
      overlay.remove();
      return py;
    })();
    pyReady.catch((err) => {
      msg(err.message || String(err));
      const card = overlay.querySelector(".boot-card");
      if (card) {
        const btn = document.createElement("button");
        btn.textContent = "重试";
        btn.className = "boot-retry";
        btn.onclick = () => location.reload();
        card.appendChild(btn);
      }
    });
    return pyReady;
  }

  // ---------------------------------------------------------------- 图片质检（JS 版，替代服务端 Pillow）
  function qcImage(dataUrl, role) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        try {
          const scale = Math.min(1, 900 / Math.max(img.width, img.height));
          const w = Math.max(1, Math.round(img.width * scale));
          const h = Math.max(1, Math.round(img.height * scale));
          const cv = document.createElement("canvas");
          cv.width = w; cv.height = h;
          const ctx = cv.getContext("2d", { willReadFrequently: true });
          ctx.drawImage(img, 0, 0, w, h);
          const d = ctx.getImageData(0, 0, w, h).data;

          const gray = new Float32Array(w * h);
          let sum = 0;
          for (let i = 0, p = 0; i < d.length; i += 4, p++) {
            const g = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
            gray[p] = g; sum += g;
          }
          const mean = sum / gray.length;
          let vsum = 0, lapSum = 0, lapSq = 0, edge = 0, edgeN = 0;
          for (let y = 1; y < h - 1; y++) {
            for (let x = 1; x < w - 1; x++) {
              const i = y * w + x;
              const lap = 4 * gray[i] - gray[i - 1] - gray[i + 1] - gray[i - w] - gray[i + w];
              lapSum += lap; lapSq += lap * lap;
              vsum += (gray[i] - mean) ** 2;
              edge += Math.abs(gray[i + 1] - gray[i]) + Math.abs(gray[i + w] - gray[i]);
              edgeN++;
            }
          }
          const n = Math.max(1, w * h);
          const contrast = Math.sqrt(vsum / n);
          const lapVar = lapSq / Math.max(1, edgeN) - (lapSum / Math.max(1, edgeN)) ** 2;
          const edgeDensity = edge / Math.max(1, edgeN) / 255;

          // 中心区域边缘密度（粗略判断主体是否居中）
          let cEdge = 0, cN = 0;
          for (let y = Math.floor(h * 0.2); y < h * 0.8; y++) {
            for (let x = Math.floor(w * 0.25); x < w * 0.75; x++) {
              const i = y * w + x;
              cEdge += Math.abs(gray[i + 1] - gray[i]) + Math.abs(gray[i + w] - gray[i]);
              cN++;
            }
          }
          const subject = Math.min(1, (cEdge / Math.max(1, cN) / 255) / 0.18);

          // 主色
          const buckets = {};
          for (let i = 0; i < d.length; i += 4 * 7) {
            const key = ((d[i] >> 4) << 8) | ((d[i + 1] >> 4) << 4) | (d[i + 2] >> 4);
            const b = buckets[key] || (buckets[key] = { n: 0, r: 0, g: 0, b: 0 });
            b.n++; b.r += d[i]; b.g += d[i + 1]; b.b += d[i + 2];
          }
          const tops = Object.values(buckets).sort((a, b) => b.n - a.n).slice(0, 4);
          const total = tops.reduce((s, x) => s + x.n, 0) || 1;
          const colors = tops.map((x) => ({
            hex: "#" + [x.r / x.n, x.g / x.n, x.b / x.n].map((v) => Math.round(v).toString(16).padStart(2, "0")).join(""),
            pct: Math.round((x.n / total) * 100),
          }));

          let score = 100, tips = [];
          if (lapVar < 40) { score -= 30; tips.push("画面偏糊，尤其是眼睛和毛发边缘——把手机拿稳、对焦点在猫脸上再拍一张。"); }
          else if (lapVar < 90) { score -= 12; tips.push("清晰度一般，逆光或手抖会糊，尽量在自然光下拍。"); }
          if (mean < 55) { score -= 20; tips.push("偏暗：色素、结痂、黄疸这些细节在暗光下看不出来，白天靠近窗户拍。"); }
          else if (mean > 215) { score -= 15; tips.push("过曝：白色猫容易被拍成一片白，降低曝光补偿 -1EV 再拍。"); }
          if (contrast < 18) { score -= 15; tips.push("对比度低，画面发灰，可能没对准主体。"); }
          if (subject < 0.35) { score -= 18; tips.push("猫在画面里占得太小，细节不足；靠近一点，让头部或身体占满画面 1/2。"); }
          if (edgeDensity < 0.03) { score -= 20; tips.push("几乎看不到边缘细节，可能拍到了墙面/地板，确认猫在取景框里。"); }
          score = Math.max(10, Math.min(100, Math.round(score)));

          resolve({
            role, width: img.width, height: img.height,
            brightness: Math.round(mean), contrast: Math.round(contrast),
            sharpness: Math.round(lapVar * 10) / 10,
            edge_density: Math.round(edgeDensity * 1000) / 1000,
            subject_ratio: Math.round(subject * 100) / 100,
            colors, color_label: colorLabel(colors[0].hex),
            score, grade: score >= 82 ? "优秀" : score >= 62 ? "可用" : "建议重拍",
            tips,
          });
        } catch (e) {
          resolve({ role, score: 0, grade: "无法解析", tips: ["这张图读不出来，换一张 JPG/PNG 试试。"] });
        }
      };
      img.onerror = () => resolve({ role, score: 0, grade: "无法解析", tips: ["这张图读不出来，换一张 JPG/PNG 试试。"] });
      img.src = dataUrl;
    });
  }

  function colorLabel(hex) {
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), v = mx;
    const s = mx === 0 ? 0 : (mx - mn) / mx;
    let h = 0;
    if (mx !== mn) {
      if (mx === r) h = (60 * ((g - b) / (mx - mn)) + 360) % 360;
      else if (mx === g) h = 60 * ((b - r) / (mx - mn)) + 120;
      else h = 60 * ((r - g) / (mx - mn)) + 240;
    }
    if (v < 0.25) return "深色 / 黑色系";
    if (s < 0.12 && v > 0.78) return "白色 / 浅色系";
    if (s < 0.15) return "灰色系";
    if (h >= 15 && h <= 45) return "橘色 / 黄色系";
    if (h > 45 && h <= 75) return "黄褐 / 奶油色系";
    if (h < 15 || h >= 340) return "棕红 / 巧克力色系";
    return "花色 / 混合";
  }

  async function qcAll(photos) {
    const results = [];
    for (const p of photos.slice(0, 4)) results.push(await qcImage(p.data_url, p.role));
    const scores = results.map((r) => r.score || 0);
    const best = results.reduce((a, b) => ((b.score || 0) > (a.score || 0) ? b : a), results[0] || {});
    return {
      photos: results,
      overall: results.length ? {
        count: results.length,
        avg_score: Math.round(scores.reduce((a, b) => a + b, 0) / scores.length),
        best: best.role,
        color_label: best.color_label,
        ready: Math.max(...scores) >= 62,
      } : null,
      available: true,
    };
  }

  // ---------------------------------------------------------------- /api/* 拦截
  const realFetch = window.fetch.bind(window);
  const jsonResponse = (data, status = 200) =>
    new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });

  window.fetch = async function (input, init) {
    const url = typeof input === "string" ? input : (input && input.url) || "";
    let abs = url;
    try { abs = new URL(url, location.href).href; } catch (e) { /* keep raw */ }
    const at = abs.indexOf("/api/");
    if (at < 0) return realFetch(input, init);
    const endpoint = abs.slice(at + 5).split("?")[0];
    let payload = {};
    try { payload = init && init.body ? JSON.parse(init.body) : {}; } catch (e) { /* ignore */ }

    if (endpoint === "schema") {
      const py = await bootPy();
      return jsonResponse(JSON.parse(py.globals.get("_schema")().toString()));
    }
    if (endpoint === "photo-qc") {
      return jsonResponse(await qcAll(payload.photos || []));
    }
    if (endpoint === "analyze") {
      const py = await bootPy();
      const body = { ...payload };
      if (body.photos && body.photos.length) {
        body.photo_qc = await qcAll(body.photos);
        body.photos = [];
      }
      return jsonResponse(JSON.parse(py.globals.get("_analyze")(JSON.stringify(body)).toString()));
    }
    if (endpoint === "vision") {
      return jsonResponse({ ok: false, reason: "静态版在浏览器里运行，没有服务端代理视觉模型；照片只做本地质检。" });
    }
    if (endpoint === "reports") return jsonResponse({ items: [], public: true });
    if (endpoint.startsWith("report/")) return jsonResponse({ error: "静态版不保存报告" }, 404);
    return jsonResponse({ error: "not found" }, 404);
  };

  bootPy().catch(() => { /* 错误已显示在遮罩上 */ });
})();
