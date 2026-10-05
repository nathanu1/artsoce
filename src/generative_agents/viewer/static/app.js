// Smallville Lab viewer: plays back recorded frames and inspects a run. Read-only; no model calls.
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
async function api(path) {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}
const pad = (n) => String(n).padStart(2, "0");
const fmtNum = (n) => (n == null ? "—" : Number(n).toLocaleString("en-US"));
const SECTOR_TINTS = ["#DCE5D8", "#E4DDCB", "#D8E0E7", "#E6DADA", "#DDD9E8", "#D6E5E2", "#E8E2D2", "#DEE6D1"];

const S = {
  run: null, map: null, agents: [], byId: {}, step: 0, minStep: -1, maxStep: 0, playing: false, speed: 60,
  selected: null, layers: { labels: true, trails: false, radius: false, eval: false },
  rows: [], keySteps: [], loaded: new Set(), state: {}, trails: {}, timeline: null, tlDay: null,
  tab: "town", base: null, px: 6, lastInspect: 0, convCache: {},
};
const CHUNK = 3600;

// ------------------------------------------------------------------ time helpers
function timeAt(step) {
  const t0 = new Date(S.run.start + "Z");
  return new Date(t0.getTime() + step * S.run.seconds_per_step * 1000);
}
function iso(d) { return d.toISOString().slice(0, 19); }
function dayOf(step) { return iso(timeAt(step)).slice(0, 10); }
function hhmm(isoStr) { return isoStr ? isoStr.slice(11, 16) : ""; }

// ------------------------------------------------------------------ frames
async function ensureFrames(step) {
  const chunk = Math.floor((step + 1) / CHUNK);
  const todo = [chunk, chunk + 1].filter((c) => !S.loaded.has(c) && c * CHUNK - 1 <= S.maxStep);
  for (const c of todo) {
    S.loaded.add(c);
    const start = Math.max(S.minStep, c * CHUNK - 1);
    const end = Math.min(S.maxStep, (c + 1) * CHUNK - 2);
    const data = await api(`/api/frames?start=${start}&end=${end}`);
    const have = new Set(S.rows.map((r) => r.step));
    for (const f of data.frames) if (!have.has(f.step)) S.rows.push(f);
    S.rows.sort((a, b) => a.step - b.step);
    S.keySteps = S.rows.filter((r) => r.key).map((r) => r.step);
  }
}
function lastIndexAtOrBefore(arr, step, get = (x) => x) {
  let lo = 0, hi = arr.length - 1, ans = -1;
  while (lo <= hi) { const mid = (lo + hi) >> 1; if (get(arr[mid]) <= step) { ans = mid; lo = mid + 1; } else hi = mid - 1; }
  return ans;
}
function stateAt(step) {
  const ki = lastIndexAtOrBefore(S.keySteps, step);
  if (ki < 0) return {};
  const kstep = S.keySteps[ki];
  let i = lastIndexAtOrBefore(S.rows, kstep, (r) => r.step);
  const st = {};
  for (; i < S.rows.length && S.rows[i].step <= step; i++) {
    const f = S.rows[i];
    if (f.key) for (const k of Object.keys(st)) delete st[k];
    for (const [aid, v] of Object.entries(f.agents)) st[aid] = v;
  }
  return st;
}

// ------------------------------------------------------------------ map
function decodeRLE(rle, size) {
  const out = new Int32Array(size); let i = 0;
  for (const [v, n] of rle) { out.fill(v, i, i + n); i += n; }
  return out;
}
function buildBase() {
  const m = S.map, canvas = $("#map");
  const cssW = canvas.parentElement.clientWidth;
  const dpr = window.devicePixelRatio || 1;
  S.px = Math.max(3, Math.floor((cssW * dpr) / m.width));
  const W = m.width * S.px, H = m.height * S.px;
  canvas.width = W; canvas.height = H;
  canvas.style.height = `${(H / W) * cssW}px`;
  const off = document.createElement("canvas"); off.width = W; off.height = H;
  const g = off.getContext("2d");
  g.fillStyle = "#E6EBE4"; g.fillRect(0, 0, W, H);
  const sec = decodeRLE(m.sector_layer, m.width * m.height), col = decodeRLE(m.collision, m.width * m.height);
  for (let y = 0; y < m.height; y++) for (let x = 0; x < m.width; x++) {
    const i = y * m.width + x;
    if (col[i]) { g.fillStyle = "#9DAAA0"; g.fillRect(x * S.px, y * S.px, S.px, S.px); }
    else if (sec[i]) { g.fillStyle = SECTOR_TINTS[sec[i] % SECTOR_TINTS.length]; g.fillRect(x * S.px, y * S.px, S.px, S.px); }
  }
  g.font = `600 ${Math.max(10, S.px * 1.5)}px 'Schibsted Grotesk', sans-serif`;
  g.textAlign = "center"; g.lineJoin = "round"; g.textBaseline = "middle";
  for (const s of m.sectors) {
    const boxW = (s.x1 - s.x0 + 1) * S.px;
    let name = s.name.replace(/'s apartment$/, "'s apt").replace(/'s house$/, "'s house");
    while (name.length > 4 && g.measureText(name).width > boxW * 1.05) name = name.slice(0, -2);
    if (name !== s.name.replace(/'s apartment$/, "'s apt")) name = name.replace(/\s+\S{0,2}$/, "") + "…";
    if (g.measureText(name).width > boxW * 1.1 || name.length < 5) continue;
    const cx = ((s.x0 + s.x1 + 1) / 2) * S.px, cy = (s.y0 + 1.2) * S.px;
    g.lineWidth = 4; g.strokeStyle = "rgba(251,252,250,0.92)"; g.strokeText(name, cx, cy);
    g.fillStyle = "#3B4943"; g.fillText(name, cx, cy);
  }
  S.base = off;
}
function drawMap() {
  if (!S.base) return;
  const c = $("#map"), g = c.getContext("2d"), P = S.px;
  g.drawImage(S.base, 0, 0);
  if (S.layers.eval && S.run.evaluator_events) {
    for (const ev of S.run.evaluator_events) {
      const box = S.map.sectors.find((s) => s.address === ev.place);
      if (!box) continue;
      g.save(); g.setLineDash([6, 4]); g.lineWidth = 3; g.strokeStyle = "#6B3E9B";
      g.strokeRect(box.x0 * P, box.y0 * P, (box.x1 - box.x0 + 1) * P, (box.y1 - box.y0 + 1) * P); g.restore();
      g.font = `600 ${Math.max(10, P * 1.5)}px 'IBM Plex Mono', monospace`; g.fillStyle = "#6B3E9B"; g.textAlign = "left";
      g.fillText(`EVALUATOR ONLY · ${ev.label} · ${ev.window ? ev.window.join(" – ") : ""}`, box.x0 * P, box.y0 * P - 6);
    }
  }
  if (S.layers.trails) {
    for (const [aid, pts] of Object.entries(S.trails)) {
      if (pts.length < 2) continue;
      g.save(); g.setLineDash([2, 5]); g.lineWidth = 2.5; g.strokeStyle = S.byId[aid]?.color || "#333"; g.lineCap = "round";
      g.beginPath(); pts.forEach(([x, y], i) => (i ? g.lineTo : g.moveTo).call(g, (x + 0.5) * P, (y + 0.5) * P)); g.stroke(); g.restore();
    }
  }
  const sel = S.selected && S.state[S.selected];
  if (S.layers.radius && sel && sel[0] != null) {
    const r = S.byId[S.selected]?.vision_r ?? 8;
    g.save(); g.fillStyle = "rgba(180,70,28,0.08)"; g.strokeStyle = "#B4461C"; g.setLineDash([5, 4]); g.lineWidth = 2;
    g.fillRect((sel[0] - r) * P, (sel[1] - r) * P, (2 * r + 1) * P, (2 * r + 1) * P);
    g.strokeRect((sel[0] - r) * P, (sel[1] - r) * P, (2 * r + 1) * P, (2 * r + 1) * P); g.restore();
  }
  const R = Math.max(7, P * 1.15);
  for (const a of S.agents) {
    const v = S.state[a.id]; if (!v || v[0] == null) continue;
    const x = (v[0] + 0.5) * P, y = (v[1] + 0.5) * P;
    if (S.layers.labels || a.id === S.selected) {
      const text = (v[3] === "conversation" ? "💬 " : "") + (v[2] || (v[3] === "failed" ? "(action failed)" : "idle"));
      const t = text.length > 34 ? text.slice(0, 33) + "…" : text;
      g.font = `${Math.max(10, P * 1.45)}px 'IBM Plex Mono', monospace`;
      const w = g.measureText(t).width + 10;
      g.fillStyle = a.id === S.selected ? "rgba(22,33,27,0.92)" : "rgba(251,252,250,0.9)";
      g.fillRect(x + R + 3, y - R * 0.7, w, R * 1.4);
      g.fillStyle = a.id === S.selected ? "#FBFCFA" : "#16211B"; g.textAlign = "left"; g.textBaseline = "middle";
      g.fillText(t, x + R + 8, y + 1);
    }
    g.beginPath(); g.arc(x, y, R, 0, Math.PI * 2); g.fillStyle = a.color; g.fill();
    g.lineWidth = a.id === S.selected ? 3 : 1.5; g.strokeStyle = a.id === S.selected ? "#B4461C" : "#FBFCFA"; g.stroke();
    g.fillStyle = "#fff"; g.font = `600 ${Math.max(9, R * 0.95)}px 'IBM Plex Mono', monospace`; g.textAlign = "center"; g.textBaseline = "middle";
    g.fillText(a.initials, x, y + 1);
  }
}

// ------------------------------------------------------------------ playback
async function seek(step, { fromPlay = false } = {}) {
  step = Math.max(S.minStep, Math.min(S.maxStep, step));
  await ensureFrames(step);
  const prev = S.state;
  S.step = step;
  S.state = stateAt(step);
  for (const [aid, v] of Object.entries(S.state)) {
    if (v[0] == null) continue;
    const tr = (S.trails[aid] ||= []);
    const last = tr[tr.length - 1];
    if (!fromPlay) tr.length = 0;
    if (!last || last[0] !== v[0] || last[1] !== v[1]) tr.push([v[0], v[1]]);
    if (tr.length > 80) tr.shift();
  }
  void prev;
  const t = timeAt(step);
  $("#clock").textContent = `${pad(t.getUTCHours())}:${pad(t.getUTCMinutes())}:${pad(t.getUTCSeconds())}`;
  $("#clockdate").textContent = `${t.toUTCString().slice(0, 16)} · step ${fmtNum(step)} · ${S.playing ? "playing" : "paused"}`;
  $("#scrub").value = String(step);
  drawMap();
  if (S.tlDay !== dayOf(step)) await loadTimeline(dayOf(step)); else renderTimeline();
  const now = performance.now();
  if (!fromPlay || now - S.lastInspect > 1500) { S.lastInspect = now; renderInspector(); }
}
function setPlaying(p) {
  S.playing = p;
  $("#btn-play").textContent = p ? "❚❚" : "▶︎";
  $("#btn-play").setAttribute("aria-label", p ? "Pause" : "Play");
  if (p) requestAnimationFrame(tick);
}
let lastTick = 0;
async function tick(ts) {
  if (!S.playing) return;
  if (!lastTick) lastTick = ts;
  const dt = (ts - lastTick) / 1000; lastTick = ts;
  const adv = Math.max(1, Math.round(S.speed * dt));
  if (S.step >= S.maxStep) { setPlaying(false); return; }
  await seek(S.step + adv, { fromPlay: true });
  requestAnimationFrame(tick);
}

// ------------------------------------------------------------------ timeline
async function loadTimeline(day) {
  S.tlDay = day;
  S.timeline = await api(`/api/timeline?day=${day}`);
  $("#tl-day").textContent = `${day} · 00:00–24:00`;
  renderTimeline();
}
function minutesOf(isoStr) { return Number(isoStr.slice(11, 13)) * 60 + Number(isoStr.slice(14, 16)) + Number(isoStr.slice(17, 19) || 0) / 60; }
function renderTimeline() {
  const tl = S.timeline; if (!tl) return;
  const nowIso = iso(timeAt(S.step)); const sameDay = nowIso.slice(0, 10) === S.tlDay; const nowMin = minutesOf(nowIso);
  const ticks = Array.from({ length: 13 }, (_, i) => `<span style="left:${(i * 2 * 60 / 1440) * 100}%">${pad(i * 2)}</span>`).join("");
  let html = `<div class="hours"><span></span><div class="ticks">${ticks}</div></div>`;
  for (const a of S.agents) {
    const lane = tl.lanes[a.id] || { blocks: [], marks: [] };
    const blocks = lane.blocks.map((b) => {
      const s = b.start.slice(0, 10) === S.tlDay ? minutesOf(b.start) : 0; const w = b.minutes;
      const past = sameDay ? s + w <= nowMin : S.tlDay < nowIso.slice(0, 10);
      return `<div class="blk ${past ? "past" : ""}" style="left:${(s / 1440) * 100}%;width:${(w / 1440) * 100}%" title="${esc(hhmm(b.start))} ${esc(b.activity)} (${w} min)">${esc(b.activity)}</div>`;
    }).join("");
    const marks = lane.marks.map((m) => `<div class="mk ${m.type}" style="left:${(minutesOf(m.t) / 1440) * 100}%" title="${esc(hhmm(m.t))} ${esc(m.type)}: ${esc(m.label || "")}"></div>`).join("");
    const now = sameDay ? `<div class="now" style="left:${(nowMin / 1440) * 100}%"></div>` : "";
    html += `<div class="lane"><button class="who" data-pick="${a.id}"><span class="chip" style="background:${a.color}">${a.initials}</span>${esc(a.name.split(" ")[0])}</button><div class="track" data-lane="${a.id}">${blocks}${marks}${now}</div></div>`;
  }
  $("#lanes").innerHTML = html;
}

// ------------------------------------------------------------------ inspector
function roster() {
  $("#roster").innerHTML = S.agents.map((a) => `<button data-pick="${a.id}" aria-pressed="${a.id === S.selected}"><span class="chip" style="background:${a.color}">${a.initials}</span>${esc(a.name.split(" ")[0])}</button>`).join("");
}
function scoreBar(c) {
  const w = c.weighted || {}; const tot = (w.recency || 0) + (w.importance || 0) + (w.relevance || 0) || 1; const max = 3;
  return `<div class="scorebar" title="recency ${(w.recency ?? 0).toFixed(2)} · importance ${(w.importance ?? 0).toFixed(2)} · relevance ${(w.relevance ?? 0).toFixed(2)}" style="width:${Math.min(100, (tot / max) * 100)}%"><span class="r" style="width:${((w.recency || 0) / tot) * 100}%"></span><span class="i" style="width:${((w.importance || 0) / tot) * 100}%"></span><span class="v" style="width:${((w.relevance || 0) / tot) * 100}%"></span></div>`;
}
async function renderInspector() {
  const aid = S.selected; if (!aid) return;
  roster();
  const before = iso(timeAt(S.step));
  const [info, traces] = await Promise.all([api(`/api/agent/${aid}?step=${S.step}`), api(`/api/agent/${aid}/traces?limit=1&before=${before}`)]);
  const trace = traces[0] ? await api(`/api/trace/${traces[0].id}`) : null;
  if (!S.convCache[aid]) S.convCache[aid] = await api(`/api/conversations?agent=${aid}`);
  const id = info.identity, v = S.state[aid] || [];
  const nowMin = minutesOf(before);
  const plan = info.hours.map((h) => {
    const s = minutesOf(h.start), cur = before.slice(0, 10) === info.day && s <= nowMin && nowMin < s + h.duration_min;
    const tasks = cur && h.tasks.length ? `<ul class="tasks">${h.tasks.filter((t) => t.status !== "superseded").map((t) => { const ts = minutesOf(t.start); const tc = ts <= nowMin && nowMin < ts + t.duration_min; return `<li class="${tc ? "cur" : ""}"><span class="t">${hhmm(t.start)}</span><span>${esc(t.description)}</span><span class="t">${t.duration_min}m</span></li>`; }).join("")}</ul>` : "";
    return `<li class="${cur ? "cur" : ""}"><span class="t">${hhmm(h.start)}</span><span>${esc(h.description)}</span>${tasks}</li>`;
  }).join("");
  const mems = trace ? trace.candidates.filter((c) => c.delivered).slice(0, 5).map((c) => `<div class="mem"><div class="meta"><span><span class="kind ${c.kind}">${c.kind}</span> ${esc(c.id)}</span><span>#${c.rank}</span></div><div>${esc(c.description)}</div><div class="scoreline">${scoreBar(c)}<b>${c.score.toFixed(2)}</b></div></div>`).join("") : `<div class="empty">no retrieval yet</div>`;
  const acc = info.state.reflection_accumulator ?? 0, thr = info.state.reflection_threshold;
  const convs = S.convCache[aid].filter((c) => c.started_at <= before).slice(-6).reverse();
  const partner = (c) => c.participants.filter((p) => p !== aid).map((p) => S.byId[p]?.name || p).join(", ");
  $("#inspect").innerHTML = `
    <div class="card"><h3>${esc(id.name)}</h3><div class="where">${esc(id.age)} · ${esc(id.innate)}</div><p style="margin:6px 0">${esc(id.learned)}</p><div class="where">home: ${esc(id.living_area)}</div></div>
    <div class="card"><div class="ttl"><span>Now</span><span>${esc({ plan: "following its plan", conversation: "in a conversation", wait: "waiting", failed: "action failed", idle: "idle" }[v[3]] || "")}</span></div><div class="now-act">${esc(v[2] || (v[3] === "failed" ? "action failed (see events)" : "idle"))}</div><div class="where">${esc(v[4] || "")}</div>${v[5] ? `<button class="linkbtn" data-conv="${v[5]}">open conversation ${esc(v[5])}</button>` : ""}</div>
    <div class="card"><div class="ttl"><span>Plan for ${esc(info.day || "")}</span><span>${info.hours.length} blocks</span></div><ol class="plan">${plan || '<li class="empty">no plan yet</li>'}</ol></div>
    <div class="card"><div class="ttl"><span>Retrieved for the last decision</span><button class="linkbtn" data-goto-trace="${trace ? trace.id : ""}">explain</button></div>${trace ? `<div class="where">query: ${esc(trace.query)} · ${esc(trace.purpose)} · ${hhmm(trace.sim_time)}</div>` : ""}<div class="legend" style="margin:4px 0"><span><i class="sw" style="background:var(--rec)"></i>recency</span><span><i class="sw" style="background:var(--imp)"></i>importance</span><span><i class="sw" style="background:var(--rel)"></i>relevance</span></div>${mems}</div>
    <div class="card"><div class="ttl"><span>Reflection trigger</span><span class="mono">${acc.toFixed(0)} / ${thr}</span></div><div class="meter" role="meter" aria-valuemin="0" aria-valuemax="${thr}" aria-valuenow="${acc}"><div style="width:${Math.min(100, (acc / thr) * 100)}%"></div></div><div class="note">Importance of newly perceived memories since the last reflection; reflects when the sum exceeds ${thr}. ${info.state.reflections_done || 0} reflections so far. ${esc(info.state.note)}.</div></div>
    <div class="card"><div class="ttl"><span>Memory</span><span>${Object.entries(info.memory_counts).map(([k, n]) => `${k} ${n}`).join(" · ")}</span></div><div class="ttl"><span>Known places</span><span>${info.known_places.length} areas</span></div><div class="where">${info.known_places.map((p) => esc(p.sector)).join(" · ")}</div></div>
    <div class="card"><div class="ttl"><span>Conversations</span><span>${S.convCache[aid].length} total</span></div>${convs.map((c) => `<div class="mem"><div class="meta"><span>${hhmm(c.started_at)} ${c.started_at.slice(5, 10)} · ${esc(partner(c))}</span><span>${c.utterances} lines</span></div><button class="linkbtn" data-conv="${c.id}">${esc(c.summary || c.id)}</button></div>`).join("") || '<div class="empty">none yet</div>'}</div>`;
}
async function openConversation(cid) {
  const c = await api(`/api/conversation/${cid}`);
  $("#dlg-body").innerHTML = `<h3>${esc(c.id)} · ${c.participants.map((p) => esc(S.byId[p]?.name || p)).join(" & ")}</h3><div class="where">${esc(c.started_at)} · ${esc(c.location || "")} · ${esc(c.status)} (${esc(c.reason || "")})</div><p><i>${esc(c.summary || "")}</i></p>${c.utterances.map((u) => `<div class="utt"><b style="color:${S.byId[u.speaker_id]?.color}">${esc(S.byId[u.speaker_id]?.name || u.speaker_id)}:</b> ${esc(u.text)}</div>`).join("")}<p class="note">Only the two participants stored these lines; bystanders perceived only that they were chatting.</p>`;
  $("#dlg").showModal();
}

// ------------------------------------------------------------------ retrieval tab
function agentOptions(sel) { sel.innerHTML = S.agents.map((a) => `<option value="${a.id}" ${a.id === S.selected ? "selected" : ""}>${esc(a.name)}</option>`).join(""); }
async function loadTraces(focus) {
  const aid = $("#rt-agent").value;
  const list = await api(`/api/agent/${aid}/traces?limit=150&before=${iso(timeAt(S.step))}`);
  $("#rt-list").innerHTML = list.map((t) => `<button data-trace="${t.id}" aria-pressed="${t.id === focus}"><span class="mono">${t.sim_time.slice(5, 16).replace("T", " ")}</span> · ${esc(t.purpose)}<br><span class="where">${esc(t.query.slice(0, 80))}</span> <span class="where">(${t.delivered}/${t.candidates})</span></button>`).join("") || '<div class="empty">no traces</div>';
  if (focus || list[0]) showTrace(focus || list[0].id);
}
async function showTrace(id) {
  $$("#rt-list button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.trace === id));
  const t = await api(`/api/trace/${id}`);
  const ex = t.explain_top2;
  const rows = t.candidates.map((c) => `<tr class="${c.delivered ? "" : "undelivered"}"><td class="num">${c.rank}${c.delivered ? "✓" : ""}</td><td><span class="kind ${c.kind}">${c.kind}</span></td><td>${esc(c.description)}</td><td class="num">${c.raw.recency == null ? "—" : Number(c.raw.recency).toFixed(3)}</td><td class="num">${c.raw.importance}</td><td class="num">${c.raw.relevance == null ? "—" : Number(c.raw.relevance).toFixed(3)}</td><td>${scoreBar(c)}</td><td class="num"><b>${c.score.toFixed(3)}</b></td></tr>`).join("");
  $("#rt-detail").innerHTML = `<div class="callout">query <b>${esc(t.query)}</b> · ${esc(t.purpose)} · at ${esc(t.sim_time)} · mode ${esc(t.mode)} · weights ${esc(JSON.stringify(t.weights))} · budget ${t.budget_tokens ?? "none"} tokens (used ${t.used_tokens}) · ${t.candidates_total} eligible, ${t.delivered.length} delivered${t.candidates_truncated ? `, top ${t.candidates.length} kept in the trace` : ""} · ${t.excluded.length} excluded</div>
  ${ex ? `<p><b>Why ${esc(ex.a)} outranked ${esc(ex.b)}:</b> score difference ${ex.score_difference.toFixed(3)}; largest push from <b>${ex.largest_push}</b> (${Object.entries(ex.difference).map(([k, v]) => `${k} ${v >= 0 ? "+" : ""}${v.toFixed(3)}`).join(", ")}).</p>` : ""}
  <table><thead><tr><th class="num">rank</th><th>kind</th><th>memory</th><th class="num">recency raw</th><th class="num">importance</th><th class="num">cosine</th><th>weighted components</th><th class="num">score</th></tr></thead><tbody>${rows}</tbody></table>`;
}

// ------------------------------------------------------------------ reflections tab
async function loadReflections() {
  const aid = $("#rf-agent").value;
  const list = await api(`/api/agent/${aid}/reflections`);
  $("#rf-list").innerHTML = list.map((r) => `<button data-refl="${r.id}"><span class="mono">${r.created_at.slice(5, 16).replace("T", " ")}</span> · depth ${r.depth}<br>${esc(r.description)}<br><span class="where">${esc(r.question || "")}</span></button>`).join("") || '<div class="empty">no reflections</div>';
  if (list[0]) showTree(list[0].id);
}
function treeHTML(n) {
  if (n.missing || n.cycle) return `<li class="where">${esc(n.id)} ${n.cycle ? "(cycle!)" : "(missing)"}</li>`;
  return `<li><span class="kind ${n.kind}">${n.kind}</span> <span class="where">${esc(n.id)} · ${esc(n.created_at.slice(5, 16))} · importance ${n.importance}</span><div>${esc(n.description)}</div>${n.evidence && n.evidence.length ? `<ul class="tree">${n.evidence.map(treeHTML).join("")}</ul>` : ""}</li>`;
}
async function showTree(id) {
  $$("#rf-list button").forEach((b) => b.setAttribute("aria-pressed", b.dataset.refl === id));
  const t = await api(`/api/evidence/${id}`);
  $("#rf-tree").innerHTML = `<ul class="tree tree-root">${treeHTML(t)}</ul>`;
}

// ------------------------------------------------------------------ social tab
function network(nodes, edges, { directed = false, highlight = null, size = 380 } = {}) {
  const c = size / 2, r = size / 2 - 60;
  const pos = Object.fromEntries(nodes.map((n, i) => [n, [c + r * Math.cos((2 * Math.PI * i) / nodes.length - Math.PI / 2), c + r * Math.sin((2 * Math.PI * i) / nodes.length - Math.PI / 2)]]));
  const lines = edges.filter(([a, b]) => pos[a] && pos[b]).map(([a, b]) => { const [x1, y1] = pos[a]; let [x2, y2] = pos[b]; if (directed) { const d = Math.hypot(x2 - x1, y2 - y1) || 1; x2 -= ((x2 - x1) * 10) / d; y2 -= ((y2 - y1) * 10) / d; } return `<line x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}" stroke="#2353AC" stroke-width="1.5" ${directed ? 'marker-end="url(#arr)"' : ""}/>`; }).join("");
  const dots = nodes.map((n) => { const [x, y] = pos[n]; const a = S.byId[n]; return `<circle cx="${x}" cy="${y}" r="8" fill="${n === highlight ? "#B4461C" : a?.color || "#FBFCFA"}" stroke="#16211B"/><text x="${x}" y="${y + 21}" text-anchor="middle" font-size="10" font-family="IBM Plex Mono">${esc((a?.name || n).split(" ")[0])}</text>`; }).join("");
  return `<svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" role="img"><defs><marker id="arr" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="#2353AC"/></marker></defs>${lines}${dots}</svg>`;
}
async function renderSocial() {
  const ev = await api("/api/evaluation");
  const el = $("#social");
  if (!ev.summary) { el.innerHTML = `<h2>Social measures</h2><p class="empty">This run has not been evaluated yet. Run <code>ga evaluate --run-dir ${esc(S.run.run_dir || "…")}</code> and reload.</p>`; return; }
  const s = ev.summary;
  const dif = Object.entries(s.snapshots).flatMap(([snap, v]) => Object.entries(v.diffusion).map(([k, d]) => `<tr><td>${snap}</td><td>${k}</td><td class="num">${d.claimed}/${d.n}</td><td class="num">${d.supported_aware}/${d.n}</td><td class="num">${d.newly_informed_supported}</td><td class="num">${d.claimed_unsupported}</td><td class="num">${d.retrieval_failures}</td></tr>`)).join("");
  const agents = S.agents.map((a) => a.id);
  const trans = (ev.transmissions || []);
  const firstBy = {};
  const originators = Object.fromEntries((s.originators ? Object.entries(s.originators) : []));
  for (const t of trans) { const k = `${t.event}|${t.receiver}`; if (!firstBy[k] && t.receiver !== originators[t.event]) firstBy[k] = t; }
  const events = [...new Set(trans.map((t) => t.event))];
  const graphs = events.map((e) => `<div><h3>${esc(e)}: first transmissions</h3>${network(agents, Object.values(firstBy).filter((t) => t.event === e).map((t) => [t.sender, t.receiver]), { directed: true })}</div>`).join("");
  const fin = s.snapshots.final?.relationships;
  const relEdges = fin ? fin.edges_supported : [];
  const rels = Object.entries(s.snapshots).filter(([, v]) => v.relationships).map(([k, v]) => `<tr><td>${k}</td><td class="num">${v.relationships.density_supported ?? "—"}</td><td class="num">${v.relationships.density_claimed ?? "—"}</td><td class="num">${v.relationships.hallucinated}</td><td class="num">${v.relationships.observed_only}</td></tr>`).join("");
  const yn = (x) => (x === "True" || x === true ? "yes" : "—");
  const att = (ev.attendance || []).map((r) => `<tr><td>${esc(S.byId[r.agent_id]?.name || r.agent_id)}${r.host === "True" ? " (host)" : ""}</td><td>${yn(r.exposed)}</td><td>${yn(r.invited)}</td><td>${yn(r.accepted)}</td><td>${yn(r.scheduled)}</td><td class="num">${r.present_minutes}</td><td><b>${yn(r.attended)}</b></td></tr>`).join("");
  const fails = Object.entries(ev.failures || {}).map(([k, v]) => `<details><summary><b>${esc(k)}</b> · ${v.count} · <span class="where">${esc(v.rule)}</span></summary><pre class="where" style="white-space:pre-wrap">${esc(JSON.stringify(v.examples, null, 1))}</pre></details>`).join("");
  el.innerHTML = `<div class="panel-head"><div><h2>Social measures</h2><span class="hint">probes on snapshot clones; claims are checked against each agent's own memory</span></div></div>
  ${S.run.mode !== "live" ? `<p class="callout">${S.run.mode.toUpperCase()} run: these numbers show the measurement pipeline working on fixture behavior, not findings.</p>` : ""}
  <div class="grid2"><div><h3>Information diffusion</h3><table><thead><tr><th>snapshot</th><th>event</th><th class="num">claimed</th><th class="num">claimed + supported</th><th class="num">newly informed</th><th class="num">unsupported</th><th class="num">evidence denied</th></tr></thead><tbody>${dif}</tbody></table>
  <h3 style="margin-top:12px">Relationships</h3><table><thead><tr><th>snapshot</th><th class="num">density (mutual, supported)</th><th class="num">density (claims only)</th><th class="num">no evidence</th><th class="num">seen only</th></tr></thead><tbody>${rels}</tbody></table>
  ${fin ? network(agents, relEdges) : ""}</div><div>${graphs}</div></div>
  ${att ? `<h3>Party attendance (physical presence; host excluded from guest denominators)</h3><table><thead><tr><th>agent</th><th>exposed</th><th>invited</th><th>said yes</th><th>scheduled</th><th class="num">minutes present</th><th>attended</th></tr></thead><tbody>${att}</tbody></table>` : `<p class="empty">Attendance: ${esc((s.not_measured || []).join("; ") || "not measured")}</p>`}
  <h3>Failure taxonomy</h3>${fails}`;
}

// ------------------------------------------------------------------ interviews tab
async function renderInterviews() {
  const sets = await api("/api/interviews");
  const el = $("#interviews");
  const names = Object.keys(sets);
  if (!names.length) { el.innerHTML = `<h2>Interviews</h2><p class="empty">No interviews yet. Run <code>ga interview --run-dir … --snapshot final</code>.</p>`; return; }
  const name = el.dataset.set && sets[el.dataset.set] ? el.dataset.set : names[0];
  const set = sets[name];
  const qids = [...new Set(set.responses.map((r) => r.question_id))];
  const qid = el.dataset.q && qids.includes(el.dataset.q) ? el.dataset.q : qids[0];
  const conds = [...new Set(set.responses.map((r) => r.condition))];
  const byAgent = {};
  for (const r of set.responses.filter((r) => r.question_id === qid)) (byAgent[r.agent_id] ||= {})[r.condition] = r;
  const an = set.analysis;
  el.innerHTML = `<div class="panel-head"><div><h2>Matched-history interviews</h2><span class="hint">${esc(name)} · reference time ${esc(set.manifest.reference_time)} · bank ${esc(set.manifest.bank?.name)} · human answers only when imported</span></div>
   <div><select id="iv-set">${names.map((n) => `<option ${n === name ? "selected" : ""}>${esc(n)}</option>`).join("")}</select> <select id="iv-q">${qids.map((q) => `<option value="${q}" ${q === qid ? "selected" : ""}>${q}</option>`).join("")}</select></div></div>
   ${S.run.mode !== "live" ? `<p class="callout">${S.run.mode.toUpperCase()} answers come from the offline fixture model.</p>` : ""}
   ${Object.entries(byAgent).map(([aid, rs]) => `<h3 style="margin-top:12px">${esc(S.byId[aid]?.name || aid)}: ${esc(Object.values(rs)[0].question)}</h3><div class="answers">${conds.map((c) => rs[c] ? `<div class="a"><div class="c">${esc(c)} · ${Object.entries(rs[c].retrieved_kinds || {}).map(([k, n]) => `${k} ${n}`).join(", ") || "no memories"}</div>${esc(rs[c].answer)}</div>` : "").join("")}</div>`).join("")}
   ${an && an.computed ? `<h3>Human ratings analysis (${an.raters} raters)</h3><table><thead><tr><th>condition</th><th class="num">TrueSkill μ</th><th class="num">σ</th></tr></thead><tbody>${Object.entries(an.trueskill).map(([c, v]) => `<tr><td>${esc(c)}</td><td class="num">${v.mu}</td><td class="num">${v.sigma}</td></tr>`).join("")}</tbody></table><p class="note">Kruskal–Wallis H = ${an.kruskal_dunn.H?.toFixed?.(2)}, p = ${an.kruskal_dunn.p?.toExponential?.(2)} (authors' method). Friedman (our addition): ${an.friedman_wilcoxon_ours.computed ? `χ² = ${an.friedman_wilcoxon_ours.chi2.toFixed(2)}` : esc(an.friedman_wilcoxon_ours.reason)}.</p>` : `<p class="note">No human rating data imported; no believability statistics are shown.</p>`}`;
  $("#iv-set").onchange = (e) => { el.dataset.set = e.target.value; el.dataset.q = ""; renderInterviews(); };
  $("#iv-q").onchange = (e) => { el.dataset.q = e.target.value; renderInterviews(); };
}

// ------------------------------------------------------------------ experiment tab
async function renderExperiment() {
  const ex = await api("/api/experiment");
  const el = $("#experiment");
  if (!ex.runs) { el.innerHTML = `<h2>Experiment</h2><p class="empty">Start the viewer with <code>--experiment runs/experiments/NAME</code> to compare independent runs.</p>`; return; }
  const cols = ["run_id", "condition", "seed", "status", "supported_party_recall", "supported_candidacy_recall", "invited_attendance_rate", "unsupported_claims", "calls", "runtime_s"];
  const comps = Object.entries(ex.summary?.comparisons || {}).map(([k, v]) => `<li><b>${esc(k)}</b>: ${esc(v.difference)} = ${v.mean_difference} (bootstrap 95% CI ${esc(JSON.stringify(v.bootstrap_95ci))}, permutation p = ${v.permutation_p}, n = ${esc(JSON.stringify(v.n))}) — ${esc(v.note)}</li>`).join("");
  el.innerHTML = `<h2>Experiment: ${esc(ex.summary?.protocol || ex.dir)}</h2><p class="note">Unit of analysis: the run. Five runs per condition are exploratory.</p><table><thead><tr>${cols.map((c) => `<th>${c}</th>`).join("")}</tr></thead><tbody>${ex.runs.map((r) => `<tr>${cols.map((c) => `<td>${esc(r[c])}</td>`).join("")}</tr>`).join("")}</tbody></table><ul>${comps}</ul>`;
}

// ------------------------------------------------------------------ wiring
function strip() {
  const r = S.run, u = r.usage || {}, lim = r.limits || {};
  const badge = r.replay_of ? `<span class="badge replay" title="Replay of recorded responses; no model calls">REPLAY</span>` : (r.mock_llm || r.mock_embeddings) ? `<span class="badge mock" title="Offline fixtures: deterministic mock model and/or hash embeddings. Not semantic results.">MOCK</span>` : `<span class="badge live">LIVE</span>`;
  $("#strip").innerHTML = `<span>${badge}<b>${esc(r.run_id)}</b></span><span>Scenario <b>${esc(r.scenario)}</b> · ${r.population} agents</span><span>Status <b>${esc(r.status)}</b></span><span>Tick <b>${esc(r.settings.tick)}</b></span><span>Retrieval <b>${esc(r.settings.retrieval)}</b></span><span>Reflection <b>${esc(r.settings.reflection)}</b></span><span>Constraints <b>${esc(r.settings.constraints)}</b></span><span>Model <b>${esc(r.settings.model)}</b></span><span>Calls <b>${fmtNum(u.calls)}${lim.max_calls ? " / " + fmtNum(lim.max_calls) : ""}</b></span><span>Tokens <b>${fmtNum(u.input_tokens)} in · ${fmtNum(u.output_tokens)} out</b></span><span>Cost <b>${u.cost_usd == null ? "unpriced" : "$" + Number(u.cost_usd).toFixed(2)}</b></span>`;
}
function showTab(tab) {
  S.tab = tab;
  $$(".tabs button").forEach((b) => (b.dataset.tab === tab ? b.setAttribute("aria-current", "page") : b.removeAttribute("aria-current")));
  $$("main.tab").forEach((m) => (m.hidden = m.id !== `tab-${tab}`));
  if (tab === "retrieval") { agentOptions($("#rt-agent")); loadTraces(); }
  if (tab === "reflections") { agentOptions($("#rf-agent")); loadReflections(); }
  if (tab === "social") renderSocial();
  if (tab === "interviews") renderInterviews();
  if (tab === "experiment") renderExperiment();
}
function select(aid) { S.selected = aid; roster(); drawMap(); renderInspector(); }

document.addEventListener("click", (e) => {
  const t = e.target.closest("[data-pick],[data-conv],[data-trace],[data-refl],[data-goto-trace],[data-tab],[data-lane],.toggle");
  if (!t) return;
  if (t.dataset.pick) select(t.dataset.pick);
  else if (t.dataset.conv) openConversation(t.dataset.conv);
  else if (t.dataset.trace) showTrace(t.dataset.trace);
  else if (t.dataset.refl) showTree(t.dataset.refl);
  else if (t.dataset.gotoTrace !== undefined && t.dataset.gotoTrace) { showTab("retrieval"); $("#rt-agent").value = S.selected; loadTraces(t.dataset.gotoTrace); }
  else if (t.dataset.tab) showTab(t.dataset.tab);
  else if (t.dataset.lane) {
    const rect = t.getBoundingClientRect(); const frac = (e.clientX - rect.left) / rect.width;
    const target = new Date(S.tlDay + "T00:00:00Z").getTime() + frac * 86400000;
    const step = Math.round((target - new Date(S.run.start + "Z").getTime()) / (S.run.seconds_per_step * 1000));
    seek(step);
  } else if (t.classList.contains("toggle")) {
    const k = t.dataset.layer; S.layers[k] = !S.layers[k]; t.setAttribute("aria-pressed", S.layers[k]); drawMap();
  }
});
$("#map").addEventListener("click", (e) => {
  const c = $("#map"), rect = c.getBoundingClientRect();
  const x = ((e.clientX - rect.left) / rect.width) * S.map.width, y = ((e.clientY - rect.top) / rect.height) * S.map.height;
  let best = null, bd = 3;
  for (const [aid, v] of Object.entries(S.state)) { if (v[0] == null) continue; const d = Math.hypot(v[0] + 0.5 - x, v[1] + 0.5 - y); if (d < bd) { bd = d; best = aid; } }
  if (best) select(best);
});
$("#btn-play").onclick = () => setPlaying(!S.playing);
$("#btn-step").onclick = () => { setPlaying(false); seek(S.step + 1); };
$("#btn-back").onclick = () => { setPlaying(false); seek(S.step - 1); };
$("#speed").onchange = (e) => (S.speed = Number(e.target.value));
$("#scrub").oninput = (e) => seek(Number(e.target.value));
$("#rt-agent").onchange = () => loadTraces();
$("#rf-agent").onchange = () => loadReflections();
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, select, textarea")) return;
  if (e.code === "Space") { e.preventDefault(); setPlaying(!S.playing); }
  if (e.code === "ArrowRight") seek(S.step + (e.shiftKey ? 60 : 1));
  if (e.code === "ArrowLeft") seek(S.step - (e.shiftKey ? 60 : 1));
});
window.addEventListener("resize", () => { buildBase(); drawMap(); });

async function follow() {
  try {
    const r = await api("/api/run");
    if (r.last_frame != null && r.last_frame > S.maxStep) {
      S.maxStep = r.last_frame; $("#scrub").max = String(S.maxStep);
      for (const c of [...S.loaded]) if ((c + 1) * CHUNK - 2 >= S.maxStep - CHUNK) S.loaded.delete(c);
    }
    S.run.status = r.status; S.run.usage = r.usage; strip();
  } catch (_) { /* keep playing what we have */ }
}

(async function main() {
  S.run = await api("/api/run");
  S.agents = S.run.agents; S.byId = Object.fromEntries(S.agents.map((a) => [a.id, a]));
  S.map = await api("/api/map");
  S.minStep = S.run.first_frame ?? -1; S.maxStep = S.run.last_frame ?? 0;
  const scrub = $("#scrub"); scrub.min = String(S.minStep); scrub.max = String(S.maxStep);
  S.selected = S.agents[0]?.id || null;
  strip(); roster(); buildBase();
  const startAt = Math.min(S.maxStep, Math.max(S.minStep, Math.round((8 * 3600) / S.run.seconds_per_step)));
  await seek(startAt);
  setInterval(follow, 5000);
})();
