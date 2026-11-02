/* 猫况 CatCheck — 前端应用（无框架） */
(() => {
  "use strict";

  // ---------------------------------------------------------------- 工具
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => Array.from(root.querySelectorAll(s));
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const pct = (v) => `${Math.round(v * 100)}%`;

  const BCS_LABEL = { 1: "极度消瘦", 2: "很瘦", 3: "偏瘦", 4: "略瘦", 5: "理想", 6: "略胖", 7: "超重", 8: "肥胖", 9: "重度肥胖" };
  const LEVEL_TONE = { emergency: "red", urgent: "amber", monitor: "olive", healthy: "green" };

  const DEFAULT_PROFILE = {
    breed_id: "domestic", sex: "male", neutered: true,
    age_months: 36, weight_kg: 4.5, bcs: 5,
    activity: "normal", multicat: 1, flush: "no", budget: "mid", auto_box: "no",
    conditions: [], notes: "",
  };

  const state = {
    schema: null,
    step: 1,
    profile: { ...DEFAULT_PROFILE },
    observations: {},
    prefilled: new Set(),
    photos: [],
    vision: null,
    report: null,
    noPersist: false,
    visionCfg: loadVisionCfg(),
  };

  function loadVisionCfg() {
    try { return JSON.parse(localStorage.getItem("catcheck.vision") || "{}"); } catch { return {}; }
  }
  function saveVisionCfg(cfg) {
    state.visionCfg = cfg;
    localStorage.setItem("catcheck.vision", JSON.stringify(cfg));
  }

  let toastTimer = null;
  function toast(msg) {
    const t = $("#toast");
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }

  // ---------------------------------------------------------------- 启动
  let booted = false;
  async function boot() {
    if (booted) return;
    booted = true;
    restore();
    try {
      const res = await fetch("/api/schema");
      state.schema = await res.json();
    } catch (e) {
      document.body.innerHTML = `<div style="padding:40px;font-family:sans-serif">无法连接本地服务，请确认 <code>python3 server.py</code> 正在运行。<br><br>${esc(e.message)}</div>`;
      return;
    }
    $("#footFine").textContent = `v${state.schema.version} · 由 ${state.schema.brand} 支持 · 推荐逻辑只基于类型与营养参数`;
    renderBreedGrid();
    renderBreedDetail();
    renderProfileControls();
    renderConditions();
    renderObs();
    bindPhotoSlots();
    bindVision();
    renderVisionState();
    bindNav();
    updateSteps();
    if (state.schema.public_mode) {
      $("#historyBtn").hidden = true;
    } else {
      renderHistoryBadge();
    }

    const params = new URLSearchParams(location.search);
    if (params.get("demo")) loadDemo(params.get("demo"));
    else if (params.get("report")) loadReportById(params.get("report"));
    else if (params.get("step") && Number(params.get("step")) <= 3) go(Number(params.get("step")));
  }

  async function loadReportById(id) {
    state.noPersist = true;
    try {
      const rep = await (await fetch(`/api/report/${encodeURIComponent(id)}`)).json();
      if (rep.error) { toast(rep.error); return; }
      state.report = rep;
      state.profile = { ...DEFAULT_PROFILE, ...rep.profile };
      state.observations = Object.fromEntries((rep.triage.picked || []).map((p) => {
        const o = state.schema.observations.find((x) => x.id === p.id);
        const i = o ? o.options.findIndex((x) => x.label === p.answer) : -1;
        return [p.id, i >= 0 ? i : 0];
      }));
      renderBreedGrid(); renderBreedDetail(); renderConditions(); renderObs();
      renderReport(rep);
      go(4);
    } catch { toast("报告加载失败"); }
  }

  function loadDemo(n = "1") {
    state.noPersist = true;
    const presets = {
      "1": {
        profile: { breed_id: "british-shorthair", sex: "male", neutered: true, age_months: 62, weight_kg: 6.8, bcs: 7, activity: "low", multicat: 1, flush: "no", budget: "mid", auto_box: "no", conditions: [], notes: "最近两周喝水明显变多，猫砂盆里的尿团比以前小。" },
        obs: { mood: 1, posture: 0, appetite: 1, water: 2, weight: 1, eyes: 1, nose: 0, mouth: 0, ears: 0, coat: 1, lumps: 0, digest: 0, stool: 1, urine: 2, litterbox: 1, breath: 0, gait: 1, other: 0 },
      },
      "2": {
        profile: { breed_id: "dsh-calico", sex: "female", neutered: false, age_months: 28, weight_kg: 4.2, bcs: 6, activity: "normal", multicat: 1, flush: "no", budget: "mid", auto_box: "no", conditions: [], notes: "发情后一个多月，最近喝水多、精神差，猫砂盆里有淡粉色分泌物。" },
        obs: { mood: 2, posture: 1, appetite: 1, water: 2, weight: 1, eyes: 0, nose: 0, mouth: 0, ears: 0, coat: 1, lumps: 0, digest: 0, stool: 0, urine: 1, litterbox: 0, breath: 0, gait: 0, other: 0 },
      },
      "3": {
        profile: { breed_id: "dsh-lion", sex: "female", neutered: true, age_months: 44, weight_kg: 5.6, bcs: 6, activity: "low", multicat: 2, flush: "no", budget: "mid", auto_box: "no", conditions: [], notes: "一周吐了两次毛球，便便里能看到毛。" },
        obs: { mood: 0, posture: 0, appetite: 1, water: 0, weight: 0, eyes: 1, nose: 0, mouth: 0, ears: 0, coat: 1, lumps: 0, digest: 1, stool: 1, urine: 0, litterbox: 0, breath: 0, gait: 0, other: 0 },
      },
    };
    const preset = presets[n] || presets["1"];
    state.profile = { ...DEFAULT_PROFILE, ...preset.profile };
    state.observations = preset.obs;
    renderBreedGrid();
    renderBreedDetail();
    renderConditions();
    syncSegs();
    renderObs();
    analyze();
  }

  // ---------------------------------------------------------------- 导航
  function go(step) {
    if (step === 4 && !state.report) return;
    state.step = step;
    $$(".view").forEach((v) => { v.hidden = Number(v.id.replace("view-", "")) !== step; });
    updateSteps();
    window.scrollTo({ top: 0, behavior: "smooth" });
    persist();
  }

  function updateSteps() {
    $$(".step").forEach((b) => {
      const n = Number(b.dataset.go);
      b.classList.toggle("active", n === state.step);
      b.classList.toggle("done", n < state.step);
    });
  }

  function bindNav() {
    document.addEventListener("click", (e) => {
      const goBtn = e.target.closest("[data-go]");
      if (goBtn) { e.preventDefault(); go(Number(goBtn.dataset.go)); }
    });
    $("#brandHome").addEventListener("click", (e) => { e.preventDefault(); go(1); });
    $("#resetBtn").addEventListener("click", () => {
      if (!confirm("清空当前填写的内容？历史报告不会被删除。")) return;
      state.profile = { ...DEFAULT_PROFILE };
      state.observations = {};
      state.prefilled.clear();
      state.photos = [];
      state.vision = null;
      state.report = null;
      localStorage.removeItem("catcheck.state");
      location.reload();
    });
    $("#historyBtn").addEventListener("click", openHistory);
    $("#allNormalBtn").addEventListener("click", () => {
      state.schema.observations.forEach((o) => { state.observations[o.id] = 0; });
      state.prefilled.clear();
      renderObs();
      toast("已全部标记为正常");
    });
    $("#analyzeBtn").addEventListener("click", analyze);
  }

  // ---------------------------------------------------------------- 档案
  function renderBreedGrid(q = "") {
    const grid = $("#breedGrid");
    const list = state.schema.breeds.filter((b) => {
      if (!q) return true;
      const hay = (b.zh + " " + b.en + " " + (b.color || "") + " " + b.alias.join(" ")).toLowerCase();
      return hay.includes(q.toLowerCase());
    });
    const groups = [
      { id: "tianyuan", label: "中华田园猫 · 按毛色" },
      { id: "purebred", label: "品种猫" },
    ];
    const card = (b) => `
      <button class="breed-card ${state.profile.breed_id === b.id ? "on" : ""}" data-breed="${b.id}">
        <b>${esc(b.zh)}</b>
        <span>${esc(b.group === "tianyuan" ? (b.color || b.en) : b.en)} · ${esc(b.size_label)}${esc(b.coat_label)}</span>
      </button>`;
    let html = "";
    for (const g of groups) {
      const items = list.filter((b) => (b.group || "purebred") === g.id);
      if (!items.length) continue;
      html += `<div class="breed-group-label">${esc(g.label)}<span>${items.length}</span></div>`;
      html += items.map(card).join("");
    }
    grid.innerHTML = html || `<p class="empty-note" style="grid-column:1/-1">没有匹配的品种，试试“三花”“橘”或直接选「田园混血」。</p>`;
    $$(".breed-card", grid).forEach((btn) => {
      btn.addEventListener("click", () => {
        state.profile.breed_id = btn.dataset.breed;
        renderBreedGrid($("#breedSearch").value);
        renderBreedDetail();
        persist();
      });
    });
  }

  function renderBreedDetail() {
    const b = state.schema.breeds.find((x) => x.id === state.profile.breed_id);
    const box = $("#breedDetail");
    if (!b) { box.innerHTML = `<p class="empty-note">选择左侧品种，查看它的遗传易感与喂养要点。</p>`; return; }
    box.innerHTML = `
      <div class="bd-title"><h3>${esc(b.zh)}</h3><span>${esc(b.en)}</span></div>
      <div class="bd-meta">
        ${b.color ? `<span class="pill">毛色：${esc(b.color)}</span>` : ""}
        ${b.sex_note ? `<span class="pill olive">${esc(b.sex_note)}</span>` : ""}
        <span class="pill">${esc(b.size_label)} · ${esc(b.coat_label)}</span>
        <span class="pill">成年 ${b.weight[0]}–${b.weight[1]} kg</span>
        <span class="pill">寿命 ${b.life[0]}–${b.life[1]} 年</span>
      </div>
      <p style="font-size:12.5px;color:var(--ink-2);margin:0">${esc(b.temper)}</p>
      ${b.genetics?.length ? `<div class="bd-block"><h4>毛色与遗传</h4><ul>${b.genetics.map((g) => `<li>${esc(g)}</li>`).join("")}</ul></div>` : ""}
      <div class="bd-block"><h4>遗传 / 易感问题</h4><ul>
        ${b.predis.map((p) => `<li><span class="risk ${esc(p.risk)}">${esc(p.risk)}</span>${esc(p.name)}${p.note ? ` — <span style="color:var(--ink-3)">${esc(p.note)}</span>` : ""}</li>`).join("")}
      </ul></div>
      <div class="bd-block"><h4>饮食要点</h4><ul>${b.diet.map((d) => `<li>${esc(d)}</li>`).join("")}</ul></div>
      <div class="bd-block"><h4>猫砂 / 盆具</h4><ul>${b.litter.map((d) => `<li>${esc(d)}</li>`).join("")}</ul></div>
      <div class="bd-block"><h4>日常护理</h4><ul><li>${esc(b.groom)}</li></ul></div>
      ${b.note ? `<p style="font-size:12px;color:var(--clay);margin:14px 0 0">💡 ${esc(b.note)}</p>` : ""}
    `;
  }

  function renderProfileControls() {
    $("#breedSearch").addEventListener("input", (e) => renderBreedGrid(e.target.value));

    $$(".seg[data-field]").forEach((seg) => {
      const field = seg.dataset.field;
      $$("button", seg).forEach((btn) => {
        btn.addEventListener("click", () => {
          let val = btn.dataset.val;
          if (field === "neutered") val = val === "true";
          if (field !== "ageUnit") state.profile[field] = val;
          $$("button", seg).forEach((x) => x.classList.toggle("on", x === btn));
          if (field === "ageUnit") syncAge();   // 只改显示单位，实际月龄不变
          persist();
        });
      });
    });
    syncSegs();

    $("#ageInput").addEventListener("input", () => {
      const unit = $(".seg[data-field=ageUnit] button.on")?.dataset.val || "years";
      const v = Number($("#ageInput").value) || 0;
      state.profile.age_months = clamp(Math.round(v * (unit === "years" ? 12 : 1)), 0, 360);
      persist();
    });

    const weight = $("#weightRange");
    weight.addEventListener("input", () => {
      state.profile.weight_kg = Number(weight.value);
      $("#weightVal").textContent = `${weight.value} kg`;
      weight.style.setProperty("--pct", `${((weight.value - 1) / 11) * 100}%`);
      persist();
    });
    weight.dispatchEvent(new Event("input"));

    const track = $("#bcsTrack");
    track.innerHTML = Object.entries(BCS_LABEL).map(([n, label]) =>
      `<button class="bcs-cell ${Number(n) === state.profile.bcs ? "on" : ""}" data-bcs="${n}"><b>${n}</b><span>${label}</span></button>`
    ).join("");
    $$(".bcs-cell", track).forEach((btn) => btn.addEventListener("click", () => {
      state.profile.bcs = Number(btn.dataset.bcs);
      $$(".bcs-cell", track).forEach((x) => x.classList.toggle("on", x === btn));
      $("#bcsVal").textContent = `${state.profile.bcs} / 9 · ${BCS_LABEL[state.profile.bcs]}`;
      persist();
    }));
    $("#bcsVal").textContent = `${state.profile.bcs} / 9 · ${BCS_LABEL[state.profile.bcs]}`;

    $$(".stepper[data-field=multicat] button").forEach((btn) => btn.addEventListener("click", () => {
      state.profile.multicat = clamp(state.profile.multicat + Number(btn.dataset.d), 1, 8);
      $("#multicatVal").textContent = state.profile.multicat;
      persist();
    }));
    $("#multicatVal").textContent = state.profile.multicat;
  }

  function syncSegs() {
    $$(".seg[data-field]").forEach((seg) => {
      const field = seg.dataset.field;
      let cur = state.profile[field];
      if (field === "neutered") cur = String(state.profile.neutered);
      if (field === "ageUnit") cur = state.profile.age_months < 12 ? "months" : "years";
      $$("button", seg).forEach((b) => b.classList.toggle("on", b.dataset.val === String(cur)));
    });
    syncAge();
  }

  function syncAge() {
    const unit = $(".seg[data-field=ageUnit] button.on")?.dataset.val || "years";
    const m = state.profile.age_months;
    $("#ageInput").value = unit === "years" ? Math.round(m / 12 * 10) / 10 : m;
  }

  function renderConditions() {
    const wrap = $("#conditionChips");
    wrap.innerHTML = state.schema.conditions.map((c) =>
      `<button class="chip ${state.profile.conditions.includes(c.id) ? "on" : ""}" data-cond="${c.id}" title="${esc(c.hint)}">${esc(c.zh)}</button>`
    ).join("");
    $$(".chip", wrap).forEach((btn) => btn.addEventListener("click", () => {
      const id = btn.dataset.cond;
      const i = state.profile.conditions.indexOf(id);
      if (i >= 0) state.profile.conditions.splice(i, 1); else state.profile.conditions.push(id);
      btn.classList.toggle("on");
      persist();
    }));
  }

  // ---------------------------------------------------------------- 观察
  function renderObs() {
    const host = $("#obsGroups");
    const obs = state.schema.observations;
    host.innerHTML = state.schema.groups.map((g) => {
      const items = obs.filter((o) => o.group === g.id);
      return `
      <section class="obs-group" data-group="${g.id}">
        <div class="obs-group-head">
          <svg><use href="#i-${g.icon}"/></svg><h3>${esc(g.zh)}</h3>
          <button class="link-btn set-normal" data-normal="${g.id}">本组全部正常</button>
        </div>
        ${items.map((o) => `
          <div class="obs-item">
            <div class="obs-q"><b>${esc(o.label)}</b><span>${esc(o.help)}</span></div>
            <div class="obs-opts">
              ${o.options.map((opt, i) => {
                const sel = state.observations[o.id] === i;
                const cls = opt.sev === 3 ? "flag" : opt.sev === 2 ? "warn" : "";
                const ai = state.prefilled.has(o.id) && sel ? `<span class="opt-prefill">AI</span>` : "";
                return `<button class="opt ${cls} ${sel ? "on" : ""}" data-obs="${o.id}" data-i="${i}">${esc(opt.label)}${ai}</button>`;
              }).join("")}
            </div>
          </div>`).join("")}
      </section>`;
    }).join("");

    $$(".opt").forEach((btn) => btn.addEventListener("click", () => {
      state.observations[btn.dataset.obs] = Number(btn.dataset.i);
      const item = btn.closest(".obs-item");
      $$(".opt", item).forEach((x) => x.classList.toggle("on", x === btn));
      updateObsProgress();
      persist();
    }));
    $$("[data-normal]").forEach((btn) => btn.addEventListener("click", () => {
      const gid = btn.dataset.normal;
      state.schema.observations.filter((o) => o.group === gid).forEach((o) => { state.observations[o.id] = 0; });
      renderObs();
      updateObsProgress();
      persist();
    }));
    updateObsProgress();
  }

  function updateObsProgress() {
    const total = state.schema.observations.length;
    const done = Object.keys(state.observations).filter((k) => state.observations[k] != null).length;
    $("#obsCount").textContent = `${done} / ${total}`;
    $("#obsBar").style.setProperty("--p", pct(done / total));
  }

  // ---------------------------------------------------------------- 照片
  function bindPhotoSlots() {
    $$(".photo-slot").forEach((slot) => {
      const input = $("input[type=file]", slot);
      const role = slot.dataset.role;
      slot.addEventListener("click", (e) => {
        if (e.target.classList.contains("slot-clear")) return;
        input.click();
      });
      input.addEventListener("change", async () => {
        const file = input.files?.[0];
        if (!file) return;
        try {
          const dataUrl = await compress(file);
          state.photos = state.photos.filter((p) => p.role !== role);
          state.photos.push({ role, dataUrl });
          paintSlot(slot, role, dataUrl);
          runQC();
        } catch (err) { toast("这张图片读不出来，换一张试试"); }
        input.value = "";
      });
    });
  }

  function paintSlot(slot, role, dataUrl) {
    slot.classList.add("filled");
    slot.innerHTML = `
      <img src="${dataUrl}" alt="${esc(role)}">
      <button class="slot-clear" type="button" title="移除">×</button>
      <span class="slot-badge">${esc(role)}</span>`;
    $(".slot-clear", slot).addEventListener("click", (e) => {
      e.stopPropagation();
      state.photos = state.photos.filter((p) => p.role !== role);
      slot.classList.remove("filled");
      slot.innerHTML = `<input type="file" accept="image/*" hidden><div class="slot-inner"><svg class="slot-icon"><use href="#i-cam"/></svg><b>${esc(role)}</b><span>${role === "正脸" ? "看眼睛、鼻子、耳朵" : role === "侧身" ? "看体况与呼吸起伏" : "看姿势、步态、被毛"}</span></div>`;
      bindPhotoSlots();
      runQC();
    });
  }

  function compress(file, maxSide = 1280, quality = 0.86) {
    return new Promise((resolve, reject) => {
      const url = URL.createObjectURL(file);
      const img = new Image();
      img.onload = () => {
        const scale = Math.min(1, maxSide / Math.max(img.width, img.height));
        const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
        const c = document.createElement("canvas");
        c.width = w; c.height = h;
        c.getContext("2d").drawImage(img, 0, 0, w, h);
        URL.revokeObjectURL(url);
        resolve(c.toDataURL("image/jpeg", quality));
      };
      img.onerror = () => { URL.revokeObjectURL(url); reject(new Error("decode failed")); };
      img.src = url;
    });
  }

  let qcTimer = null;
  function runQC() {
    clearTimeout(qcTimer);
    qcTimer = setTimeout(async () => {
      const panel = $("#qcPanel");
      if (!state.photos.length) { panel.hidden = true; return; }
      panel.hidden = false;
      panel.innerHTML = `<div class="qc-card skeleton" style="height:120px"></div>`;
      try {
        const res = await fetch("/api/photo-qc", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ photos: state.photos }),
        });
        const qc = await res.json();
        panel.innerHTML = (qc.photos || []).map((p) => `
          <div class="qc-card">
            <h4>${esc(p.role)} · 画质 ${p.score ?? 0}</h4>
            <div class="qc-score">${p.score ?? 0}<small>/100 · ${esc(p.grade || "")}</small></div>
            ${p.color_label ? `<p style="margin:6px 0 0;color:var(--ink-3);font-size:11.5px">画面主色：${esc(p.color_label)}　清晰度 ${p.sharpness ?? "–"}</p>` : ""}
            ${p.tips?.length ? `<ul>${p.tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul>` : `<p style="margin:6px 0 0;color:var(--green);font-size:12px">✓ 这张细节够用</p>`}
          </div>`).join("") + (qc.overall ? `<div class="qc-card"><h4>综合</h4><p style="margin:0;font-size:12.5px;color:var(--ink-2)">平均 ${qc.overall.avg_score} 分，${qc.overall.ready ? "可以用于分析" : "建议重拍一张更清晰的"}。主色 ${esc(qc.overall.color_label || "—")}。</p></div>` : "");
      } catch { panel.hidden = true; }
    }, 260);
  }

  // ---------------------------------------------------------------- 视觉模型
  function renderVisionState() {
    const cfg = state.visionCfg;
    const configured = Boolean(cfg.api_key) || state.schema?.vision_configured;
    const btn = $("#visionBtn");
    btn.hidden = !configured;
    $("#visionState").textContent = configured
      ? `已连接 ${cfg.model || state.schema?.vision_model || "视觉模型"}：可把照片里的眼、鼻、耳、被毛情况自动预填到观察量表，再由你核对。`
      : "未配置视觉模型：报告仍会基于品种 + 观察量表生成，照片只做画质与主色分析。";
    $("#visionConfig").hidden = true;
  }

  function bindVision() {
    $("#visionConfigBtn").addEventListener("click", () => {
      const box = $("#visionConfig");
      box.hidden = !box.hidden;
      $("#vBase").value = state.visionCfg.base_url || "";
      $("#vModel").value = state.visionCfg.model || "";
      $("#vKey").value = state.visionCfg.api_key || "";
    });
    ["#vBase", "#vModel", "#vKey"].forEach((sel) => $(sel).addEventListener("change", () => {
      saveVisionCfg({ base_url: $("#vBase").value.trim(), model: $("#vModel").value.trim(), api_key: $("#vKey").value.trim() });
      renderVisionState();
      toast("已保存到本机");
    }));
    $("#visionBtn").addEventListener("click", runVision);
  }

  async function runVision() {
    if (!state.photos.length) { toast("先拍一张照片"); return; }
    const btn = $("#visionBtn");
    btn.disabled = true; btn.textContent = "识别中…";
    try {
      const res = await fetch("/api/vision", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ photos: state.photos, profile: state.profile, config: state.visionCfg }),
      });
      const data = await res.json();
      if (!data.ok) { toast(data.reason || "视觉模型调用失败"); return; }
      state.vision = data.result;
      applyVisionPrefill(data.result);
      toast("已预填观察项，请核对后修改");
    } catch (e) {
      toast("调用失败：" + e.message);
    } finally {
      btn.disabled = false; btn.textContent = "用 AI 预填观察项";
    }
  }

  function applyVisionPrefill(r) {
    const map = r.suggested_observations || {};
    const obsIndex = Object.fromEntries(state.schema.observations.map((o) => [o.id, o]));
    Object.entries(map).forEach(([k, sev]) => {
      const o = obsIndex[k];
      if (!o) return;
      const idx = o.options.findIndex((x) => x.sev === Number(sev));
      if (idx >= 0) { state.observations[k] = idx; state.prefilled.add(k); }
    });
    renderObs();
    go(3);
  }

  // ---------------------------------------------------------------- 分析
  async function analyze() {
    const isDemo = Boolean(new URLSearchParams(location.search).get("demo"));
    const btn = $("#analyzeBtn");
    btn.disabled = true;
    btn.innerHTML = `分析中…`;
    const payload = {
      profile: { ...state.profile },
      observations: state.observations,
      photos: state.photos,
      vision: state.vision,
      preview: isDemo,
    };
    try {
      const res = await fetch("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error((await res.json()).error || res.statusText);
      state.report = await res.json();
      renderReport(state.report);
      go(4);
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = `生成报告 <svg><use href="#i-arrow"/></svg>`;
    }
  }

  // ---------------------------------------------------------------- 报告
  function renderReport(r) {
    const t = r.triage, n = r.nutrition, l = r.litter, c = r.care;
    const tone = LEVEL_TONE[t.level] || "olive";
    const p = r.profile;
    const breed = r.breed;

    const metaBits = [
      breed ? esc(breed.zh) : "品种未选",
      p.sex === "male" ? "公猫" : "母猫",
      p.neutered ? "已绝育" : "未绝育",
      ageLabel(p.age_months),
      `${p.weight_kg} kg`,
      `BCS ${p.bcs}/9`,
    ];

    const redFlags = (t.red_flags || []).map((f) => `
      <div class="redflag">
        <h3>⚠ ${esc(f.title)}</h3>
        <p>${esc(f.why)}</p>
        <ol>${f.do.map((d) => `<li>${esc(d)}</li>`).join("")}</ol>
      </div>`).join("");

    const diffs = (t.differentials || []).map((d) => `
      <div class="diff">
        <div class="diff-head">
          <h3>${esc(d.name)}</h3>
          <span class="diff-label ${d.confidence >= .7 ? "hi" : d.confidence >= .5 ? "mid" : ""}">${esc(d.label)}</span>
          <div class="conf"><span>相关度</span><div class="conf-bar"><i style="width:${Math.round(d.confidence * 100)}%"></i></div><b>${Math.round(d.confidence * 100)}%</b></div>
        </div>
        ${d.evidence?.length ? `<div class="ev">${d.evidence.map((e) => `<span>${esc(e)}</span>`).join("")}</div>` : ""}
        <p>${esc(d.why)}</p>
        <div class="diff-cols">
          <div><h4>兽医可能做的检查</h4><ul>${d.tests.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
          <div><h4>通常的处理方向</h4><ul>${d.care.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
        </div>
        ${d.drugs?.length ? `<div class="drugs"><b>兽医可能考虑的用药类别</b><span>（只写类别与用途，不含剂量，不可自行购买使用）</span><div class="look">${d.drugs.map((x) => `<span>${esc(x)}</span>`).join("")}</div></div>` : ""}
        ${d.note ? `<div class="diff-note">${esc(d.note)}</div>` : ""}
      </div>`).join("");

    const advisories = (t.breed_advisories || []).map((a) => `
      <div class="advisory lv-${esc(a.level)}">
        <b>${esc(a.title)}</b>
        <p>${esc(a.text)}</p>
      </div>`).join("");

    const breedFocus = (breed?.predis || []).map((x) => `
      <div class="prev"><b>${esc(x.risk)}风险 · ${esc(x.name)}</b><p>${esc(x.note || "该品种常见，建议在日常体检中关注。")}</p></div>`).join("");

    const frange = ([a, b], suffix = "%") => {
      const dec = (!Number.isInteger(a) || !Number.isInteger(b)) && Math.max(a, b) < 10 ? 1 : 0;
      return `${a.toFixed(dec)}–${b.toFixed(dec)}${suffix}`;
    };
    const specRows = [
      ["粗蛋白", frange(n.spec.protein), "干物质基础，动物蛋白为主"],
      ["粗脂肪", frange(n.spec.fat), "过低会影响吸收与被毛"],
      ["磷", frange(n.spec.phosphorus), "肾病猫要严格看这一项"],
      ["钙磷比", n.spec.ca_p, "骨骼与肾脏代谢"],
      ["牛磺酸", n.spec.taurine, "猫自身不能合成，必须添加"],
      ["碳水 NFC", n.spec.carbs, "估算值：100 − 蛋白 − 脂肪 − 灰分 − 水分"],
      ["纤维", Array.isArray(n.spec.fiber) ? frange(n.spec.fiber) : n.spec.fiber, "毛球/减重时上调"],
      ["水分", n.spec.water, ""],
    ];

    const plans = n.plans.map((pl) => `
      <div class="plan">
        <div class="plan-head"><span class="plan-tag">${esc(pl.tag)}</span><h3>${esc(pl.title)}</h3></div>
        <p>${esc(pl.desc)}</p>
        <div class="look">${pl.look.map((x) => `<span>${esc(x)}</span>`).join("")}</div>
        ${pl.watch ? `<div class="watch">注意：${esc(pl.watch)}</div>` : ""}
      </div>`).join("");

    const transition = n.transition.map((s) => `
      <div class="tl-step"><b>${esc(s.day)}</b>
        <div class="tl-mix"><i class="old" style="width:${s.old}"></i><i class="new" style="width:${s.new}"></i></div>
        <small>旧 ${s.old} / 新 ${s.new}</small>
      </div>`).join("");

    const altLitter = l.alternatives.map((a) => `
      <div class="alt"><b>${esc(a.zh)}</b> <span style="color:var(--ink-3);font-size:11px">匹配度 ${Math.round(a.score * 100)}</span>
        <p>${esc(a.why)}　${esc(a.note)}</p></div>`).join("");

    const redLines = c.red_lines.map((d) => `
      <div class="drug"><b>${esc(d.name)}</b><span class="rk ${d.risk === "高" || d.risk === "致命" ? "" : "mid"}">${esc(d.risk)}</span>
        <p>${esc(d.why)}</p></div>`).join("");

    const toxic = c.toxic_food.map((x) => `<div class="drug"><b>${esc(x.name)}</b><p>${esc(x.why)}</p></div>`).join("");

    const costRow = (x) => `<tr><td>${esc(x.item)}</td><td>${esc(x.range)} 元</td></tr>`;
    const costsHalf1 = c.cost_ref.slice(0, Math.ceil(c.cost_ref.length / 2)).map(costRow).join("");
    const costsHalf2 = c.cost_ref.slice(Math.ceil(c.cost_ref.length / 2)).map(costRow).join("");

    const prevent = c.prevention.map((x) => `<div class="prev"><b>${esc(x.t)}</b><p>${esc(x.d)}</p></div>`).join("");

    const careList = c.home_care.map((x) => `<li>${esc(x)}</li>`).join("");

    const vetQs = t.vet_questions.map((q) => `<li>${esc(q)}</li>`).join("");

    const visionCard = state.vision ? `
      <div class="card">
        <div class="vision-summary">
          <h3 style="margin:0 0 6px;font-size:14px">AI 视觉描述 <span class="diff-label">仅描述，不诊断</span></h3>
          <p style="margin:0 0 10px;font-size:13px;color:var(--ink-2)">${esc(state.vision.summary || "—")}</p>
          <div class="look">${["eyes", "nose_mouth", "ears", "coat", "posture"].filter((k) => state.vision[k]?.finding).map((k) => `<span>${esc(labelOf(k))}：${esc(state.vision[k].finding)}</span>`).join("")}</div>
          ${state.vision.limits ? `<p style="margin:10px 0 0;font-size:11.5px;color:var(--ink-3)">局限：${esc(state.vision.limits)}</p>` : ""}
        </div>
      </div>` : "";

    let sn = 0;
    const nx = () => String(++sn).padStart(2, "0");
    const nRed = redFlags ? nx() : null;
    const nDiff = nx();
    const nBreed = breedFocus ? nx() : null;
    const nFood = nx();
    const nLitter = nx();
    const nVet = nx();
    const nCare = nx();

    const photoCard = r.photo_qc?.overall ? `
      <div class="card">
        <h3 style="margin:0 0 10px;font-size:14px">照片质检</h3>
        <div class="kv">
          ${r.photo_qc.photos.map((p) => `<div><span>${esc(p.role)}</span><b>${p.score} 分 · ${esc(p.grade)}</b></div>`).join("")}
          <div><span>画面主色</span><b>${esc(r.photo_qc.overall.color_label || "—")}</b></div>
        </div>
        ${r.photo_qc.overall.ready ? "" : `<p style="margin:10px 0 0;font-size:12px;color:var(--amber)">提示：照片清晰度不足，视觉判断的参考价值有限，报告主要依据观察量表。</p>`}
      </div>` : "";

    $("#reportRoot").innerHTML = `
    <div class="report-head">
      <div class="report-title">
        <h1>${breed ? esc(breed.zh) : "猫咪"} · 状态报告</h1>
        <div class="report-meta">
          <span>No. ${esc(r.id)}</span>
          <span>${esc(r.created_label)}</span>
          ${metaBits.map((m) => `<span>${m}</span>`).join("")}
        </div>
      </div>
      <div class="report-actions">
        <button class="ghost-btn" id="printBtn"><svg style="width:14px;height:14px"><use href="#i-print"/></svg> 打印 / 存 PDF</button>
        <button class="ghost-btn" id="copyBtn">复制就诊卡</button>
        <button class="ghost-btn" id="againBtn">重新评估</button>
      </div>
    </div>

    <div class="verdict tone-${tone}">
      <div class="verdict-top">
        <span class="badge"><span class="pulse"></span>${esc(t.level_short)}</span>
        <span class="verdict-window">${esc(t.window)}</span>
      </div>
      <h2>${esc(t.headline)}</h2>
      <p>${esc(t.summary)}</p>
      <div class="counts">
        <div class="count red"><b>${t.counts.sev3}</b><span>急症级信号</span></div>
        <div class="count amber"><b>${t.counts.sev2}</b><span>需要关注</span></div>
        <div class="count olive"><b>${t.counts.sev1}</b><span>轻微变化</span></div>
        <div class="count green"><b>${t.counts.normal}</b><span>正常项</span></div>
      </div>
    </div>

    ${redFlags ? `<section class="sec"><div class="sec-head"><span class="sec-num">${nRed}</span><h2>需要立刻处理的事</h2><span class="sec-sub">红旗信号优先于一切建议</span></div>${redFlags}</section>` : ""}

    <section class="sec">
      <div class="sec-head"><span class="sec-num">${nDiff}</span><h2>可能的方向</h2><span class="sec-sub">按你提供的信息排序，不是诊断</span></div>
      ${diffs || `<div class="card"><p style="margin:0;color:var(--ink-2);font-size:13px">没有明显的异常组合。保持观察即可，重点看体重、饮水和尿团。</p></div>`}
    </section>

    ${(breedFocus || advisories) ? `<section class="sec"><div class="sec-head"><span class="sec-num">${nBreed}</span><h2>${esc(breed.zh)} 需要额外留意的</h2><span class="sec-sub">毛色 / 品种专属</span></div>
      ${advisories}
      ${breedFocus ? `<div class="prev-grid" style="margin-top:${advisories ? "12px" : "0"}">${breedFocus}</div>` : ""}
    </section>` : ""}

    <section class="sec">
      <div class="sec-head"><span class="sec-num">${nFood}</span><h2>猫粮方案</h2><span class="sec-sub">按体重与状况计算，不是品牌推荐</span></div>
      <div class="card">
        <div class="stat-row">
          <div class="stat"><b>${n.energy.der}<small>kcal/天</small></b><span>每日热量目标</span></div>
          <div class="stat"><b>${n.dry_g}<small>g</small></b><span>若全喂干粮</span></div>
          <div class="stat"><b>${n.cans}<small>罐</small></b><span>若全喂湿粮（85g）</span></div>
          <div class="stat"><b>${n.energy.ideal_weight}<small>kg</small></b><span>理想体重 · ${esc(n.energy.stage)}</span></div>
        </div>
        <p style="font-size:12.5px;color:var(--ink-3);margin:0 0 12px">${esc(n.water_tip)}</p>
        <div class="ev" style="margin-bottom:18px">
          ${(n.conditions || []).map((c) => `<span>已计入：${esc(c.zh)}</span>`).join("")}
          ${(n.suspected || []).map((c) => `<span style="background:var(--amber-soft);color:var(--amber)">待排除：${esc(c.zh)}</span>`).join("")}
        </div>

        <div class="grid-2">
          <div>
            <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">营养规格（对照包装袋看）</h3>
            <table class="spec-table">
              <thead><tr><th>项目</th><th>目标</th><th>说明</th></tr></thead>
              <tbody>${specRows.map(([a, b, cc]) => `<tr><td>${esc(a)}</td><td class="v">${esc(b)}</td><td>${esc(cc)}</td></tr>`).join("")}</tbody>
            </table>
          </div>
          <div>
            <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">每日分餐</h3>
            <div class="kv" style="grid-template-columns:repeat(2,1fr)">
              ${n.schedule.map((s) => `<div><span>${esc(s.meal)}</span><b>${s.kcal} kcal</b></div>`).join("")}
            </div>
            <h3 style="margin:18px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">7 天换粮</h3>
            <div class="timeline">${transition}</div>
            ${n.cautions?.length ? `<div class="diff-note" style="margin-top:16px">${n.cautions.map((x) => esc(x)).join("<br>")}</div>` : ""}
          </div>
        </div>

        <h3 style="margin:24px 0 10px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">三套可选方案</h3>
        ${plans}

        <h3 style="margin:24px 0 10px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">选粮时逐条核对</h3>
        <ol class="checklist">${n.checklist.map((x) => `<li>${esc(x)}</li>`).join("")}</ol>

        <h3 style="margin:22px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">避免</h3>
        <div class="avoid-list">${n.avoid.map((x) => `<span>${esc(x)}</span>`).join("")}</div>
        ${n.suspected?.length ? `<div class="diff-note" style="margin-top:14px">${n.suspected.map((x) => esc(x.hint)).join("<br>")}</div>` : ""}
        ${n.spec_notes?.length ? `<p style="margin:16px 0 0;font-size:12px;color:var(--ink-3)">${n.spec_notes.map(([, note]) => esc(note)).join(" ")}</p>` : ""}
      </div>
    </section>

    <section class="sec">
      <div class="sec-head"><span class="sec-num">${nLitter}</span><h2>猫砂与猫砂盆</h2><span class="sec-sub">按品种特征、健康风险与你的习惯匹配</span></div>
      <div class="card">
        <div class="litter-hero">
          <div class="litter-main">
            <div class="lh">
              <h3>${esc(l.primary.zh)}</h3>
              <div class="score-ring" style="--s:${Math.round(l.primary.score * 100)}">${Math.round(l.primary.score * 100)}</div>
            </div>
            <p class="grain">建议颗粒：${esc(l.primary.grain)}</p>
            <p style="font-size:13px;color:var(--ink-2);margin:8px 0 0">${esc(l.primary.note)}</p>
            <div class="pros-cons">
              <div><h4>适合你的理由</h4><ul>${l.primary.pros.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
              <div><h4>要有心理准备</h4><ul>${l.primary.cons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
            </div>
            ${l.cautions.map((x) => `<div class="diff-note" style="margin-top:12px">${esc(x)}</div>`).join("")}
          </div>
          <div>
            <h3 style="margin:0 0 10px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">备选</h3>
            <div class="alt-list">${altLitter}</div>
            <h3 style="margin:18px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">盆具配置</h3>
            <div class="kv" style="grid-template-columns:repeat(2,1fr)">
              <div><span>数量</span><b>${l.box.count} 个</b></div>
              <div><span>尺寸</span><b>${esc(l.box.size)}</b></div>
              <div><span>入口高度</span><b>${esc(l.box.entry)}</b></div>
              <div><span>砂层厚度</span><b>${esc(l.box.litter_depth)}</b></div>
              <div style="grid-column:1/-1"><span>类型</span><b>${esc(l.box.type)}</b></div>
            </div>
          </div>
        </div>

        <h3 style="margin:24px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">为什么是它</h3>
        <ul class="care-list">${l.reasons.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>

        <div class="grid-2" style="margin-top:20px">
          <div>
            <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">清洁节奏</h3>
            <ul class="sop">${l.sop.map((s) => `<li><span class="t">${esc(s.t)}</span><span>${esc(s.d)}</span></li>`).join("")}</ul>
          </div>
          <div>
            <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">摆盆规则</h3>
            <ul class="care-list">${l.box_rules.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          </div>
        </div>
        ${l.brand ? `<p style="margin:18px 0 0;font-size:11px;color:var(--ink-3);border-top:1px solid var(--line-soft);padding-top:12px">${esc(l.brand)}</p>` : ""}
      </div>
    </section>

    <section class="sec">
      <div class="sec-head"><span class="sec-num">${nVet}</span><h2>就医与用药</h2><span class="sec-sub">先看红线，再看清单</span></div>
      ${visionCard}
      ${photoCard}
      <div class="card" style="margin-top:12px">
        <div class="grid-2">
          <div>
            <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">到诊室要问的问题</h3>
            <ul class="q-list">${vetQs || "<li>暂时没有特别要问的，按常规体检即可。</li>"}</ul>
            <h3 style="margin:20px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">出发前准备</h3>
            <ul class="care-list">${c.vet_prep.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          </div>
          <div>
            <div class="vet-note-bar"><b>就诊沟通卡 · 直接给医生看</b><button class="link-btn" id="copyBtn2">复制</button></div>
            <div class="vet-note">${esc(c.vet_note)}</div>
            <h3 style="margin:18px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">带上这些会更高效</h3>
            <ul class="care-list">${c.transport.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
          </div>
        </div>
        <h3 style="margin:24px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">常见检查费用参考（元）</h3>
        <div class="grid-2">
          <table class="cost-table"><tbody>${costsHalf1}</tbody></table>
          <table class="cost-table"><tbody>${costsHalf2}</tbody></table>
        </div>
        <p style="font-size:10.5px;color:var(--ink-3);margin:8px 0 0">城市与医院等级差异很大，仅作心理准备；急诊与住院费用通常另计。</p>
      </div>

      <details class="fold" style="margin-top:12px">
        <summary>⚠ 用药红线：这些人用药对猫可能致命</summary>
        <div class="fold-body">${redLines}</div>
      </details>
      <details class="fold">
        <summary>🚫 不能喂的食物</summary>
        <div class="fold-body">${toxic}</div>
      </details>
    </section>

    <section class="sec">
      <div class="sec-head"><span class="sec-num">${nCare}</span><h2>在家能做的</h2><span class="sec-sub">以及 ${c.followup_days} 天后的复评点</span></div>
      <div class="grid-2">
        <div class="card">
          <h3 style="margin:0 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">护理要点</h3>
          <ul class="care-list">${careList}</ul>
          <h3 style="margin:20px 0 8px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">${c.followup_days} 天后复评</h3>
          <p style="margin:0;font-size:13px;color:var(--ink-2)">按同样的 18 项再填一次。判断标准很简单：<b>任何一项从 1 变成 2、或从 2 变成 3，就直接去就医</b>，不要再等下一轮。</p>
        </div>
        <div class="card">
          <h3 style="margin:0 0 10px;font-size:13px;letter-spacing:.06em;color:var(--ink-3)">长期预防</h3>
          <div class="prev-grid" style="grid-template-columns:1fr">${prevent}</div>
        </div>
      </div>
    </section>

    <div class="disclaimer"><b>免责声明：</b>${esc(r.disclaimer)}</div>

    <div class="report-foot">
      <span style="font-size:11px;color:var(--ink-3)">报告编号 ${esc(r.id)} · 生成于 ${esc(r.created_label)}</span>
      <button class="primary-btn" id="printBtn2"><svg><use href="#i-print"/></svg> 打印 / 存为 PDF</button>
    </div>
    `;

    $("#printBtn")?.addEventListener("click", () => window.print());
    $("#printBtn2")?.addEventListener("click", () => window.print());
    const copy = async () => {
      try { await navigator.clipboard.writeText(c.vet_note); toast("就诊卡已复制"); }
      catch { toast("复制失败，请手动选择文本"); }
    };
    $("#copyBtn")?.addEventListener("click", copy);
    $("#copyBtn2")?.addEventListener("click", copy);
    $("#againBtn")?.addEventListener("click", () => { state.report = null; go(1); });
  }

  function labelOf(k) { return { eyes: "眼睛", nose_mouth: "口鼻", ears: "耳朵", coat: "被毛", posture: "姿势" }[k] || k; }

  function ageLabel(m) {
    if (!m && m !== 0) return "年龄未填";
    if (m < 12) return `${m} 月龄`;
    const y = Math.floor(m / 12), r = m % 12;
    return r ? `${y} 岁 ${r} 个月` : `${y} 岁`;
  }

  // ---------------------------------------------------------------- 历史
  async function openHistory() {
    const drawer = $("#historyDrawer");
    drawer.hidden = false;
    const list = $("#historyList");
    list.innerHTML = `<p class="empty-note">加载中…</p>`;
    try {
      const data = await (await fetch("/api/reports")).json();
      if (!data.items.length) { list.innerHTML = `<p class="empty-note">还没有报告。完成一次评估后会自动保存在本机。</p>`; return; }
      const toneColor = { red: "var(--red)", amber: "var(--amber)", olive: "var(--olive)", green: "var(--green)" };
      list.innerHTML = data.items.map((it) => `
        <button class="history-item" data-id="${esc(it.id)}">
          <b><span class="dot-tone" style="background:${toneColor[it.tone] || "var(--ink-3)"}"></span>${esc(it.breed || "猫咪")} · ${esc(it.level)}</b>
          <p>${esc(it.at)}　${esc(it.headline)}</p>
        </button>`).join("");
      $$(".history-item", list).forEach((b) => b.addEventListener("click", async () => {
        const rep = await (await fetch(`/api/report/${b.dataset.id}`)).json();
        state.report = rep;
        state.profile = { ...DEFAULT_PROFILE, ...rep.profile };
        state.observations = Object.fromEntries((rep.triage.picked || []).map((p) => {
          const o = state.schema.observations.find((x) => x.id === p.id);
          const i = o ? o.options.findIndex((x) => x.label === p.answer) : -1;
          return [p.id, i >= 0 ? i : 0];
        }));
        renderReport(rep);
        drawer.hidden = true;
        go(4);
        updateSteps();
      }));
    } catch {
      list.innerHTML = `<p class="empty-note">读取失败。</p>`;
    }
    $$("[data-close]", drawer).forEach((b) => { b.onclick = () => { drawer.hidden = true; }; });
  }

  async function renderHistoryBadge() {
    if (state.schema?.public_mode) return;
    try {
      const data = await (await fetch("/api/reports")).json();
      if (data.items?.length) $("#historyBtn").textContent = `历史报告 · ${data.items.length}`;
    } catch {}
  }

  // ---------------------------------------------------------------- 持久化
  let persistTimer = null;
  function persist() {
    if (state.noPersist) return;
    clearTimeout(persistTimer);
    persistTimer = setTimeout(() => {
      localStorage.setItem("catcheck.state", JSON.stringify({
        profile: state.profile, observations: state.observations, step: state.step < 4 ? state.step : 1,
      }));
    }, 300);
  }

  function restore() {
    try {
      const raw = JSON.parse(localStorage.getItem("catcheck.state") || "null");
      if (!raw) return;
      state.profile = { ...DEFAULT_PROFILE, ...(raw.profile || {}) };
      state.observations = raw.observations || {};
    } catch {}
  }

  // 修正：BCS 控件与分段控件的初始状态依赖 schema 之外的 DOM
  document.addEventListener("DOMContentLoaded", boot);
  if (document.readyState !== "loading") boot();
})();
