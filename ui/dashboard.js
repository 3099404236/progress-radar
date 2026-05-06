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
let currentView = "active"; // 'active' | 'honored' | 'ignored'

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

  // 全局指标行（基于全部维度统计）
  const totalEntries = dims.reduce((s, x) => s + (x.total_entries || 0), 0);
  const activeDimsHasEntry = dims.filter(x => (x.total_entries || 0) > 0).length;
  const thisWeek = dims.reduce((s, x) => s + (x.heat || []).slice(-7).reduce((a, b) => a + b, 0), 0);

  let h = `<div class="metric-row">
    <div class="metric"><div class="metric-label">Total entries</div><div class="metric-val">${totalEntries}</div></div>
    <div class="metric"><div class="metric-label">Active dimensions</div><div class="metric-val">${activeDimsHasEntry}</div></div>
    <div class="metric"><div class="metric-label">This week activity</div><div class="metric-val">${thisWeek}</div></div>
  </div>`;

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

  if (globalAchievements && (globalAchievements.milestone_total || 0) > 0) {
    h += achievementsBlock(globalAchievements, "__global__", true);
  }

  app.innerHTML = h;

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
    render();
  } catch (e) {
    document.getElementById("app").innerHTML = `<div class="empty">加载失败：${escapeHTML(String(e))}</div>`;
  }
}

// 侧边栏视图切换
document.querySelectorAll("#dash-side .side-tab").forEach(btn => {
  btn.addEventListener("click", () => {
    currentView = btn.dataset.view;
    document.querySelectorAll("#dash-side .side-tab").forEach(b => b.classList.toggle("on", b === btn));
    selected = null;
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
