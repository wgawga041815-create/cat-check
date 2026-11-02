/* 猫况 CatCheck —— 照片初筛
 *
 * 只做“能看见的事”：毛色比例、花纹对比度、白斑面积。
 * 不做年龄/性别/品种的强行猜测——那需要兽医面诊或专业分类模型。
 *
 * 输出候选品种（中华田园猫按毛色细分）+ 每条候选的依据，由用户点选确认。
 */
(function () {
  "use strict";

  // ---------------------------------------------------------------- 颜色工具
  function rgb2hsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), d = mx - mn;
    let h = 0;
    if (d !== 0) {
      if (mx === r) h = ((g - b) / d) % 6;
      else if (mx === g) h = (b - r) / d + 2;
      else h = (r - g) / d + 4;
      h *= 60;
      if (h < 0) h += 360;
    }
    return [h, mx === 0 ? 0 : d / mx, mx];
  }

  function bucketOf(h, s, v) {
    if (v > 0.80 && s < 0.16) return "white";
    if (v < 0.22) return "black";
    if (s < 0.18) return "gray";
    if (h >= 10 && h <= 48 && s >= 0.30 && v >= 0.30) return "orange";
    if (h >= 15 && h <= 50 && v < 0.42) return "brown";
    if (s < 0.35 && v < 0.55) return "gray";
    return "other";
  }

  // ---------------------------------------------------------------- 核心：像素统计
  function profilePixels(data, width, height) {
    const counts = { white: 0, black: 0, gray: 0, orange: 0, brown: 0, other: 0 };
    let n = 0, vSum = 0, vSq = 0, orangeV = 0, orangeN = 0;

    // 只取画面中部 76%，减少背景占比
    const x0 = Math.floor(width * 0.12), x1 = Math.floor(width * 0.88);
    const y0 = Math.floor(height * 0.12), y1 = Math.floor(height * 0.88);
    const step = Math.max(1, Math.round(Math.min(width, height) / 180));

    for (let y = y0; y < y1; y += step) {
      for (let x = x0; x < x1; x += step) {
        const i = (y * width + x) * 4;
        if (data[i + 3] < 40) continue;
        const [h, s, v] = rgb2hsv(data[i], data[i + 1], data[i + 2]);
        const b = bucketOf(h, s, v);
        counts[b]++;
        if (b === "orange") { orangeV += v; orangeN++; }
        vSum += v; vSq += v * v; n++;
      }
    }
    if (!n) return null;
    const total = n;
    const ratio = (k) => counts[k] / total;
    const mean = vSum / total;
    const sd = Math.sqrt(Math.max(0, vSq / total - mean * mean));

    // 花纹对比度：非黑非白像素的明度标准差，越大越像虎斑
    const furTotal = counts.orange + counts.brown + counts.gray + counts.other;
    const tabby = furTotal > total * 0.15 ? sd : 0;

    return {
      white: +ratio("white").toFixed(3),
      black: +ratio("black").toFixed(3),
      gray: +ratio("gray").toFixed(3),
      orange: +ratio("orange").toFixed(3),
      orange_v: +(orangeN ? orangeV / orangeN : 0).toFixed(3),
      brown: +ratio("brown").toFixed(3),
      other: +ratio("other").toFixed(3),
      brightness: +mean.toFixed(3),
      contrast: +sd.toFixed(3),
      tabby: +tabby.toFixed(3),
      samples: n,
    };
  }

  // ---------------------------------------------------------------- 候选品种
  const pct = (v) => Math.round(v * 100);

  function candidates(p) {
    const out = [];
    const add = (id, score, reason) => out.push({ id, score: Math.max(0, Math.min(99, score)), reason });

    const { white, black, orange, brown, gray, tabby } = p;
    const colored = orange + brown + gray;

    // 三花：黑、橘、白三色同时存在
    if (orange > 0.08 && black > 0.08 && white > 0.10) {
      const tri = Math.min(orange, black, white);
      add("dsh-calico", 58 + tri * 220, `黑 ${pct(black)}%、橘 ${pct(orange)}%、白 ${pct(white)}% 三色并存`);
    }
    // 玳瑁：黑 + 橘，几乎无白
    if (orange > 0.12 && black > 0.12 && white < 0.12) {
      add("dsh-tortie", 55 + Math.min(orange, black) * 160, "黑橘交织、白斑很少");
    }
    // 奶牛：黑白，无橘
    if (black > 0.10 && white > 0.15 && orange < 0.06) {
      add("dsh-cow", 60 + Math.min(black, white) * 140, `黑白两色、无橘色（黑 ${pct(black)}% / 白 ${pct(white)}%）`);
    }
    // 橘猫：橘色占比高且明度亮（暗棕的「橘」多半是虎斑底色）
    if (orange > 0.22 && p.orange_v > 0.58) {
      add("dsh-orange", 50 + orange * 50 + (p.orange_v - 0.5) * 40,
        `橘色占 ${pct(orange)}%，且是明亮的橘（明度 ${pct(p.orange_v)}%）`);
    }
    // 白猫 / 长毛白猫
    if (white > 0.45) {
      add("dsh-white", 52 + white * 55, `白色占 ${pct(white)}%`);
      if (true) {
        add("dsh-lion", 20 + white * 40, "如果它是长毛、有颈部鬃毛，可能是山东狮子猫");
      }
    }
    // 黑猫
    if (black > 0.45) {
      add("dsh-black", 52 + black * 55, `黑色占 ${pct(black)}%`);
    }
    // 狸花 / 棕虎斑：底色偏暗 + 明暗条纹
    if (colored > 0.30 && tabby > 0.09) {
      const brownish = brown + (p.orange_v < 0.60 ? orange : 0);
      add("dsh-tabby", 40 + brownish * 70 + tabby * 90,
        `棕灰底色占 ${pct(colored)}%，明暗反差 ${pct(tabby)}% 像虎斑`);
      add("dsh-jianzhou", brownish * 34, "外形与狸花相近；若有「耳廓褶皱」才考虑简州猫");
    }
    // 灰蓝
    if (gray > 0.45) {
      add("domestic", 35 + gray * 30, `灰/蓝色占 ${pct(gray)}%，系统按通用田园猫处理`);
    }
    // 兜底
    add("domestic", 22, "毛色分布不典型，建议手动确认");

    // 去重保序（同 id 取最高分）
    const best = new Map();
    for (const c of out) {
      const prev = best.get(c.id);
      if (!prev || c.score > prev.score) best.set(c.id, c);
    }
    return [...best.values()].sort((a, b) => b.score - a.score).slice(0, 3);
  }

  // ---------------------------------------------------------------- 图像入口
  function compress(file, maxSide = 900, quality = 0.85) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.round(img.width * scale);
        c.height = Math.round(img.height * scale);
        c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", quality));
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("图片读取失败")); };
      img.src = url;
    });
  }

  function dataUrlToImageData(dataUrl) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const max = 260;
        const scale = Math.min(1, max / Math.max(img.width, img.height));
        const c = document.createElement("canvas");
        c.width = Math.max(1, Math.round(img.width * scale));
        c.height = Math.max(1, Math.round(img.height * scale));
        const ctx = c.getContext("2d", { willReadFrequently: true });
        ctx.drawImage(img, 0, 0, c.width, c.height);
        resolve({ imageData: ctx.getImageData(0, 0, c.width, c.height), width: img.width, height: img.height });
      };
      img.onerror = () => reject(new Error("图片解码失败"));
      img.src = dataUrl;
    });
  }

  async function analyzeDataUrl(dataUrl) {
    const { imageData, width, height } = await dataUrlToImageData(dataUrl);
    const profile = profilePixels(imageData.data, imageData.width, imageData.height);
    if (!profile) throw new Error("这张图里没有可用像素");
    return {
      profile,
      candidates: candidates(profile),
      ratio: { w: width, h: height },
      summary: describe(profile),
    };
  }

  function describe(p) {
    const parts = [];
    if (p.orange) parts.push(`橘 ${pct(p.orange)}%`);
    if (p.black) parts.push(`黑 ${pct(p.black)}%`);
    if (p.white) parts.push(`白 ${pct(p.white)}%`);
    if (p.brown) parts.push(`棕 ${pct(p.brown)}%`);
    if (p.gray) parts.push(`灰 ${pct(p.gray)}%`);
    return parts.join(" · ") || "无法判断";
  }

  // ---------------------------------------------------------------- 可选：视觉模型识别纯种猫
  const VLM_SYS = `你是猫的品种鉴定助手。只输出 JSON，不要解释。格式：
{"breed":"中文品种名（不确定写 未知）","confidence":0.0-1.0,"coat":"你看到的毛色与花纹","note":"一句依据"}
只根据可见外形判断，不要猜年龄性别。看不清就降低 confidence 并写 未知。`;

  function readCfg() {
    try { return JSON.parse(localStorage.getItem("catcheck.vision") || "{}"); } catch (e) { return {}; }
  }

  async function vlmRecognize(dataUrl) {
    const cfg = readCfg();
    if (!cfg.api_key) throw new Error("未配置 API Key");
    const base = (cfg.base_url || "https://api.openai.com/v1").replace(/\/+$/, "");
    const res = await fetch(base + "/chat/completions", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${cfg.api_key}` },
      body: JSON.stringify({
        model: cfg.model || "gpt-4o-mini",
        temperature: 0,
        max_tokens: 300,
        messages: [
          { role: "system", content: VLM_SYS },
          { role: "user", content: [
            { type: "text", text: "识别这只猫的品种。" },
            { type: "image_url", image_url: { url: dataUrl, detail: "low" } },
          ] },
        ],
      }),
    });
    if (!res.ok) throw new Error(`接口返回 ${res.status}`);
    const data = await res.json();
    let text = (data.choices?.[0]?.message?.content || "").trim();
    if (text.startsWith("```")) {
      text = text.split("```")[1] || "";
      text = text.replace(/^json/i, "");
    }
    return JSON.parse(text);
  }

  function aiBlock(host, dataUrl) {
    const cfg = readCfg();
    const box = el("div", "scan-ai");

    if (!cfg.api_key) {
      box.innerHTML = `<p class="scan-hint">英短、布偶这类纯种猫外观相近，仅凭毛色分不出来。在「02 拍照 → 配置模型」填入 API Key 后，这里会出现 AI 识别。</p>`;
      host.appendChild(box);
      return;
    }

    const btn = el("button", "ghost-btn", "用 AI 再认一次（纯种猫更准）");
    box.appendChild(btn);
    host.appendChild(box);

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      btn.textContent = "AI 识别中…";
      try {
        const r = await vlmRecognize(dataUrl);
        const id = matchBreed(r.breed);
        const conf = Math.round((r.confidence || 0) * 100);
        const card = el("button", "scan-cand ai-cand");
        card.innerHTML = `<b>${r.breed || "未知"}${id ? "" : "（未收录，可手动选）"}</b>
          <span class="scan-score">${conf}<small>%</small></span>
          <em>${r.coat || ""}${r.note ? " · " + r.note : ""}</em>`;
        if (id) {
          card.addEventListener("click", () => {
            window.dispatchEvent(new CustomEvent("cat:pick-breed", { detail: { id } }));
            window.dispatchEvent(new CustomEvent("cat:add-photo", { detail: { role: "正脸", dataUrl } }));
            host.querySelectorAll(".scan-cand").forEach((x) => x.classList.remove("picked"));
            card.classList.add("picked");
          });
        } else {
          card.classList.add("disabled");
        }
        box.appendChild(card);
        btn.remove();
      } catch (e) {
        btn.disabled = false;
        btn.textContent = "重试 AI 识别";
        const why = /Failed to fetch|NetworkError/i.test(e.message)
          ? "浏览器直连被拒绝（CORS）。改用本地服务版 python3 server.py 可走代理。"
          : e.message;
        box.appendChild(el("p", "scan-hint", `AI 识别失败：${why}`));
      }
    });
  }

  // ---------------------------------------------------------------- 界面
  function el(tag, cls, html) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (html != null) e.innerHTML = html;
    return e;
  }

  function renderResult(host, res, dataUrl) {
    host.innerHTML = "";
    host.hidden = false;

    const swatches = el("div", "scan-swatches");
    const total = Object.values(res.profile).filter((v) => typeof v === "number" && v <= 1);
    const map = [
      ["white", "#F3EFE6"], ["black", "#24211D"], ["orange", "#D98A43"],
      ["brown", "#8A6440"], ["gray", "#9A9C97"],
    ];
    for (const [k, color] of map) {
      const v = res.profile[k] || 0;
      if (v < 0.03) continue;
      const s = el("span", "swatch");
      s.style.background = color;
      s.style.width = `${Math.max(8, v * 100)}%`;
      s.title = `${k} ${pct(v)}%`;
      swatches.appendChild(s);
    }
    host.appendChild(swatches);

    host.appendChild(el("p", "scan-summary",
      `画面中：${res.summary}${res.profile.tabby > 0.12 ? "，可见明暗花纹" : ""}`));

    const list = el("div", "scan-cands");
    res.candidates.forEach((c, i) => {
      const b = el("button", "scan-cand" + (i === 0 ? " top" : ""));
      b.innerHTML = `<b>${c.id === "domestic" ? "田园混血 / 拿不准" : breedName(c.id)}</b>
        <span class="scan-score">${c.score}<small>分</small></span>
        <em>${c.reason}</em>`;
      b.addEventListener("click", () => {
        window.dispatchEvent(new CustomEvent("cat:pick-breed", { detail: { id: c.id } }));
        host.querySelectorAll(".scan-cand").forEach((x) => x.classList.remove("picked"));
        b.classList.add("picked");
        window.dispatchEvent(new CustomEvent("cat:add-photo", { detail: { role: "正脸", dataUrl } }));
      });
      list.appendChild(b);
    });
    host.appendChild(list);

    host.appendChild(el("p", "scan-hint", "点一个候选就会填入档案，之后随时可以手动改。"));
    aiBlock(host, dataUrl);
  }

  let BREEDS = [];
  let NAME_MAP = new Map();

  function setBreeds(list) {
    if (!Array.isArray(list) || !list.length) return;
    BREEDS = list;
    NAME_MAP = new Map();
    for (const b of list) {
      [b.zh, b.en, ...(b.alias || [])].forEach((n) => {
        if (!n) return;
        NAME_MAP.set(String(n).toLowerCase().replace(/\s+/g, ""), b.id);
      });
    }
  }

  function matchBreed(name) {
    if (!name) return null;
    const key = String(name).toLowerCase().replace(/[\s·\/]/g, "");
    if (NAME_MAP.has(key)) return NAME_MAP.get(key);
    for (const [k, id] of NAME_MAP) {
      if (k.includes(key) || key.includes(k)) return id;
    }
    return null;
  }

  // 品种中文名兜底
  let BREED_NAMES = {
    "dsh-calico": "三花猫", "dsh-tortie": "玳瑁猫", "dsh-cow": "奶牛猫",
    "dsh-orange": "橘猫", "dsh-white": "白猫", "dsh-black": "黑猫（玄猫）",
    "dsh-tabby": "狸花猫", "dsh-lion": "山东狮子猫", "dsh-jianzhou": "简州猫",
    "domestic": "田园混血 / 拿不准",
  };
  function breedName(id) { return BREED_NAMES[id] || id; }


  function wire(host, btn, input) {
    btn.addEventListener("click", () => input.click());
    input.addEventListener("change", async () => {
      const file = input.files && input.files[0];
      input.value = "";
      if (!file) return;
      btn.disabled = true;
      host.hidden = false;
      host.innerHTML = `<div class="scan-loading"><i></i><span>正在看它的毛色…</span></div>`;
      try {
        const dataUrl = await compress(file);
        const res = await analyzeDataUrl(dataUrl);
        renderResult(host, res, dataUrl);
      } catch (e) {
        host.innerHTML = `<p class="scan-error">识别失败：${e.message}</p>`;
      } finally {
        btn.disabled = false;
      }
    });
  }

  async function analyzeAndRender(host, dataUrl) {
    const res = await analyzeDataUrl(dataUrl);
    renderResult(host, res, dataUrl);
    return res;
  }

  window.CatScan = { analyzeDataUrl, analyzeAndRender, profilePixels, candidates, setBreeds, compress };

  document.addEventListener("DOMContentLoaded", () => {
    const host = document.getElementById("scanResult");
    const btn = document.getElementById("scanBtn");
    const input = document.getElementById("scanFile");
    if (host && btn && input) wire(host, btn, input);
  });
})();
