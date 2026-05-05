const heatColors = ["", "#1f3552", "#2c6aab", "#4a9bee"];
const phaseShades = ["#4a9bee", "#f0c870", "#8ad08f", "#d8a0e8", "#f08585", "#6cd0d0"];

let dims = [];
let selected = null;
let cycleFilter = "current";
let weeklyVisible = false;
let weeklyText = null;

function escapeHTML(s) {
  return (s || "").toString().replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

function ringSegmented(dim, sz) {
  const r = sz / 2 - 4, cx = sz / 2, cy = sz / 2;
  const total = (dim.phase_activity || []).reduce((a, b) => a + b, 0);
  const phases = dim.phases || [];
  let svg = `<svg width="${sz}" height="${sz}" viewBox="0 0 ${sz} ${sz}">`;
  svg += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="var(--color-border-tertiary)" stroke-width="3"/>`;
  if (total > 0) {
    let acc = 0;
    for (let i = 0; i < phases.length; i++) {
      const v = (dim.phase_activity || [])[i] || 0;
      if (!v) continue;
      const a1 = -Math.PI / 2 + (acc / total) * 2 * Math.PI;
      const a2 = -Math.PI / 2 + ((acc + v) / total) * 2 * Math.PI;
      acc += v;
      const x1 = cx + r * Math.cos(a1), y1 = cy + r * Math.sin(a1);
      const x2 = cx + r * Math.cos(a2), y2 = cy + r * Math.sin(a2);
      const lg = (a2 - a1) > Math.PI ? 1 : 0;
      const color = phaseShades[i % phaseShades.length];
      svg += `<path d="M${x1},${y1} A${r},${r} 0 ${lg} 1 ${x2},${y2}" fill="none" stroke="${color}" stroke-width="4" stroke-linecap="butt"/>`;
    }
  }
  const totalEntries = dim.total_entries || 0;
  const ir = Math.min(r * 0.55, r - 6);
  const fill = Math.min(totalEntries / 15, 1);
  svg += `<circle cx="${cx}" cy="${cy}" r="${ir * fill}" fill="rgba(55,138,221,0.10)"/>`;
  svg += `<text x="${cx}" y="${cy + 1}" text-anchor="middle" dominant-baseline="middle" font-size="13" font-weight="500" fill="var(--color-text-primary)">${totalEntries}</text>`;
  svg += `</svg>`;
  return svg;
}

function phaseDistribution(dim) {
  const phases = dim.phases || [];
  const activity = dim.phase_activity || [];
  const max = Math.max(1, ...activity);
  const primary = dim.primary_phase;
  let h = `<div class="phase-dist">`;
  for (let i = 0; i < phases.length; i++) {
    const v = activity[i] || 0;
    const pct = Math.round((v / max) * 100);
    const isP = i === primary;
    h += `<div class="phase-row">
      <div class="phase-row-name${isP ? ' primary' : ''}">${i+1}. ${escapeHTML(phases[i])}</div>
      <div class="phase-bar-wrap"><div class="phase-bar-fill ${isP ? '' : 'dim'}" style="width:${pct}%;background:${phaseShades[i % phaseShades.length]}"></div></div>
      <div class="phase-row-count">${v}</div>
    </div>`;
  }
  h += `</div>`;
  return h;
}

function weekLabels() { return ["W-4", "W-3", "W-2", "W-1", "本周"]; }

function render() {
  const app = document.getElementById("app");
  if (!dims.length) {
    app.innerHTML = `<div class="empty">还没有任何记录。点击右上角 <b>+ 粘贴</b> 添加第一条。</div>`;
    return;
  }
  if (!selected || !dims.find(x => x.id === selected)) selected = dims[0].id;
  const d = dims.find(x => x.id === selected);

  const totalEntries = dims.reduce((s, x) => s + (x.total_entries || 0), 0);
  const activeDims = dims.filter(x => (x.total_entries || 0) > 0).length;
  const thisWeek = dims.reduce((s, x) => s + (x.heat || []).slice(-7).reduce((a, b) => a + b, 0), 0);

  let h = `<div class="metric-row">
    <div class="metric"><div class="metric-label">Total entries</div><div class="metric-val">${totalEntries}</div></div>
    <div class="metric"><div class="metric-label">Active dimensions</div><div class="metric-val">${activeDims}</div></div>
    <div class="metric"><div class="metric-label">This week activity</div><div class="metric-val">${thisWeek}</div></div>
  </div>`;

  h += `<div class="dims">`;
  for (const dm of dims) {
    const primary = dm.primary_phase;
    const stageName = (dm.phases || [])[primary] || "—";
    const total = dm.phases ? dm.phases.length : 0;
    const autoBadge = dm.created_by === "auto" ? `<div class="dim-badge">auto</div>` : "";
    const cycleBadge = (dm.current_cycle || 1) > 1 ? `<div class="dim-cycle-badge">#${dm.current_cycle}</div>` : "";
    h += `<div class="dim-card${dm.id === selected ? ' active' : ''}" data-id="${escapeHTML(dm.id)}">
      ${autoBadge}${cycleBadge}
      <div class="dim-label">${escapeHTML(dm.label)}</div>
      <div class="dim-stage">主阶段：${escapeHTML(stageName)}</div>
      <div class="dim-ring-row">
        ${ringSegmented(dm, 56)}
        <div class="dim-stats">
          <b>${dm.total_entries || 0}</b> 条记录<br>
          ${total} 阶段 · 周期 ${dm.current_cycle || 1}
        </div>
      </div>
    </div>`;
  }
  h += `</div>`;

  const versionInfo = (d.phase_versions || []).length > 1
    ? ` · 阶段已演化 ${d.phase_versions.length - 1} 次`
    : "";
  h += `<div class="detail">
    <div class="detail-title">${escapeHTML(d.label)}${d.created_by === "auto" ? ' <span class="dim-badge" style="position:static;margin-left:6px">auto</span>' : ""}</div>
    <div class="detail-sub">主阶段：${escapeHTML((d.phases || [])[d.primary_phase] || "—")} · 共 ${d.total_entries || 0} 条记录${versionInfo}</div>
    ${phaseDistribution(d)}`;

  h += `<div class="entries-title"><span>最近进展（${cycleFilter === 'current' ? '当前周期' : '全部'}）</span></div>`;
  if (!(d.entries || []).length) {
    h += `<div class="empty">暂无记录</div>`;
  } else {
    for (const e of d.entries) {
      const phaseName = (d.phases || [])[e.phase_index] || "?";
      h += `<div class="entry">
        <div class="entry-date">${escapeHTML(e.d)}</div>
        <div class="entry-text">${escapeHTML(e.t)}<span class="entry-phase">${escapeHTML(phaseName)}</span>${e.tag ? `<span class="entry-tag">${escapeHTML(e.tag)}</span>` : ""}</div>
      </div>`;
    }
  }
  h += `</div>`;

  h += `<div class="heatmap"><div class="heat-title">活跃度热力图（近 35 天）</div>`;
  h += `<div class="hm-weeks">`;
  const wl = weekLabels();
  for (let i = 0; i < 5; i++) h += `<div class="hm-week" style="width:calc(14px * 7 + 4px * 6);text-align:center">${wl[i]}</div>`;
  h += `</div>`;
  for (const dm of dims) {
    h += `<div class="hm-row"><div class="hm-label" title="${escapeHTML(dm.label)}">${escapeHTML(dm.label)}</div>`;
    const heat = dm.heat || [];
    for (let i = 0; i < 35; i++) {
      const v = heat[i] || 0;
      const lvl = v >= 3 ? 3 : v;
      const bg = lvl > 0 ? heatColors[lvl] : "";
      h += `<div class="hm-cell"${bg ? ` style="background:${bg}"` : ""}></div>`;
    }
    h += `</div>`;
  }
  h += `<div class="hm-legend"><span>Less</span>`;
  for (let i = 0; i <= 3; i++) h += `<div class="hm-cell" style="width:12px;height:12px;${i > 0 ? `background:${heatColors[i]}` : ""}"></div>`;
  h += `<span>More</span></div></div>`;

  if (weeklyVisible) {
    h += `<div class="weekly-section"><h3>最近周报 <button class="bar-link" id="weekly-close">关闭</button></h3>
          <pre>${escapeHTML(weeklyText || "尚未生成。点击右上角『生成周报』。")}</pre></div>`;
  }

  app.innerHTML = h;

  app.querySelectorAll(".dim-card").forEach(card => {
    card.addEventListener("click", () => { selected = card.dataset.id; render(); });
  });
  const wc = document.getElementById("weekly-close");
  if (wc) wc.addEventListener("click", () => { weeklyVisible = false; render(); });
}

async function load() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const j = JSON.parse(await window.pywebview.api.get_dimensions(cycleFilter));
    dims = j.dimensions || [];
    render();
  } catch (e) {
    document.getElementById("app").innerHTML = `<div class="empty">加载失败：${escapeHTML(String(e))}</div>`;
  }
}

document.getElementById("cycle-toggle").addEventListener("click", (e) => {
  const b = e.target.closest("button");
  if (!b) return;
  cycleFilter = b.dataset.v;
  document.querySelectorAll("#cycle-toggle button").forEach(x => x.classList.toggle("on", x === b));
  load();
});

document.getElementById("paste-btn").addEventListener("click", async () => {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    await window.pywebview.api.show_paste();
  } catch (e) {
    alert("打开粘贴窗口失败：" + e);
  }
});

document.getElementById("weekly-btn").addEventListener("click", async () => {
  if (!window.pywebview || !window.pywebview.api) return;
  weeklyVisible = true;
  weeklyText = "生成中…";
  render();
  try {
    const r = JSON.parse(await window.pywebview.api.generate_weekly_report());
    if (r.status === "ok") weeklyText = r.report;
    else weeklyText = "生成失败：" + (r.message || "");
  } catch (e) {
    weeklyText = "错误：" + e;
  }
  render();
});

window.addEventListener("pywebviewready", load);
setTimeout(() => { if (window.pywebview && window.pywebview.api && !dims.length) load(); }, 1000);
setInterval(load, 30000);
