const TAGCOL = ["#e5172f", "#ff8a98", "#f5a524", "#5aa9ff", "#2ecc71", "#c084fc", "#ececf1"];
let notes = [], current = null, G = { nodes: [], links: [] }, view = { x: 0, y: 0, k: 1 }, tagColor = {};

function tab(p) { $$(".tab").forEach(t => t.classList.toggle("on", t.dataset.p === p)); $$("[data-pane]").forEach(e => { e.hidden = e.dataset.pane !== p; if (e.dataset.pane === "ask") e.style.display = p === "ask" ? "flex" : "none"; }); if (p === "graph") resize(); }
$$(".tab").forEach(t => t.onclick = () => tab(t.dataset.p));

async function load() {
  notes = await api("/api/notes"); $("#count").textContent = `${notes.length} notes`;
  notes.flatMap(n => n.tags).forEach(t => tagColor[t] ??= TAGCOL[Object.keys(tagColor).length % TAGCOL.length]);
  renderList(notes); await loadGraph();
}
function renderList(items, hits) {
  $("#list").innerHTML = items.map(n => `<div class="n ${current && current.id === n.id ? "on" : ""}" data-id="${n.id}"><b>${esc(n.title)}</b>
    ${hits ? `<div class="dim" style="font-size:12px">${esc(hits[n.id].slice(0, 90))}…</div>` : (n.tags || []).map(t => `<span class="tag">#${esc(t)}</span>`).join("")}</div>`).join("")
    || `<div class="empty" style="padding:20px">Aucune note.<br><br><button class="btn sm" onclick="$('#ex').click()">Charger des exemples</button></div>`;
  $$("#list .n").forEach(e => e.onclick = () => openNote(+e.dataset.id));
}
let st; $("#q").oninput = e => { clearTimeout(st); st = setTimeout(async () => {
  const q = e.target.value.trim(); if (!q) return renderList(notes);
  const res = await api("/api/search?q=" + encodeURIComponent(q)), hits = {}, order = [];
  res.forEach(r => { if (!hits[r.note_id]) { hits[r.note_id] = r.text; order.push(notes.find(n => n.id === r.note_id)); } });
  renderList(order.filter(Boolean), hits);
}, 250); };
$("#ex").onclick = async () => { const r = await api("/api/examples", { method: "POST" }); toast(`${r.added} notes d'exemple ajoutées`); load(); };
$("#files").onchange = async e => {
  const fd = new FormData(); [...e.target.files].forEach(f => fd.append("files", f));
  const r = await api("/api/import", { method: "POST", body: fd }); toast(`${r.added.length} fichier(s) importé(s)`); r.errors.forEach(x => toast(x, 5000)); load();
};
$("#newNote").onclick = () => { current = { id: null, title: "", body: "", tags: [], related: [], backlinks: [] }; tab("note"); renderNote(true); };

/* ───────── note ───────── */
async function openNote(id) { current = await api("/api/notes/" + id); tab("note"); renderNote(false); renderList(notes); }
function md(s) {
  return esc(s).replace(/^### (.*)$/gm, "<h3>$1</h3>").replace(/^## (.*)$/gm, "<h2>$1</h2>").replace(/^# (.*)$/gm, "<h1>$1</h1>")
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\[\[([^\]]+)\]\]/g, `<a class="wl" data-t="$1">$1</a>`)
    .replace(/(^|\s)#([\wÀ-ÿ-]{2,30})/g, `$1<span class="tag">#$2</span>`).replace(/^- (.*)$/gm, "• $1")
    .split(/\n{2,}/).map(p => /^<h\d/.test(p) ? p : `<p>${p.replace(/\n/g, "<br>")}</p>`).join("");
}
function renderNote(edit) {
  const n = current, v = $("#noteView"); v.className = "";
  if (edit) {
    v.innerHTML = `<div style="max-width:900px;margin:0 auto" class="col"><input class="input" id="et" placeholder="Titre" value="${esc(n.title)}" style="font-size:20px;font-weight:700">
      <textarea id="eb" rows="20" placeholder="Écrivez en Markdown. [[Titre d'une note]] crée un lien, #tag ajoute un tag.">${esc(n.body)}</textarea>
      <div class="row"><button class="btn" id="save">Enregistrer</button><button class="btn ghost" id="cancel">Annuler</button></div></div>`;
    $("#save").onclick = async () => {
      const body = { title: $("#et").value || "Sans titre", body: $("#eb").value };
      if (n.id) await api("/api/notes/" + n.id, { method: "PUT", body }); else n.id = (await api("/api/notes", { method: "POST", body })).id;
      await load(); openNote(n.id);
    };
    $("#cancel").onclick = () => n.id ? renderNote(false) : tab("graph");
    return;
  }
  v.innerHTML = `<div class="note-grid"><article class="md"><div class="row between"><span class="kicker">${esc(n.source || "")}</span>
      <span class="row"><button class="btn ghost sm" id="edit">✎ Modifier</button><button class="btn ghost sm" id="delN">Supprimer</button></span></div>
      <h1 style="margin-top:12px">${esc(n.title)}</h1>${md(n.body)}</article>
    <div class="col"><div class="card flat"><h3>Idées liées</h3>${n.related.map(r => `<div class="src" data-id="${r.id}" style="margin-bottom:6px">${esc(r.title)} <span class="dim mono">${Math.round(r.score * 100)}%</span></div>`).join("") || `<div class="dim">—</div>`}</div>
    <div class="card flat"><h3>Rétroliens</h3>${n.backlinks.map(r => `<div class="src" data-id="${r.id}" style="margin-bottom:6px">← ${esc(r.title)}</div>`).join("") || `<div class="dim">Aucune note ne pointe ici.</div>`}</div></div></div>`;
  $("#edit").onclick = () => renderNote(true);
  $("#delN").onclick = async () => { if (confirm("Supprimer cette note ?")) { await api("/api/notes/" + n.id, { method: "DELETE" }); current = null; await load(); tab("graph"); } };
  $$("#noteView [data-id]").forEach(e => e.onclick = () => openNote(+e.dataset.id));
  $$("#noteView .wl").forEach(e => e.onclick = () => { const t = notes.find(x => x.title.toLowerCase() === e.dataset.t.toLowerCase()); t ? openNote(t.id) : toast("Cette note n'existe pas encore"); });
}

/* ───────── questions ───────── */
async function ask() {
  const q = $("#question").value.trim(); if (!q) return; $("#question").value = "";
  if ($("#msgs .empty")) $("#msgs").innerHTML = "";
  $("#msgs").insertAdjacentHTML("beforeend", `<div class="q">${esc(q)}</div><div class="a" id="pending"><span class="badge live">recherche dans vos notes…</span></div>`);
  const r = await api("/api/ask", { method: "POST", body: { question: q } });
  const ans = esc(r.answer).replace(/\[(\d)\]/g, `<span class="cite" data-s="$1">[$1]</span>`).replace(/\n/g, "<br>");
  $("#pending").outerHTML = `<div class="a">${ans}<div class="dim" style="font-size:11px;margin:10px 0 8px">${r.mode === "llm" ? "Réponse générée par LLM à partir de vos notes" : "Réponse extractive (aucune clé d'API LLM configurée)"}</div>
    <div class="grid g2" style="gap:8px">${r.sources.slice(0, 4).map((s, i) => `<div class="src" data-id="${s.note_id}"><b class="red">[${i + 1}]</b> <b>${esc(s.title)}</b> <span class="dim mono">${Math.round(s.score * 100)}%</span><div class="dim" style="margin-top:4px">${esc(s.text.slice(0, 140))}…</div></div>`).join("")}</div></div>`;
  $$("#msgs .src").forEach(e => e.onclick = () => openNote(+e.dataset.id));
  $$("#msgs .cite").forEach(e => e.onclick = () => { const s = r.sources[+e.dataset.s - 1]; s && openNote(s.note_id); });
  $("#chat").scrollTop = 1e9;
}
$("#send").onclick = ask; $("#question").onkeydown = e => e.key === "Enter" && ask();

/* ───────── graphe à forces ───────── */
const cv = $("#graph"), ctx = cv.getContext("2d");
async function loadGraph() {
  const g = await api("/api/graph?t=" + $("#t").value), old = Object.fromEntries(G.nodes.map(n => [n.id, n]));
  g.nodes.forEach((n, i) => { const o = old[n.id]; const a = i / g.nodes.length * 6.28; Object.assign(n, o ? { x: o.x, y: o.y } : { x: Math.cos(a) * 200, y: Math.sin(a) * 200 }, { vx: 0, vy: 0 }); });
  const by = Object.fromEntries(g.nodes.map(n => [n.id, n])); g.links.forEach(l => { l.s = by[l.source]; l.t = by[l.target]; });
  g.nodes.forEach(n => n.deg = g.links.filter(l => l.s === n || l.t === n).length); G = g; heat = 1;
}
$("#t").oninput = e => { $("#tv").textContent = e.target.value; loadGraph(); };
let heat = 1, hover = null, drag = null, pan = null;
function resize() { const r = cv.getBoundingClientRect(), d = devicePixelRatio || 1; cv.width = r.width * d; cv.height = r.height * d; }
addEventListener("resize", resize);
function physics() {
  const N = G.nodes; if (heat < 0.002) return;
  for (let i = 0; i < N.length; i++) for (let j = i + 1; j < N.length; j++) {
    const a = N[i], b = N[j], dx = b.x - a.x, dy = b.y - a.y, d2 = dx * dx + dy * dy + 0.01, f = 9000 / d2 * heat, d = Math.sqrt(d2);
    a.vx -= dx / d * f; a.vy -= dy / d * f; b.vx += dx / d * f; b.vy += dy / d * f;
  }
  G.links.forEach(l => { const dx = l.t.x - l.s.x, dy = l.t.y - l.s.y, d = Math.hypot(dx, dy) || 1, f = (d - 140) * 0.02 * l.w * heat; l.s.vx += dx / d * f; l.s.vy += dy / d * f; l.t.vx -= dx / d * f; l.t.vy -= dy / d * f; });
  N.forEach(n => { n.vx -= n.x * 0.004 * heat; n.vy -= n.y * 0.004 * heat; if (n !== drag) { n.x += n.vx; n.y += n.vy; } n.vx *= .6; n.vy *= .6; });
  heat *= .995;
}
function toScreen(n) { return [cv.width / (devicePixelRatio || 1) / 2 + (n.x + view.x) * view.k, cv.height / (devicePixelRatio || 1) / 2 + (n.y + view.y) * view.k]; }
function draw() {
  physics(); const d = devicePixelRatio || 1; ctx.setTransform(d, 0, 0, d, 0, 0); ctx.clearRect(0, 0, cv.width, cv.height);
  if (!G.nodes.length) { ctx.fillStyle = "#5d5d69"; ctx.font = "14px Inter"; ctx.textAlign = "center"; ctx.fillText("Ajoutez des notes pour voir émerger le graphe de vos idées.", cv.width / d / 2, cv.height / d / 2); return requestAnimationFrame(draw); }
  const near = hover ? new Set(G.links.filter(l => l.s === hover || l.t === hover).flatMap(l => [l.s, l.t])) : null;
  G.links.forEach(l => {
    const [x1, y1] = toScreen(l.s), [x2, y2] = toScreen(l.t), hl = hover && (l.s === hover || l.t === hover);
    ctx.strokeStyle = hl ? "#ff3b52" : l.kind === "lien" ? "rgba(236,236,241,.45)" : `rgba(229,23,47,${.15 + l.w * .5})`;
    ctx.lineWidth = (hl ? 2 : 1) * (0.6 + l.w * 2); ctx.setLineDash(l.kind === "lien" ? [] : l.kind === "tag" ? [1, 5] : [6, 4]); if (l.kind === "tag" && !hl) ctx.strokeStyle = "rgba(141,141,153,.35)";
    ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
  }); ctx.setLineDash([]);
  G.nodes.forEach(n => {
    const [x, y] = toScreen(n), r = (6 + Math.sqrt(n.deg) * 3 + Math.min(6, n.size / 600)) * Math.sqrt(view.k), col = tagColor[n.tags[0]] || "#8d8d99";
    const dim = near && !near.has(n) && n !== hover;
    ctx.globalAlpha = dim ? .25 : 1; ctx.shadowColor = col; ctx.shadowBlur = n === hover || (current && current.id === n.id) ? 24 : 8;
    ctx.fillStyle = col; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); ctx.shadowBlur = 0;
    if (current && current.id === n.id) { ctx.strokeStyle = "#fff"; ctx.lineWidth = 2; ctx.stroke(); }
    ctx.fillStyle = "#ececf1"; ctx.font = `${n === hover ? 600 : 500} ${12 * Math.min(1.3, Math.max(.8, view.k))}px Inter, sans-serif`; ctx.textAlign = "center";
    ctx.fillText(n.title.length > 28 ? n.title.slice(0, 26) + "…" : n.title, x, y + r + 14); ctx.globalAlpha = 1;
  });
  requestAnimationFrame(draw);
}
function pick(e) { const r = cv.getBoundingClientRect(), mx = e.clientX - r.left, my = e.clientY - r.top; return G.nodes.find(n => { const [x, y] = toScreen(n); return Math.hypot(x - mx, y - my) < 14 * Math.sqrt(view.k); }); }
cv.onmousemove = e => {
  if (drag) { drag.x += e.movementX / view.k; drag.y += e.movementY / view.k; heat = Math.max(heat, .3); drag.moved = true; return; }
  if (pan) { view.x += e.movementX / view.k; view.y += e.movementY / view.k; return; }
  hover = pick(e); cv.style.cursor = hover ? "pointer" : "grab"; const tip = $("#tip");
  if (hover) { const links = G.links.filter(l => l.s === hover || l.t === hover);
    tip.style.display = "block"; tip.style.left = e.offsetX + 14 + "px"; tip.style.top = e.offsetY + 14 + "px";
    tip.innerHTML = `<b>${esc(hover.title)}</b><br>${hover.tags.map(t => `<span class="tag">#${esc(t)}</span>`).join("")}<br><span class="dim">${links.length} lien(s)${links[0] && links[0].why.length ? " · " + esc(links.flatMap(l => l.why).slice(0, 4).join(", ")) : ""}</span>`;
  } else tip.style.display = "none";
};
cv.onmousedown = e => { const n = pick(e); if (n) { drag = n; drag.moved = false; } else pan = true; };
addEventListener("mouseup", () => { if (drag && !drag.moved) openNote(drag.id); drag = null; pan = null; });
cv.onwheel = e => { e.preventDefault(); view.k = Math.min(3, Math.max(.3, view.k * (e.deltaY < 0 ? 1.1 : .9))); };

tab("graph"); resize(); draw(); load();
