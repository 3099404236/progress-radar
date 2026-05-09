const heatColors = ["", "#1f3552", "#2c6aab", "#4a9bee"];
const phaseShades = ["#4a9bee", "#f0c870", "#8ad08f", "#d8a0e8", "#f08585", "#6cd0d0"];
const rarityClass = { common: "common", uncommon: "uncommon", rare: "rare", epic: "epic", legendary: "legendary" };
const rarityLabel = { common: "寻常", uncommon: "不凡", rare: "稀有", epic: "史诗", legendary: "传奇" };

let dims = [];
let selected = null;       // dim id of expanded card; null = none expanded
let cycleFilter = "current";
let weeklyVisible = false;
let weeklyText = null;
let globalAchievements = null;
let currentView = "active"; // 'active' | 'honored' | 'ignored' | 'notes'
let todayInfo = null;
let scratchpad = { content: "", updated_at: null };
let scratchpadDirty = false;
let arenaState = null;
let _lastArenaCups = 0;

const TROPHY_SVG = '<svg viewBox="0 0 24 24" class="trophy" fill="currentColor"><path d="M5 3h14v3.5c0 3.04-2.46 5.5-5.5 5.5h-3C7.46 12 5 9.54 5 6.5V3zM2 5h2v2c0 1.66 1.34 3 3 3v2c-2.76 0-5-2.24-5-5V5zm18 0h2v2c0 2.76-2.24 5-5 5v-2c1.66 0 3-1.34 3-3V5zM10 13h4v3h2v2H8v-2h2v-3z"/></svg>';

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

// 图片缓存 + 异步加载
const imageCache = {};   // image_id -> dataURL ("" 表示已查过但还没好)
const imageFetching = new Set();
let imagePollTimer = null;

async function fetchCardImage(imageId, imgEl) {
  if (!imageId || imageFetching.has(imageId)) return;
  if (imageCache[imageId]) {
    if (imgEl) imgEl.src = imageCache[imageId];
    return;
  }
  imageFetching.add(imageId);
  try {
    const r = JSON.parse(await window.pywebview.api.get_card_image(imageId));
    imageFetching.delete(imageId);
    if (r.ready && r.data_url) {
      imageCache[imageId] = r.data_url;
      // 找页面上所有等同 image_id 的 img 元素更新
      document.querySelectorAll(`img[data-img-id="${imageId}"]`).forEach(el => {
        el.src = r.data_url;
        el.classList.add("loaded");
      });
    }
  } catch (e) {
    imageFetching.delete(imageId);
  }
}

function ensureImagePolling() {
  if (imagePollTimer) return;
  imagePollTimer = setInterval(() => {
    document.querySelectorAll("img[data-img-id]:not(.loaded)").forEach(el => {
      const id = el.dataset.imgId;
      if (id && !imageCache[id]) fetchCardImage(id, el);
    });
  }, 6000);
}

function cardImageHTML(item, isUnlocked) {
  const iid = item.image_id || "";
  if (!isUnlocked) {
    return `<div class="card-img-wrap"><div class="card-img-locked">？</div></div>`;
  }
  // 已锁定但有 image_id：尝试展示，未生成完显示 loading
  return `<div class="card-img-wrap">
    <img class="card-img" data-img-id="${escapeHTML(iid)}" alt="${escapeHTML(item.title || '')}" />
    <div class="card-img-loading"><div class="spinner"></div><span>生成中</span></div>
  </div>`;
}

function achCard(item, kind) {
  const rar = rarityClass[item.rarity] || "common";
  const title = escapeHTML(item.title || "");
  const desc = escapeHTML(item.description || item.condition_text || "");
  const tag = kind === "insight" ? "洞察" : kind === "custom" ? "自定" : kind === "custom-locked" ? "未达" : "里程碑";
  const isLocked = kind === "custom-locked";
  const lock = isLocked ? " locked" : "";
  const rarText = rarityLabel[item.rarity] || "寻常";
  const date = item.unlocked_at ? `<div class="ach-card-date">${escapeHTML(item.unlocked_at)}</div>` : "";
  const dataAttrs = `data-card-id="${escapeHTML(item.image_id || '')}" data-card-vc="${escapeHTML(item.visual_concept || '')}" data-card-rarity="${escapeHTML(item.rarity || 'common')}"`;
  return `<div class="ach-card ${rar}${lock}" ${dataAttrs} title="${desc}">
    ${cardImageHTML(item, !isLocked)}
    <div class="ach-card-info">
      <div class="ach-card-top"><span class="ach-card-tag">${tag}</span><span class="ach-card-rar">${rarText}</span></div>
      <div class="ach-card-title">${title}</div>
      <div class="ach-card-desc">${desc}</div>
      ${date}
    </div>
  </div>`;
}

function todayMetricRow(t) {
  const total = t.total_today || 0;
  const dimsCount = t.active_dims_today || 0;
  const bt = t.by_track || { must: 0, main: 0, side: 0 };
  const sum = (bt.must || 0) + (bt.main || 0) + (bt.side || 0);
  const pct = (n) => sum > 0 ? Math.round((n || 0) / sum * 100) : 0;
  const signals = t.signals || [];

  let distInner;
  if (sum === 0) {
    distInner = `<div class="dist-empty">还没记录</div>`;
  } else {
    distInner = `
      <div class="dist-bar">
        ${bt.must ? `<div class="dist-seg must" style="width:${pct(bt.must)}%" title="必做 ${bt.must}"></div>` : ""}
        ${bt.main ? `<div class="dist-seg main" style="width:${pct(bt.main)}%" title="主线 ${bt.main}"></div>` : ""}
        ${bt.side ? `<div class="dist-seg side" style="width:${pct(bt.side)}%" title="支线 ${bt.side}"></div>` : ""}
      </div>
      <div class="dist-legend">
        ${bt.must ? `<span class="dl must"><i></i>必做 ${bt.must}</span>` : ""}
        ${bt.main ? `<span class="dl main"><i></i>主线 ${bt.main}</span>` : ""}
        ${bt.side ? `<span class="dl side"><i></i>支线 ${bt.side}</span>` : ""}
      </div>`;
  }

  let signalsHTML;
  if (!signals.length) {
    signalsHTML = `<div class="signal-empty">—</div>`;
  } else {
    signalsHTML = signals.map(sg =>
      `<div class="signal lvl-${sg.level || 'info'} kind-${sg.kind || ''}">${escapeHTML(sg.text || '')}</div>`
    ).join("");
  }

  // 卡片本身的高亮颜色取最高级别信号
  const topLevel = signals.length ? signals[0].level : "info";

  return `<div class="today-row">
    <div class="today-card today-count clickable" id="today-count-card" title="点击查看今日活动列表">
      <div class="metric-label">今天</div>
      <div class="metric-val">${total}</div>
      <div class="today-sub">${dimsCount ? dimsCount + ' 个方向 · 点击查看' : '尚未开张'}</div>
    </div>
    <div class="today-card today-dist clickable" id="today-dist-card" title="点击查看今日活动列表">
      <div class="metric-label">今日分布 · 点击查看</div>
      ${distInner}
    </div>
    <div class="today-card today-hint hint-${topLevel}">
      <div class="metric-label">提醒 · ${signals.length || 0}</div>
      <div class="signals">${signalsHTML}</div>
    </div>
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

// 计算单个 milestone 的进度（cur/target/label）
function milestoneProgress(m, d) {
  const stats = d.stats || {};
  const phasesLen = (d.phases || []).length || 1;
  const primary = d.primary_phase || 0;
  const versions = (d.phase_versions || []).length;
  const cycle = d.current_cycle || 1;
  switch (m.id) {
    case "dim_first":    return { cur: stats.total_entries, target: 1,  unit: "条记录" };
    case "dim_10":       return { cur: stats.total_entries, target: 10, unit: "条记录" };
    case "dim_deep":     return { cur: stats.total_entries, target: 20, unit: "条记录" };
    case "dim_50":       return { cur: stats.total_entries, target: 50, unit: "条记录" };
    case "dim_hatch":    return { cur: primary > 0 ? 1 : 0, target: 1, unit: "迈出起阶", binary: true, hint: primary > 0 ? "已迈出" : "尚在起阶" };
    case "dim_mid":      return { cur: primary, target: Math.floor(phasesLen / 2), unit: "阶段索引", hint: `主阶段 ${primary + 1}/${phasesLen}` };
    case "dim_finale":   return { cur: primary, target: phasesLen - 1, unit: "阶段索引", hint: `主阶段 ${primary + 1}/${phasesLen}` };
    case "dim_cycle2":   return { cur: cycle, target: 2,  unit: "周期", binary: true, hint: `当前周期 #${cycle}` };
    case "dim_streak3":  return { cur: stats.current_streak || 0, target: 3, unit: "天连续", hint: `连续 ${stats.current_streak || 0} 天` };
    case "dim_streak7":  return { cur: stats.current_streak || 0, target: 7, unit: "天连续", hint: `连续 ${stats.current_streak || 0} 天` };
    case "dim_active30": return { cur: stats.span_days || 0, target: 30, unit: "天跨度", hint: `首-末跨度 ${stats.span_days || 0} 天` };
    case "dim_active90": return { cur: stats.span_days || 0, target: 90, unit: "天跨度", hint: `首-末跨度 ${stats.span_days || 0} 天` };
    case "dim_reshape":  return { cur: versions >= 2 ? 1 : 0, target: 1, unit: "次演化", binary: true, hint: versions >= 2 ? "已演化" : "尚未演化（需 AI 重组阶段）" };
  }
  return { cur: 0, target: 1, unit: "" };
}

function nextMilestonesPanel(d) {
  const ms = (d.achievements && d.achievements.milestones) || [];
  const locked = ms.filter(m => !m.unlocked_at);
  if (!locked.length) {
    return `<div class="next-milestones empty-next">所有里程碑已解锁 — 已是该维度的"完全体"。</div>`;
  }
  // 算每个的进度比例，挑前 3 个最接近的
  const ranked = locked.map(m => {
    const p = milestoneProgress(m, d);
    const ratio = p.target > 0 ? Math.min(p.cur / p.target, 0.999) : 0;
    return { m, p, ratio };
  }).sort((a, b) => b.ratio - a.ratio).slice(0, 3);

  let h = `<h4 class="detail-h">下一里程碑</h4><div class="next-milestones">`;
  for (const { m, p, ratio } of ranked) {
    const pct = Math.round(ratio * 100);
    const rar = rarityClass[m.rarity] || "common";
    const rarText = rarityLabel[m.rarity] || "寻常";
    const right = p.binary
      ? `<span class="nm-hint">${escapeHTML(p.hint || "")}</span>`
      : `<span class="nm-hint">${escapeHTML(p.hint || `${p.cur}/${p.target} ${p.unit}`)}</span>`;
    h += `<div class="nm-row ${rar}">
      <div class="nm-line1">
        <span class="nm-title">${escapeHTML(m.title)}</span>
        <span class="nm-rar">${rarText}</span>
      </div>
      <div class="nm-bar"><div class="nm-bar-fill" style="width:${pct}%"></div></div>
      <div class="nm-line2">
        <span class="nm-desc">${escapeHTML(m.description || "")}</span>
        ${right}
      </div>
    </div>`;
  }
  h += `</div>`;
  return h;
}

// ---------- 详情面板（嵌入到卡片下方） ----------

function renderDetailPanel(d) {
  const versionInfo = (d.phase_versions || []).length > 1
    ? ` · 阶段已演化 ${d.phase_versions.length - 1} 次`
    : "";
  let h = `<div class="dim-detail" data-detail="${escapeHTML(d.id)}">
    <div class="dim-detail-head">
      <div class="dim-detail-title">${escapeHTML(d.label)}${d.created_by === "auto" ? ' <span class="dim-badge" style="position:static;margin-left:6px">auto</span>' : ""}</div>
      <div style="display:flex;gap:6px">
        <button class="bar-link" data-retheme="${escapeHTML(d.id)}" title="让 AI 按本维度主题重新命名 13 个里程碑">重命名成就</button>
        <button class="bar-link" data-collapse>收起 ▲</button>
      </div>
    </div>`;
  h += metricRow(d);
  h += `<div class="dim-detail-sub">主阶段：${escapeHTML((d.phases || [])[d.primary_phase] || "—")} · 共 ${d.total_entries || 0} 条记录${versionInfo}</div>`;
  h += nextMilestonesPanel(d);
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

// ---------- 总览（三栏：必做 / 主线 / 支线） ----------

const TRACK_DEF = [
  { key: "must", title: "必做", subtitle: "每天的基本盘 · 喝水/吃饭/作息" },
  { key: "main", title: "主线", subtitle: "核心目标 · 研究/竞赛/考试" },
  { key: "side", title: "支线", subtitle: "辅助探索 · 工具/兴趣/低频" },
];

function dimCardHTML(dm, posIndex) {
  const stageName = (dm.phases || [])[dm.primary_phase] || "—";
  const total = dm.phases ? dm.phases.length : 0;
  const autoBadge = dm.created_by === "auto" ? `<div class="dim-badge">auto</div>` : "";
  const cycleBadge = (dm.current_cycle || 1) > 1 ? `<div class="dim-cycle-badge">#${dm.current_cycle}</div>` : "";
  const ach = dm.achievements || {};
  const achPill = `<span class="dim-ach-pill">${ach.milestone_unlocked || 0}/${ach.milestone_total || 13}</span>`;
  const isActive = dm.id === selected ? " active" : "";
  const tier = posIndex === 0 ? " tier-0" : posIndex === 1 ? " tier-1" : posIndex === 2 ? " tier-2" : "";
  const tlCount = (dm.timeline || []).length;
  const tlBtn = `<button class="dim-tl-btn${tlCount ? ' has' : ''}" data-tl-id="${escapeHTML(dm.id)}" title="${tlCount ? '查看时间轴 ('+tlCount+')' : '时间轴（提交带日期的内容会自动填充）'}">${tlCount || ''}</button>`;
  return `<div class="dim-card${isActive}${tier}" draggable="true" data-id="${escapeHTML(dm.id)}">
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
    ${tlBtn}
  </div>`;
}

function render() {
  const app = document.getElementById("app");

  // 更新侧边计数
  const cntA = dims.filter(d => (d.state || "active") === "active").length;
  const cntH = dims.filter(d => d.state === "honored").length;
  const cntI = dims.filter(d => d.state === "ignored").length;
  const fmt = (n) => n;
  const setText = (id, v) => { const e = document.getElementById(id); if (e) e.textContent = fmt(v); };
  setText("cnt-active", cntA); setText("cnt-honored", cntH); setText("cnt-ignored", cntI);

  // 记事视图独立渲染
  if (currentView === "notes") {
    renderScratchpad();
    return;
  }

  let h = todayMetricRow(todayInfo || {});

  // 按当前视图过滤
  const visible = dims.filter(d => (d.state || "active") === currentView);

  if (!dims.length) {
    h += `<div class="empty">还没有任何维度。点击右上角 <b>+ 粘贴</b> 添加第一条。</div>`;
  } else if (currentView === "active") {
    if (!visible.length) {
      h += `<div class="empty">所有维度都已归档或忽视，左侧切到「荣誉墙」或「已忽视」查看。</div>`;
    } else {
      const buckets = { must: [], main: [], side: [] };
      for (const dm of visible) {
        const t = (buckets[dm.track] !== undefined) ? dm.track : "main";
        buckets[t].push(dm);
      }
      for (const k of Object.keys(buckets)) {
        buckets[k].sort((a, b) => {
          const ar = a.rank == null ? 9999 : a.rank;
          const br = b.rank == null ? 9999 : b.rank;
          if (ar !== br) return ar - br;
          return (b.created_at || "").localeCompare(a.created_at || "");
        });
      }

      h += `<div class="track-grid">`;
      for (const td of TRACK_DEF) {
        const list = buckets[td.key];
        h += `<div class="track-col" data-track="${td.key}">
          <div class="track-head">
            <div class="track-title">${td.title}</div>
            <div class="track-sub">${td.subtitle}</div>
            <div class="track-count">${list.length}</div>
          </div>
          <div class="track-drop" data-track="${td.key}">`;
        if (!list.length) {
          h += `<div class="track-empty">把卡片拖过来</div>`;
        }
        for (let i = 0; i < list.length; i++) {
          h += dimCardHTML(list[i], i);
        }
        h += `</div></div>`;
      }
      h += `</div>`;
    }
  } else {
    // honored / ignored 视图：扁平网格，按 state_changed_at 倒序
    const sorted = visible.slice().sort((a, b) =>
      (b.state_changed_at || "").localeCompare(a.state_changed_at || "")
    );
    const headTitle = currentView === "honored" ? "荣誉墙" : "已忽视";
    const headSub = currentView === "honored"
      ? "已完成的旅程 — 你曾走过的山。右键可恢复或转入忽视。"
      : "暂时不追踪的方向。右键可恢复或转入荣誉。";
    h += `<div class="state-view ${currentView}">
      <div class="state-head">
        <div class="state-title">${headTitle}</div>
        <div class="state-sub">${headSub} · 共 ${sorted.length} 项</div>
      </div>`;
    if (!sorted.length) {
      h += `<div class="empty">还没有 ${headTitle} 中的维度。在「进行中」对一张卡右键即可归档到这里。</div>`;
    } else {
      h += `<div class="state-grid">`;
      for (const dm of sorted) h += dimCardHTML(dm, 99);
      h += `</div>`;
    }
    h += `</div>`;
  }

  // 详情面板（任意视图都可展开看详情）
  if (selected) {
    const d = dims.find(x => x.id === selected);
    if (d && (d.state || "active") === currentView) h += renderDetailPanel(d);
  }

  // 全局成就重组成竞技场卡片
  if (arenaState) {
    h += arenaCardHTML(arenaState);
  }

  app.innerHTML = h;

  // 顶部"今天 / 分布"卡片点击 → 今日活动 modal
  ["today-count-card", "today-dist-card"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", openTodayModal);
  });

  // 卡片点击展开详情；拖拽行为见 wireDragAndDrop
  app.querySelectorAll(".dim-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (card.classList.contains("dragging")) return;  // 拖动后短暂阻止 click
      const id = card.dataset.id;
      const wasOpen = selected === id;
      selected = wasOpen ? null : id;
      render();
      if (!wasOpen) {
        setTimeout(() => {
          const panel = document.querySelector(`[data-detail="${id}"]`);
          if (panel) panel.scrollIntoView({ behavior: "smooth", block: "start" });
        }, 30);
      }
    });
  });

  wireDragAndDrop();
  wireContextMenu();
  wireTimelineButtons();
  wireArenaCard();

  const collapseBtn = app.querySelector("[data-collapse]");
  if (collapseBtn) collapseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    selected = null;
    render();
  });

  app.querySelectorAll("[data-add-custom]").forEach(btn => {
    btn.addEventListener("click", (e) => { e.stopPropagation(); addCustomFlow(btn.dataset.addCustom); });
  });

  app.querySelectorAll("[data-retheme]").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!window.pywebview || !window.pywebview.api) return;
      const id = btn.dataset.retheme;
      const orig = btn.textContent;
      btn.disabled = true; btn.textContent = "AI 正在命名…";
      try {
        const r = JSON.parse(await window.pywebview.api.regenerate_themed_milestones(id));
        if (r.status === "ok") {
          btn.textContent = `已重命名 ${r.count} 项 ✓`;
          setTimeout(() => { btn.textContent = orig; btn.disabled = false; load(); }, 1200);
        } else {
          alert("失败：" + (r.message || ""));
          btn.disabled = false; btn.textContent = orig;
        }
      } catch (err) {
        alert("错误：" + err);
        btn.disabled = false; btn.textContent = orig;
      }
    });
  });

  // 卡牌点击 → 大图 modal
  app.querySelectorAll(".ach-card").forEach(card => {
    if (card.classList.contains("locked")) return;
    card.addEventListener("click", (e) => {
      e.stopPropagation();
      openCardModal(card);
    });
  });

  // 启动一轮异步加载图片
  app.querySelectorAll("img[data-img-id]").forEach(img => {
    const iid = img.dataset.imgId;
    if (imageCache[iid]) {
      img.src = imageCache[iid];
      img.classList.add("loaded");
    } else {
      fetchCardImage(iid, img);
    }
  });
  ensureImagePolling();
}

function openCardModal(cardEl) {
  const iid = cardEl.dataset.cardId;
  const vc = cardEl.dataset.cardVc;
  const rarity = cardEl.dataset.cardRarity;
  const titleEl = cardEl.querySelector(".ach-card-title");
  const descEl = cardEl.querySelector(".ach-card-desc");
  const dateEl = cardEl.querySelector(".ach-card-date");
  const tagEl = cardEl.querySelector(".ach-card-tag");
  const rarEl = cardEl.querySelector(".ach-card-rar");

  const title = titleEl ? titleEl.textContent : "";
  const desc = descEl ? descEl.textContent : "";
  const date = dateEl ? dateEl.textContent : "";
  const tag = tagEl ? tagEl.textContent : "";
  const rarText = rarEl ? rarEl.textContent : "";

  const imgURL = imageCache[iid] || "";
  const modal = document.createElement("div");
  modal.className = "card-modal";
  modal.innerHTML = `
    <div class="card-modal-bg"></div>
    <div class="card-modal-card ${rarityClass[rarity] || 'common'}">
      <div class="card-modal-img-wrap">
        ${imgURL
          ? `<img class="card-modal-img loaded" src="${imgURL}" />`
          : `<img class="card-modal-img" data-img-id="${escapeHTML(iid)}" />
             <div class="card-img-loading"><div class="spinner big"></div><span>正在生成卡面…</span></div>`}
      </div>
      <div class="card-modal-info">
        <div class="card-modal-tags"><span class="ach-card-tag">${escapeHTML(tag)}</span><span class="ach-card-rar">${escapeHTML(rarText)}</span></div>
        <div class="card-modal-title">${escapeHTML(title)}</div>
        <div class="card-modal-desc">${escapeHTML(desc)}</div>
        ${date ? `<div class="ach-card-date">${escapeHTML(date)}</div>` : ""}
        <div class="card-modal-actions">
          ${vc ? `<button class="bar-link" data-regen>重新生成卡面</button>` : ""}
          <button class="btn btn-secondary" data-close>关闭</button>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  modal.querySelector(".card-modal-bg").addEventListener("click", () => modal.remove());
  modal.querySelector("[data-close]").addEventListener("click", () => modal.remove());
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { modal.remove(); document.removeEventListener("keydown", esc); }
  });

  const regenBtn = modal.querySelector("[data-regen]");
  if (regenBtn) {
    regenBtn.addEventListener("click", async () => {
      regenBtn.disabled = true; regenBtn.textContent = "重新生成中…";
      try {
        const r = JSON.parse(await window.pywebview.api.regenerate_card_image(iid, vc, rarity));
        if (r.status === "ok" && r.data_url) {
          imageCache[iid] = r.data_url;
          modal.querySelector(".card-modal-img").src = r.data_url;
          modal.querySelector(".card-modal-img").classList.add("loaded");
          const ld = modal.querySelector(".card-img-loading");
          if (ld) ld.style.display = "none";
          regenBtn.textContent = "已替换 ✓";
        } else {
          regenBtn.textContent = "失败"; alert("失败：" + (r.message || ""));
        }
      } catch (err) { alert("错误：" + err); regenBtn.disabled = false; regenBtn.textContent = "重新生成卡面"; }
    });
  }

  // 弹层内的图片如果还没就绪，启动 fetch
  modal.querySelectorAll("img[data-img-id]:not(.loaded)").forEach(img => {
    fetchCardImage(img.dataset.imgId, img);
  });
}

// ---------- 拖拽：跨栏移动 / 同栏排序 ----------

let dragSrcId = null;

function wireDragAndDrop() {
  document.querySelectorAll(".dim-card").forEach(card => {
    card.addEventListener("dragstart", (e) => {
      dragSrcId = card.dataset.id;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", dragSrcId); } catch (_) {}
    });
    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      document.querySelectorAll(".track-drop.over, .dim-card.drop-target").forEach(el => {
        el.classList.remove("over");
        el.classList.remove("drop-target");
      });
      // 拖完短暂保留 dragging class 阻止 click 误触发
      setTimeout(() => card.classList.remove("dragging"), 50);
    });
  });

  document.querySelectorAll(".track-drop").forEach(zone => {
    zone.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      zone.classList.add("over");
      // 找最接近指针的卡片，标 drop-target（视觉指示）
      const cards = [...zone.querySelectorAll(".dim-card:not(.dragging)")];
      const after = cards.find(c => {
        const r = c.getBoundingClientRect();
        return e.clientY < r.top + r.height / 2;
      });
      zone.querySelectorAll(".dim-card.drop-target").forEach(el => el.classList.remove("drop-target"));
      if (after) after.classList.add("drop-target");
    });
    zone.addEventListener("dragleave", () => zone.classList.remove("over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("over");
      if (!dragSrcId) return;
      const src = document.querySelector(`.dim-card[data-id="${dragSrcId}"]`);
      if (!src) return;
      const cards = [...zone.querySelectorAll(".dim-card:not(.dragging)")];
      const after = cards.find(c => {
        const r = c.getBoundingClientRect();
        return e.clientY < r.top + r.height / 2;
      });
      if (after) zone.insertBefore(src, after);
      else zone.appendChild(src);
      dragSrcId = null;
      persistTrackLayout();
    });
  });
}

// ---------- 今日活动 modal ----------

async function openTodayModal() {
  if (!window.pywebview || !window.pywebview.api) return;
  let data;
  try {
    data = JSON.parse(await window.pywebview.api.get_today_entries());
  } catch (e) {
    alert("加载失败：" + e); return;
  }
  if (data.status !== "ok") { alert("失败：" + (data.message || "")); return; }
  const items = data.items || [];

  let body;
  if (!items.length) {
    body = `<div class="today-modal-empty">今天还没有任何记录。点 + 粘贴 写点什么吧。</div>`;
  } else {
    body = `<ul class="today-list">`;
    for (const it of items) {
      const trk = it.track || "main";
      body += `<li class="today-item track-${trk}" data-dim-id="${escapeHTML(it.dim_id)}">
        <div class="today-time">${escapeHTML(it.time)}</div>
        <div class="today-meat">
          <div class="today-line1">
            <span class="today-dim-pill ${trk}">${escapeHTML(it.dim_label)}</span>
            <span class="today-phase">${escapeHTML(it.phase_name)}</span>
            ${it.tag ? `<span class="entry-tag">${escapeHTML(it.tag)}</span>` : ""}
            ${(it.cross_dimensions||[]).length ? `<span class="today-cross">↔ ${(it.cross_dimensions||[]).map(escapeHTML).join("、")}</span>` : ""}
          </div>
          <div class="today-summary">${escapeHTML(it.summary)}</div>
          ${(it.key_progress||[]).length ? `<ul class="today-kp">${it.key_progress.map(kp=>`<li>${escapeHTML(kp)}</li>`).join("")}</ul>` : ""}
        </div>
      </li>`;
    }
    body += `</ul>`;
  }

  // 按 track 计数
  const cnt = items.reduce((acc, it) => { acc[it.track || "main"] = (acc[it.track || "main"] || 0) + 1; return acc; }, {});

  const modal = document.createElement("div");
  modal.className = "today-modal";
  modal.innerHTML = `
    <div class="today-modal-bg"></div>
    <div class="today-modal-card">
      <div class="today-modal-head">
        <div>
          <div class="today-modal-title">今天的活动 · ${items.length} 条</div>
          <div class="today-modal-sub">
            必做 ${cnt.must || 0} · 主线 ${cnt.main || 0} · 支线 ${cnt.side || 0}
          </div>
        </div>
        <button class="tl-close" data-close>×</button>
      </div>
      <div class="today-modal-body">${body}</div>
    </div>
  `;
  document.body.appendChild(modal);

  modal.querySelector(".today-modal-bg").addEventListener("click", () => modal.remove());
  modal.querySelector("[data-close]").addEventListener("click", () => modal.remove());
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { modal.remove(); document.removeEventListener("keydown", esc); }
  });
  // 点击维度 pill / item → 跳转到对应维度详情
  modal.querySelectorAll(".today-item").forEach(li => {
    li.addEventListener("click", () => {
      const id = li.dataset.dimId;
      modal.remove();
      selected = id;
      currentView = "active";
      document.querySelectorAll("#dash-side .side-tab").forEach(b =>
        b.classList.toggle("on", b.dataset.view === "active")
      );
      render();
      setTimeout(() => {
        const card = document.querySelector(`.dim-card[data-id="${id}"]`);
        if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
      }, 50);
    });
  });
}

// ---------- 时间轴漫画气泡 ----------

let _tlBubble = null;

function wireTimelineButtons() {
  document.querySelectorAll(".dim-tl-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const dim = dims.find(x => x.id === btn.dataset.tlId);
      if (!dim) return;
      openTimelineBubble(btn, dim);
    });
  });
}

function closeTimelineBubble() {
  if (_tlBubble) { _tlBubble.remove(); _tlBubble = null; }
}

function openTimelineBubble(anchor, dim) {
  closeTimelineBubble();
  const tl = (dim.timeline || []).slice().sort((a, b) => (a.date || "").localeCompare(b.date || ""));
  const today = new Date().toISOString().slice(0, 10);

  let body = "";
  if (!tl.length) {
    body = `<div class="tl-empty">还没有时间事件。<br>在粘贴页提交"6 月 15 日操作系统期末"这种带日期的内容，AI 会自动填进来。</div>`;
  } else {
    body = `<ol class="tl-list">`;
    for (const ev of tl) {
      let cls = "future";
      if (ev.date < today) cls = "past";
      else if (ev.date === today) cls = "today";
      const dt = new Date(ev.date + "T00:00:00");
      const md = `${dt.getMonth()+1}/${dt.getDate()}`;
      const wk = "日一二三四五六"[dt.getDay()];
      let countdown = "";
      if (ev.date >= today) {
        const days = Math.round((dt - new Date(today + "T00:00:00")) / 86400000);
        countdown = days === 0 ? "今天" : `${days} 天后`;
      } else {
        const days = Math.round((new Date(today + "T00:00:00") - dt) / 86400000);
        countdown = `${days} 天前`;
      }
      body += `<li class="tl-item ${cls}">
        <div class="tl-dot"></div>
        <div class="tl-meat">
          <div class="tl-line1">
            <span class="tl-date">${md}</span>
            <span class="tl-week">周${wk}</span>
            <span class="tl-cd">${countdown}</span>
          </div>
          <div class="tl-label">${escapeHTML(ev.label)}</div>
          ${ev.note ? `<div class="tl-note">${escapeHTML(ev.note)}</div>` : ""}
          <button class="tl-del" data-del="${escapeHTML(ev.id)}" title="删除">×</button>
        </div>
      </li>`;
    }
    body += `</ol>`;
  }

  const bubble = document.createElement("div");
  bubble.className = "tl-bubble";
  bubble.innerHTML = `
    <div class="tl-bubble-head">
      <div class="tl-bubble-title">时间轴 · ${escapeHTML(dim.label)}</div>
      <button class="tl-close" data-close>×</button>
    </div>
    ${body}
    <div class="tl-arrow"></div>
  `;
  document.body.appendChild(bubble);
  _tlBubble = bubble;

  // 定位：默认从 anchor 右下方往外引出。气泡放在 anchor 下方一点
  const ar = anchor.getBoundingClientRect();
  const vw = window.innerWidth, vh = window.innerHeight;
  const br = bubble.getBoundingClientRect();
  let left = ar.right + 10;
  let top  = ar.top - 8;
  let arrowSide = "left";
  // 右边塞不下：从左侧出
  if (left + br.width + 12 > vw) { left = ar.left - br.width - 10; arrowSide = "right"; }
  // 底部塞不下：往上抬
  if (top + br.height + 12 > vh) top = vh - br.height - 12;
  if (top < 12) top = 12;
  if (left < 12) left = 12;
  bubble.style.left = left + "px";
  bubble.style.top  = top + "px";
  bubble.classList.add("arrow-" + arrowSide);
  // 把箭头垂直对到 anchor 中心
  const anchorMid = ar.top + ar.height / 2;
  const arrowEl = bubble.querySelector(".tl-arrow");
  if (arrowEl) arrowEl.style.top = (anchorMid - top - 8) + "px";

  // 删除事件
  bubble.querySelectorAll("[data-del]").forEach(b => {
    b.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = b.dataset.del;
      try {
        await window.pywebview.api.remove_timeline_event(dim.id, id);
        dim.timeline = (dim.timeline || []).filter(x => x.id !== id);
        closeTimelineBubble();
        render();
      } catch (err) { alert("错误：" + err); }
    });
  });
  bubble.querySelector("[data-close]").addEventListener("click", closeTimelineBubble);
  setTimeout(() => {
    document.addEventListener("click", function once(e) {
      if (_tlBubble && !_tlBubble.contains(e.target)) {
        closeTimelineBubble();
        document.removeEventListener("click", once);
      } else {
        document.addEventListener("click", once, { once: true });
      }
    }, { once: true });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { closeTimelineBubble(); document.removeEventListener("keydown", esc); }
    });
  }, 0);
}

// ---------- 右键菜单：完成 / 忽视 / 恢复 ----------

function wireContextMenu() {
  document.querySelectorAll(".dim-card").forEach(card => {
    card.addEventListener("contextmenu", (e) => {
      e.preventDefault();
      const dim = dims.find(x => x.id === card.dataset.id);
      if (!dim) return;
      showContextMenu(e.clientX, e.clientY, dim);
    });
  });
}

function showContextMenu(x, y, dim) {
  const menu = document.getElementById("ctx-menu");
  const cur = dim.state || "active";
  const items = [];
  if (cur !== "honored") items.push({ label: "标记完成（→ 荣誉墙）", to: "honored" });
  if (cur !== "ignored") items.push({ label: "忽视（→ 垃圾箱）", to: "ignored" });
  if (cur !== "active")  items.push({ label: "恢复到进行中", to: "active" });

  menu.innerHTML = items.map(it =>
    `<div class="ctx-item" data-to="${it.to}">${it.label}</div>`
  ).join("");

  // 定位（避免出屏）
  const vw = window.innerWidth, vh = window.innerHeight;
  menu.style.display = "block";
  const r = menu.getBoundingClientRect();
  menu.style.left = Math.min(x, vw - r.width - 8) + "px";
  menu.style.top  = Math.min(y, vh - r.height - 8) + "px";

  const close = () => { menu.style.display = "none"; menu.innerHTML = ""; };
  menu.querySelectorAll(".ctx-item").forEach(it => {
    it.addEventListener("click", async () => {
      const to = it.dataset.to;
      close();
      try {
        const r = JSON.parse(await window.pywebview.api.set_dim_state(dim.id, to));
        if (r.status === "ok") {
          dim.state = to;
          dim.state_changed_at = new Date().toISOString();
          load();  // 拉一次最新数据，含计数
        } else {
          alert("失败：" + (r.message || ""));
        }
      } catch (err) { alert("错误：" + err); }
    });
  });

  // 点其他地方 / Esc 关闭
  setTimeout(() => {
    document.addEventListener("click", close, { once: true });
    document.addEventListener("keydown", function esc(e) {
      if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
    });
  }, 0);
}

async function persistTrackLayout() {
  if (!window.pywebview || !window.pywebview.api) return;
  const layout = { must: [], main: [], side: [] };
  document.querySelectorAll(".track-drop").forEach(zone => {
    const t = zone.dataset.track;
    layout[t] = [...zone.querySelectorAll(".dim-card")].map(c => c.dataset.id);
  });
  try {
    const r = JSON.parse(await window.pywebview.api.set_track_layout(JSON.stringify(layout)));
    if (r.status === "ok") {
      // 不整体重渲染，仅更新 dims 内存中的 track/rank，避免 DOM 闪烁
      for (const t of ["must", "main", "side"]) {
        layout[t].forEach((id, idx) => {
          const dm = dims.find(x => x.id === id);
          if (dm) { dm.track = t; dm.rank = idx; }
        });
      }
      // 重新算 tier class（rank 0/1/2 视觉）
      document.querySelectorAll(".track-drop").forEach(zone => {
        [...zone.querySelectorAll(".dim-card")].forEach((c, idx) => {
          c.classList.remove("tier-0", "tier-1", "tier-2");
          if (idx === 0) c.classList.add("tier-0");
          else if (idx === 1) c.classList.add("tier-1");
          else if (idx === 2) c.classList.add("tier-2");
        });
        // 更新栏目计数
        const head = zone.parentElement.querySelector(".track-count");
        if (head) head.textContent = zone.querySelectorAll(".dim-card").length;
      });
    }
  } catch (e) { console.warn("布局保存失败:", e); }
}

// ---------- 全局竞技场天梯 ----------

function arenaCardHTML(s) {
  if (!s) return "";
  const cups = s.cups || 0;
  const cur = (s.current_idx >= 0 && s.arenas) ? s.arenas[s.current_idx] : null;
  const next = (s.next_idx !== null && s.next_idx !== undefined) ? s.arenas[s.next_idx] : null;
  const pct = Math.round((s.progress_to_next || 0) * 100);
  const curRar = cur ? (cur.rarity || "common") : "common";

  const headLeft = `${TROPHY_SVG}
    <span class="arena-cups-num" data-target="${cups}">${_lastArenaCups || cups}</span>
    <span class="arena-cups-label">杯</span>`;
  const headRight = cur
    ? `<span class="arena-cur-pos">第 ${cur.position} 届</span><span class="arena-cur-title">${escapeHTML(cur.title)}</span>`
    : `<span class="arena-cur-title">尚未踏入第一届</span>`;

  let centerHTML;
  if (cur && cur.image_id) {
    centerHTML = `<img class="arena-card-img" data-img-id="${escapeHTML(cur.image_id)}" alt="${escapeHTML(cur.title)}" />`;
  } else {
    centerHTML = `<div class="arena-card-placeholder">${escapeHTML(cur ? cur.title : "尚未达到")}</div>`;
  }

  return `
    <div class="arena-card rarity-${curRar}" id="arena-main-card" title="点击查看全部 ${s.max_arena || 7} 届">
      <div class="arena-card-head">
        <div class="arena-cups">${headLeft}</div>
        <div class="arena-cur">${headRight}</div>
      </div>
      <div class="arena-card-img-wrap">${centerHTML}</div>
      <div class="arena-card-foot">
        <div class="arena-bar"><div class="arena-fill" style="width:${pct}%"></div></div>
        <div class="arena-target">
          ${next
            ? `下一届：<b>${escapeHTML(next.title)}</b> · 还差 ${s.cups_to_next} 杯（门槛 ${next.threshold}）`
            : `已是最高竞技场`}
        </div>
      </div>
    </div>
  `;
}

function animateArenaProgress() {
  const el = document.querySelector(".arena-cups-num");
  if (!el) return;
  // 加载 arena 中央卡面图（无论杯数有没有变都要做）
  const cardImg = document.querySelector(".arena-card-img[data-img-id]");
  if (cardImg) {
    const iid = cardImg.dataset.imgId;
    if (imageCache[iid]) { cardImg.src = imageCache[iid]; cardImg.classList.add("loaded"); }
    else fetchCardImage(iid, cardImg);
  }
  const target = parseInt(el.dataset.target || "0", 10);
  const from = parseInt(el.textContent, 10) || 0;
  if (from === target) { _lastArenaCups = target; return; }
  const start = performance.now();
  const dur = 900;
  const step = (now) => {
    const t = Math.min(1, (now - start) / dur);
    const eased = 1 - Math.pow(1 - t, 3);
    el.textContent = Math.round(from + (target - from) * eased);
    if (t < 1) requestAnimationFrame(step);
    else { el.textContent = target; _lastArenaCups = target; }
  };
  requestAnimationFrame(step);
}

function wireArenaCard() {
  const card = document.getElementById("arena-main-card");
  if (card) card.addEventListener("click", openArenaModal);
}

function openArenaModal() {
  if (!arenaState) return;
  const overlay = document.createElement("div");
  overlay.className = "arena-modal";

  const arenas = arenaState.arenas || [];
  let body = `<div class="arena-ladder">`;
  for (const a of arenas) {
    const isCur = (a.position - 1) === arenaState.current_idx;
    const isNext = (a.position - 1) === arenaState.next_idx;
    let cls;
    if (a.unlocked) cls = "ok" + (isCur ? " current" : "");
    else if (isNext) cls = "next";
    else cls = "locked";
    const rar = a.rarity || "common";

    let imgHTML;
    if (a.unlocked && a.image_id) {
      imgHTML = `<img class="arena-item-img" data-img-id="${escapeHTML(a.image_id)}" />`;
    } else {
      imgHTML = `<div class="arena-item-locked-img">${a.position}</div>`;
    }

    body += `<div class="arena-item ${cls} rarity-${rar}">
      <div class="arena-item-pos">#${a.position}</div>
      <div class="arena-item-img-wrap">${imgHTML}</div>
      <div class="arena-item-meat">
        <div class="arena-item-title-row">
          <span class="arena-item-title">${escapeHTML(a.title || "（未解锁）")}</span>
          <span class="arena-item-rar">${escapeHTML(rarityLabel[rar] || "寻常")}</span>
        </div>
        <div class="arena-item-desc">${escapeHTML(a.description || "")}</div>
        <div class="arena-item-meta">
          ${a.unlocked
            ? `<span class="arena-item-unlocked">已解锁 · ${escapeHTML(a.unlocked_at || "")}</span>`
            : `<span class="arena-item-cond">门槛 ${a.threshold} 杯${isNext ? `（还差 ${arenaState.cups_to_next} 杯）` : ""}</span>`}
        </div>
      </div>
    </div>`;
  }
  body += `</div>`;

  overlay.innerHTML = `
    <div class="card-modal-bg"></div>
    <div class="arena-modal-card">
      <div class="arena-modal-head">
        <div>
          <div class="arena-modal-title">竞技场天梯</div>
          <div class="arena-modal-sub">
            ${TROPHY_SVG}<span class="arena-modal-cups">${arenaState.cups}</span> 杯 ·
            已征服 ${arenas.filter(a => a.unlocked).length} / ${arenas.length} 届
          </div>
        </div>
        <button class="tl-close" data-close>×</button>
      </div>
      <div class="arena-modal-body">${body}</div>
    </div>
  `;
  document.body.appendChild(overlay);
  overlay.querySelector(".card-modal-bg").addEventListener("click", () => overlay.remove());
  overlay.querySelector("[data-close]").addEventListener("click", () => overlay.remove());
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", esc); }
  });
  // 加载图
  overlay.querySelectorAll("img[data-img-id]").forEach(img => {
    const iid = img.dataset.imgId;
    if (imageCache[iid]) img.src = imageCache[iid];
    else fetchCardImage(iid, img);
  });
}


// ---------- 临时记事本（单 textarea + 自动保存 + 历史） ----------

let _padAutoTimer = null;
const PAD_AUTOSAVE_DELAY = 1500;  // ms

async function loadScratchpad() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const r = JSON.parse(await window.pywebview.api.get_scratchpad());
    scratchpad = { content: r.content || "", updated_at: r.updated_at || null };
    scratchpadDirty = false;
  } catch (e) { scratchpad = { content: "", updated_at: null }; }
}

function renderScratchpad() {
  const app = document.getElementById("app");
  const upd = scratchpad.updated_at
    ? "上次保存于 " + scratchpad.updated_at.slice(0, 16).replace("T", " ")
    : "尚未保存";
  app.innerHTML = `
    <div class="pad-shell">
      <div class="pad-head">
        <div class="pad-meta" id="pad-meta">${escapeHTML(upd)}</div>
        <div class="pad-actions">
          <button class="bar-link" id="pad-history-btn">历史版本</button>
          <span class="pad-status" id="pad-status">自动保存</span>
        </div>
      </div>
      <textarea id="pad-content" class="pad-textarea" placeholder="临时记一笔 · 边打边自动保存，每次保存的旧版本都会留底，从「历史版本」可恢复"></textarea>
    </div>
  `;
  const ta = document.getElementById("pad-content");
  ta.value = scratchpad.content || "";
  ta.focus();

  ta.addEventListener("input", () => {
    scratchpadDirty = true;
    setPadStatus("…正在输入");
    if (_padAutoTimer) clearTimeout(_padAutoTimer);
    _padAutoTimer = setTimeout(saveScratchpad, PAD_AUTOSAVE_DELAY);
  });
  ta.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault(); saveScratchpad();
    }
  });
  document.getElementById("pad-history-btn").addEventListener("click", openPadHistory);
}

function setPadStatus(text, kind="") {
  const el = document.getElementById("pad-status");
  if (!el) return;
  el.textContent = text;
  el.className = "pad-status" + (kind ? " " + kind : "");
}

async function saveScratchpad() {
  const ta = document.getElementById("pad-content");
  if (!ta) return;
  if (_padAutoTimer) { clearTimeout(_padAutoTimer); _padAutoTimer = null; }
  const content = ta.value;
  if (content === scratchpad.content) {
    setPadStatus("已保存", "ok");
    return;
  }
  setPadStatus("保存中…");
  try {
    const r = JSON.parse(await window.pywebview.api.save_scratchpad(content));
    if (r.status === "ok") {
      scratchpad.content = content;
      scratchpad.updated_at = r.updated_at;
      scratchpadDirty = false;
      setPadStatus("已保存 ✓", "ok");
      const meta = document.getElementById("pad-meta");
      if (meta) meta.textContent = "上次保存于 " + r.updated_at.slice(0,16).replace("T"," ");
    } else {
      setPadStatus("保存失败", "err");
    }
  } catch (e) { setPadStatus("保存失败", "err"); }
}

async function openPadHistory() {
  if (!window.pywebview || !window.pywebview.api) return;
  let history = [];
  try {
    const r = JSON.parse(await window.pywebview.api.get_scratchpad_history());
    history = r.history || [];
  } catch (e) {}

  const overlay = document.createElement("div");
  overlay.className = "pad-hist-overlay";
  let body;
  if (!history.length) {
    body = `<div class="pad-hist-empty">还没有历史版本。每次内容变更后会自动留底。</div>`;
  } else {
    body = `<ul class="pad-hist-list">` + history.map((h, i) => {
      const ts = (h.ts || "").slice(0, 16).replace("T", " ");
      const preview = (h.content || "").slice(0, 200).replace(/\s+/g, " ");
      const more = (h.content || "").length > 200 ? "…" : "";
      return `<li class="pad-hist-item" data-idx="${i}">
        <div class="pad-hist-ts">${escapeHTML(ts)}</div>
        <div class="pad-hist-preview">${escapeHTML(preview)}${more}</div>
        <div class="pad-hist-actions">
          <button class="bar-link" data-action="restore">恢复</button>
          <button class="bar-link" data-action="insert">追加到末尾</button>
        </div>
      </li>`;
    }).join("") + `</ul>`;
  }
  overlay.innerHTML = `
    <div class="pad-hist-bg"></div>
    <div class="pad-hist-card">
      <div class="pad-hist-head">
        <div class="pad-hist-title">历史版本 · 共 ${history.length} 条（按时间倒序）</div>
        <button class="tl-close" data-close>×</button>
      </div>
      <div class="pad-hist-body">${body}</div>
    </div>
  `;
  document.body.appendChild(overlay);

  function close() { overlay.remove(); }
  overlay.querySelector(".pad-hist-bg").addEventListener("click", close);
  overlay.querySelector("[data-close]").addEventListener("click", close);
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });

  overlay.querySelectorAll(".pad-hist-item").forEach(li => {
    const idx = +li.dataset.idx;
    const item = history[idx];
    li.querySelectorAll("[data-action]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        const action = btn.dataset.action;
        const ta = document.getElementById("pad-content");
        if (!ta) return;
        if (action === "restore") {
          if (!confirm("用这一版替换当前内容？当前内容也会自动留底。")) return;
          ta.value = item.content || "";
          await saveScratchpad();
        } else if (action === "insert") {
          const sep = ta.value && !ta.value.endsWith("\n") ? "\n\n" : "";
          ta.value = ta.value + sep + (item.content || "");
          await saveScratchpad();
        }
        close();
        ta.focus();
      });
    });
  });
}

async function addCustomFlow(dimId) {
  const title = prompt("成就名称（4-6字）：");
  if (!title) return;
  const cond = prompt("解锁条件描述（一句话）：");
  if (!cond) return;
  const rarity = prompt("稀有度：common / uncommon / rare / epic / legendary", "rare") || "rare";
  const vc = prompt("（可选）卡面视觉概念，英文，描述具体画面（用于生图）：", "") || "";
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const r = JSON.parse(await window.pywebview.api.create_custom_achievement(dimId, title, cond, rarity, vc));
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
    todayInfo = j.today || null;
    // 同时拉 arena
    try {
      arenaState = JSON.parse(await window.pywebview.api.get_arena_state());
    } catch (_) { arenaState = null; }
    render();
    // 渲染完后启动数字滚动 + 进度条动画
    requestAnimationFrame(animateArenaProgress);
  } catch (e) {
    document.getElementById("app").innerHTML = `<div class="empty">加载失败：${escapeHTML(String(e))}</div>`;
  }
}

// 侧边栏视图切换
document.querySelectorAll("#dash-side .side-tab").forEach(btn => {
  btn.addEventListener("click", async () => {
    currentView = btn.dataset.view;
    document.querySelectorAll("#dash-side .side-tab").forEach(b => b.classList.toggle("on", b === btn));
    selected = null;
    if (currentView === "notes") await loadScratchpad();
    render();
    document.querySelector(".dash-body").scrollTop = 0;
  });
});

// 侧边栏折叠 / 展开
function setSideCollapsed(collapsed) {
  const side = document.getElementById("dash-side");
  side.classList.toggle("collapsed", collapsed);
  const icon = document.querySelector(".side-collapse-icon");
  if (icon) icon.textContent = collapsed ? "›" : "‹";
  try { localStorage.setItem("side-collapsed", collapsed ? "1" : "0"); } catch (_) {}
}
document.getElementById("side-collapse").addEventListener("click", () => {
  const side = document.getElementById("dash-side");
  setSideCollapsed(!side.classList.contains("collapsed"));
});
// 启动时恢复折叠状态
try {
  if (localStorage.getItem("side-collapsed") === "1") setSideCollapsed(true);
} catch (_) {}
// Ctrl+B 切换
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "b") {
    e.preventDefault();
    const side = document.getElementById("dash-side");
    setSideCollapsed(!side.classList.contains("collapsed"));
  }
});

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

async function warmCards() {
  if (!window.pywebview || !window.pywebview.api) return;
  try {
    const r = JSON.parse(await window.pywebview.api.warm_card_images());
    if (r.status === "ok" && r.queued > 0) console.log(`卡面补生：已排 ${r.queued} 张`);
  } catch (e) { /* ignore */ }
}

async function bootstrap() {
  await load();
  warmCards();
}
window.addEventListener("pywebviewready", bootstrap);
setTimeout(() => { if (window.pywebview && window.pywebview.api && !dims.length) bootstrap(); }, 1000);
setInterval(load, 30000);

// 后端任何写操作完成后会派发这个事件 → 立即拉新数据
window.addEventListener("progress-changed", () => {
  if (window.pywebview && window.pywebview.api) load();
});

// 后端写操作触发解锁时派发 chest-show，弹开箱动画
window.addEventListener("chest-show", (e) => {
  const items = (e.detail || []);
  if (items.length) openChestSequence(items);
});

// ---------- 宝箱开箱动画 ----------

const _chestImgCache = {};
async function fetchChestImage(rarity) {
  const iid = `chest__${rarity}`;
  if (_chestImgCache[iid]) return _chestImgCache[iid];
  if (!window.pywebview || !window.pywebview.api) return "";
  try {
    const r = JSON.parse(await window.pywebview.api.get_card_image(iid));
    if (r.ready && r.data_url) {
      _chestImgCache[iid] = r.data_url;
      return r.data_url;
    }
  } catch (_) {}
  return "";
}

async function fetchCardURL(image_id) {
  if (!image_id) return "";
  if (imageCache[image_id]) return imageCache[image_id];
  try {
    const r = JSON.parse(await window.pywebview.api.get_card_image(image_id));
    if (r.ready && r.data_url) {
      imageCache[image_id] = r.data_url;
      return r.data_url;
    }
  } catch (_) {}
  return "";
}

function openChestSequence(items) {
  if (!items || !items.length) return;
  let idx = 0;

  const overlay = document.createElement("div");
  overlay.className = "chest-overlay";
  overlay.innerHTML = `
    <div class="chest-stage rarity-common">
      <div class="chest-counter">1 / ${items.length}</div>
      <div class="chest-area">
        <div class="chest-aura"></div>
        <img class="chest-img" alt="" />
      </div>
      <div class="chest-hint">点击开启</div>
      <div class="chest-card-wrap"></div>
      <div class="chest-actions">
        <button class="btn btn-secondary chest-skip">跳过</button>
        <button class="btn chest-next" style="display:none">下一个 →</button>
      </div>
    </div>
  `;
  document.body.appendChild(overlay);

  const stage = overlay.querySelector(".chest-stage");
  const counter = overlay.querySelector(".chest-counter");
  const chestArea = overlay.querySelector(".chest-area");
  const chestImg = overlay.querySelector(".chest-img");
  const aura = overlay.querySelector(".chest-aura");
  const hint = overlay.querySelector(".chest-hint");
  const cardWrap = overlay.querySelector(".chest-card-wrap");
  const nextBtn = overlay.querySelector(".chest-next");
  const skipBtn = overlay.querySelector(".chest-skip");

  function close() { overlay.remove(); }

  async function loadChest() {
    const item = items[idx];
    counter.textContent = `${idx + 1} / ${items.length}`;
    stage.className = "chest-stage rarity-" + (item.rarity || "common");
    chestArea.style.display = "flex";
    chestImg.style.display = "block";
    chestImg.classList.remove("shaking", "exploding");
    aura.classList.remove("active", "burst");
    aura.style.display = "block";
    hint.style.display = "block";
    hint.textContent = "点击开启";
    cardWrap.innerHTML = "";
    cardWrap.style.display = "none";
    nextBtn.style.display = "none";
    skipBtn.textContent = "跳过";

    chestImg.src = await fetchChestImage(item.rarity || "common");
    chestImg.onclick = () => openChest(item);
  }

  async function openChest(item) {
    chestImg.onclick = null;
    hint.style.display = "none";
    chestImg.classList.add("shaking");
    aura.classList.add("active");

    // 提前加载卡面图
    const cardUrl = await fetchCardURL(item.image_id);

    setTimeout(() => {
      chestImg.classList.remove("shaking");
      chestImg.classList.add("exploding");
      aura.classList.add("burst");
      setTimeout(() => {
        chestImg.style.display = "none";
        aura.style.display = "none";
        cardWrap.innerHTML = renderRevealCard(item, cardUrl);
        cardWrap.style.display = "block";
        nextBtn.style.display = "inline-block";
        nextBtn.textContent = (idx >= items.length - 1) ? "完成" : `下一个 (${idx + 1}/${items.length})`;
        skipBtn.textContent = "关闭";
      }, 600);
    }, 1500);
  }

  nextBtn.onclick = () => {
    idx++;
    if (idx >= items.length) { close(); }
    else { loadChest(); }
  };
  skipBtn.onclick = close;
  document.addEventListener("keydown", function esc(e) {
    if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
  });

  loadChest();
}

function renderRevealCard(item, cardUrl) {
  const rar = item.rarity || "common";
  const rarMap = { common: "寻常", uncommon: "不凡", rare: "稀有", epic: "史诗", legendary: "传奇" };
  const kindLabel = item.kind === "insight" ? "洞察" : (item.scope === "global" ? "全局" : "里程碑");
  const img = cardUrl
    ? `<img class="reveal-img" src="${cardUrl}" />`
    : `<div class="reveal-img reveal-img-placeholder"></div>`;
  return `
    <div class="reveal-card ${rar}">
      ${img}
      <div class="reveal-tags">
        <span class="reveal-tag">${escapeHTML(kindLabel)}</span>
        <span class="reveal-rar">${rarMap[rar] || "寻常"}</span>
      </div>
      <div class="reveal-title">${escapeHTML(item.title || "")}</div>
      <div class="reveal-desc">${escapeHTML(item.description || "")}</div>
    </div>
  `;
}
