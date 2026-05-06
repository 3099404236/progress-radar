const heatColors = ["", "#1f3552", "#2c6aab", "#4a9bee"];
const phaseShades = ["#4a9bee", "#f0c870", "#8ad08f", "#d8a0e8", "#f08585", "#6cd0d0"];
const rarityClass = { common: "common", uncommon: "uncommon", rare: "rare", epic: "epic", legendary: "legendary" };

let dims = [];
let selected = null;       // dim id of expanded card; null = none expanded
let cycleFilter = "current";
let weeklyVisible = false;
let weeklyText = null;
let globalAchievements = null;

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
  svg += `<circle cx="${cx}" cy="${cy}" r="${ir * fill}" fill="rgba(74,155,238,0.10)"/>`;
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

function heat90(dim) {
  const heat = dim.heat_90 || [];
  // 7 行 (周日…周六) × 13 列大约 91 天的视图
  const days = 90;
  const today = new Date();
  // 计算每个 cell 对应的日期（heat[0] = days-1 天前）
  const cells = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() - (days - 1 - i));
    cells.push({ v: heat[i] || 0, date: d });
  }
  // 按周分列：第一列从最早一天所在的周日开始
  const cols = [];
  let curWeek = new Array(7).fill(null);
  cells.forEach((c) => {
    const dow = c.date.getDay();
    if (curWeek[dow] !== null && dow === 0) { cols.push(curWeek); curWeek = new Array(7).fill(null); }
    curWeek[dow] = c;
    if (dow === 6) { cols.push(curWeek); curWeek = new Array(7).fill(null); }
  });
  if (curWeek.some(x => x !== null)) cols.push(curWeek);

  // 月份标签
  const monthLabel = (i) => {
    const c = cols[i].find(x => x !== null);
    if (!c) return "";
    return c.date.getDate() <= 7 ? `${c.date.getMonth() + 1}月` : "";
  };

  let h = `<div class="heat90">`;
  h += `<div class="heat90-grid"><div class="heat90-months">`;
  for (let ci = 0; ci < cols.length; ci++) {
    h += `<div class="heat90-month">${monthLabel(ci)}</div>`;
  }
  h += `</div><div class="heat90-cols">`;
  for (let ci = 0; ci < cols.length; ci++) {
    h += `<div class="heat90-col">`;
    for (let r = 0; r < 7; r++) {
      const c = cols[ci][r];
      if (!c) { h += `<div class="heat90-cell empty"></div>`; continue; }
      const lvl = c.v >= 3 ? 3 : c.v;
      const bg = lvl > 0 ? heatColors[lvl] : "";
      const title = `${c.date.getMonth()+1}/${c.date.getDate()} · ${c.v} 条`;
      h += `<div class="heat90-cell" title="${title}"${bg ? ` style="background:${bg}"` : ""}></div>`;
    }
    h += `</div>`;
  }
  h += `</div></div>`;
  h += `<div class="heat90-legend"><span>少</span>`;
  for (let i = 0; i <= 3; i++) h += `<div class="heat90-cell" style="${i > 0 ? `background:${heatColors[i]}` : ""}"></div>`;
  h += `<span>多</span></div>`;
  h += `</div>`;
  return h;
}

function achievementsBlock(achv, dimId, isGlobal) {
  if (!achv) return "";
  const ms = achv.milestones || [];
  const ins = achv.insights || [];
  const cust = achv.custom || [];
  const unlockedMs = ms.filter(m => m.unlocked_at);
  const lockedMs = ms.filter(m => !m.unlocked_at);
  const next = achv.next_milestone;

  let h = `<div class="ach-section">`;
  h += `<div class="ach-head"><span class="ach-title">${isGlobal ? "全局成就" : "维度成就"}</span>
        <span class="ach-count">${achv.total_unlocked} 解锁 · 里程碑 ${achv.milestone_unlocked}/${achv.milestone_total}</span></div>`;

  if (unlockedMs.length || ins.length || cust.filter(c => c.unlocked_at).length) {
    h += `<div class="ach-grid">`;
    for (const m of unlockedMs) {
      h += achCard(m, "milestone");
    }
    for (const i of ins) {
      h += achCard(i, "insight");
    }
    for (const c of cust.filter(x => x.unlocked_at)) {
      h += achCard(c, "custom");
    }
    h += `</div>`;
  } else {
    h += `<div class="empty">尚无解锁</div>`;
  }

  if (next) {
    h += `<div class="ach-next">下一个：<b>${escapeHTML(next.title)}</b> — ${escapeHTML(next.description)}</div>`;
  }

  if (lockedMs.length) {
    h += `<div class="ach-locked">`;
    for (const m of lockedMs) {
      h += `<div class="ach-dot" title="${escapeHTML(m.title + ' — ' + m.description)}"></div>`;
    }
    h += `</div>`;
  }

  if (!isGlobal) {
    const lockedCust = cust.filter(c => !c.unlocked_at);
    h += `<div class="ach-custom-row">
            <span class="ach-sub">自定义成就（${cust.filter(c => c.unlocked_at).length}/${cust.length}）</span>
            <button class="bar-link" data-add-custom="${escapeHTML(dimId)}">+ 新建</button>
          </div>`;
    if (lockedCust.length) {
      h += `<div class="ach-grid">`;
      for (const c of lockedCust) h += achCard(c, "custom-locked");
      h += `</div>`;
    }
  }

  h += `</div>`;
  return h;
}

function achCard(item, kind) {
  const rar = rarityClass[item.rarity] || "common";
  const title = escapeHTML(item.title || "");
  const desc = escapeHTML(item.description || item.condition_text || "");
  const tag = kind === "insight" ? "洞察" : kind === "custom" ? "自定" : kind === "custom-locked" ? "未达" : "里程碑";
  const lock = kind === "custom-locked" ? " locked" : "";
  return `<div class="ach-card ${rar}${lock}" title="${desc}">
    <div class="ach-card-top"><span class="ach-card-tag">${tag}</span><span class="ach-card-rar">${item.rarity || "common"}</span></div>
    <div class="ach-card-title">${title}</div>
    <div class="ach-card-desc">${desc}</div>
  </div>`;
}

function metricRow(d) {
  return `<div class="dstat-row">
    <span class="dstat"><b>${d.stats.total_entries}</b> 记录</span>
    <span class="dstat"><b>${d.stats.active_days}</b> 活跃天</span>
    <span class="dstat"><b>${d.stats.max_streak}</b> 连续</span>
    <span class="dstat"><b>${d.stats.this_week}</b> 本周</span>
    <span class="dstat"><b>${d.achievements.milestone_unlocked}/${d.achievements.milestone_total}</b> 里程碑</span>
    ${(d.current_cycle || 1) > 1 ? `<span class="dstat dstat-cycle">周期 #${d.current_cycle}</span>` : ""}
  </div>`;
}

// ---------- 详情面板（嵌入到卡片下方） ----------

function renderDetailPanel(d) {
  const versionInfo = (d.phase_versions || []).length > 1
    ? ` · 阶段已演化 ${d.phase_versions.length - 1} 次`
    : "";
  let h = `<div class="dim-detail" data-detail="${escapeHTML(d.id)}">
    <div class="dim-detail-head">
      <div class="dim-detail-title">${escapeHTML(d.label)}${d.created_by === "auto" ? ' <span class="dim-badge" style="position:static;margin-left:6px">auto</span>' : ""}</div>
      <button class="bar-link" data-collapse>收起 ▲</button>
    </div>`;
  h += metricRow(d);
  h += `<div class="dim-detail-sub">主阶段：${escapeHTML((d.phases || [])[d.primary_phase] || "—")} · 共 ${d.total_entries || 0} 条记录${versionInfo}</div>`;
  h += `<h4 class="detail-h">阶段热力分布</h4>${phaseDistribution(d)}`;
  h += `<h4 class="detail-h">每日活跃（近 90 天）</h4>${heat90(d)}`;
  h += `<h4 class="detail-h">最近记录</h4>`;
  if (!(d.entries || []).length) {
    h += `<div class="empty">暂无记录</div>`;
  } else {
    h += `<div class="entries-wrap">`;
    for (const e of d.entries) {
      const phaseName = (d.phases || [])[e.phase_index] || "?";
      h += `<div class="entry">
        <div class="entry-date">${escapeHTML(e.d)}</div>
        <div class="entry-text">${escapeHTML(e.t)}<span class="entry-phase">${escapeHTML(phaseName)}</span>${e.tag ? `<span class="entry-tag">${escapeHTML(e.tag)}</span>` : ""}</div>
      </div>`;
    }
    h += `</div>`;
  }
  h += `<div class="detail-ach">${achievementsBlock(d.achievements, d.id, false)}</div>`;
  h += `</div>`;
  return h;
}

// ---------- 总览（单页，详情就地展开） ----------

function render() {
  const app = document.getElementById("app");
  const totalEntries = dims.reduce((s, x) => s + (x.total_entries || 0), 0);
  const activeDims = dims.filter(x => (x.total_entries || 0) > 0).length;
  const thisWeek = dims.reduce((s, x) => s + (x.heat || []).slice(-7).reduce((a, b) => a + b, 0), 0);

  let h = `<div class="metric-row">
    <div class="metric"><div class="metric-label">Total entries</div><div class="metric-val">${totalEntries}</div></div>
    <div class="metric"><div class="metric-label">Active dimensions</div><div class="metric-val">${activeDims}</div></div>
    <div class="metric"><div class="metric-label">This week activity</div><div class="metric-val">${thisWeek}</div></div>
  </div>`;

  if (!dims.length) {
    h += `<div class="empty">还没有任何维度。点击右上角 <b>+ 粘贴</b> 添加第一条。</div>`;
  } else {
    // 找出选中维度在网格里的"行结尾位置"，详情插在该行之后
    h += `<div class="dims">`;
    // 先全部画卡片，详情区作为 grid 的整行 child 插在选中卡片之后
    for (const dm of dims) {
      const stageName = (dm.phases || [])[dm.primary_phase] || "—";
      const total = dm.phases ? dm.phases.length : 0;
      const autoBadge = dm.created_by === "auto" ? `<div class="dim-badge">auto</div>` : "";
      const cycleBadge = (dm.current_cycle || 1) > 1 ? `<div class="dim-cycle-badge">#${dm.current_cycle}</div>` : "";
      const ach = dm.achievements || {};
      const achPill = `<span class="dim-ach-pill">${ach.milestone_unlocked || 0}/${ach.milestone_total || 13}</span>`;
      const isActive = dm.id === selected ? " active" : "";
      h += `<div class="dim-card${isActive}" data-id="${escapeHTML(dm.id)}">
        ${autoBadge}${cycleBadge}
        <div class="dim-label">${escapeHTML(dm.label)}</div>
        <div class="dim-stage">主阶段：${escapeHTML(stageName)}</div>
        <div class="dim-ring-row">
          ${ringSegmented(dm, 56)}
          <div class="dim-stats">
            <b>${dm.total_entries || 0}</b> 条 · ${total} 阶段<br>
            ${achPill} 里程碑
          </div>
        </div>
      </div>`;
    }
    h += `</div>`;

    // 详情面板放在网格下方
    if (selected) {
      const d = dims.find(x => x.id === selected);
      if (d) h += renderDetailPanel(d);
    }
  }

  if (globalAchievements && (globalAchievements.milestone_total || 0) > 0) {
    h += achievementsBlock(globalAchievements, "__global__", true);
  }

  app.innerHTML = h;

  app.querySelectorAll(".dim-card").forEach(card => {
    card.addEventListener("click", () => {
      const id = card.dataset.id;
      const wasOpen = selected === id;
      selected = wasOpen ? null : id;
      render();
      // 平滑滚动让详情区进入视口
      if (!wasOpen) {
        setTimeout(() => {
          const panel = document.querySelector(`[data-detail="${id}"]`);
          if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 30);
      }
    });
  });

  const collapseBtn = app.querySelector("[data-collapse]");
  if (collapseBtn) collapseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selected = null;
    render();
  });

  app.querySelectorAll("[data-add-custom]").forEach(btn => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); addCustomFlow(btn.dataset.addCustom); });
  });
}

async function addCustomFlow(dimId) {
  const title = prompt("成就名称（4-6字）：");
  if (!title) return;
  const cond = prompt("解锁条件描述（一句话）：");
  if (!cond) return;
  const rarity = prompt("稀有度：common / uncommon / rare / epic / legendary", "rare") || "rare";
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const r = JSON.parse(await window.pywebview.api.create_custom_achievement(dimId, title, cond, rarity));
    if (r.status === "ok") load();
    else alert("失败：" + (r.message || ""));
  } catch (e) { alert("错误：" + e); }
}

async function load() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const j = JSON.parse(await window.pywebview.api.get_dimensions(cycleFilter));
    dims = j.dimensions || [];
    globalAchievements = j.global_achievements || null;
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
  try { await window.pywebview.api.show_paste(); }
  catch (e) { alert("打开粘贴窗口失败：" + e); }
});

document.getElementById("export-raw-btn").addEventListener("click", async () => {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const s = JSON.parse(await window.pywebview.api.get_raw_stats());
    const ok = confirm(`已归档 ${s.count || 0} 条粘贴记录（${(s.size_bytes/1024).toFixed(1)} KB）。\n范围：${s.first || "—"} ~ ${s.last || "—"}\n\n导出到桌面？`);
    if (!ok) return;
    const r = JSON.parse(await window.pywebview.api.export_raw_to_desktop());
    if (r.status === "ok") alert(`已导出 ${r.count} 条到：\n${r.path}`);
    else alert("失败：" + (r.message || ""));
  } catch (e) { alert("错误：" + e); }
});

document.getElementById("weekly-btn").addEventListener("click", async () => {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const r = JSON.parse(await window.pywebview.api.generate_weekly_report());
    if (r.status === "ok") {
      alert("周报已生成：\n\n" + r.report.slice(0, 1500));
    } else {
      alert("失败：" + (r.message || ""));
    }
  } catch (e) {
    alert("错误：" + e);
  }
});

window.addEventListener("pywebviewready", load);
setTimeout(() => { if (window.pywebview && window.pywebview.api && !dims.length) load(); }, 1000);
setInterval(load, 30000);
