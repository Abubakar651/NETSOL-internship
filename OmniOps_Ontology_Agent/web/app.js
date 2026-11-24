/* OmniOps Operations Center — Interactive SVG 60% Squircles, Live MCP Trace & Omnigraph Inbox */

const state = {
  topology: null,
  branchesData: null,
  schemaData: null,
  selectedServiceId: "SVC-PAYMENT-GW",
  blastHighlightIds: new Set(),
  pendingMergeBranch: null,
};

function escapeHtml(raw) {
  return String(raw ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/**
 * Exact Apple UIKit 60% corner-smoothing continuous-curvature squircle path.
 * Uses the reverse-engineered 1.528665 tangent extension and symmetric cubic Bezier constants.
 */
function appleSquirclePath(x, y, w, h, r) {
  const k = Math.min(r, w / 3.2, h / 3.2);
  if (k <= 0) {
    return `M ${x} ${y} H ${x + w} V ${y + h} H ${x} Z`;
  }
  const p = 1.528665 * k;
  const c1 = 1.08849296 * k;
  const c2 = 0.86840694 * k;
  const sx = 0.63149379 * k;
  const sy = 0.07491139 * k;
  const cx1 = 0.37282383 * k;
  const cy1 = 0.16905956 * k;
  const f = (n) => n.toFixed(2);

  return [
    `M ${f(x + p)} ${f(y)}`,
    `L ${f(x + w - p)} ${f(y)}`,
    `C ${f(x + w - c1)} ${f(y)} ${f(x + w - c2)} ${f(y)} ${f(x + w - sx)} ${f(y + sy)}`,
    `C ${f(x + w - cx1)} ${f(y + cy1)} ${f(x + w - cy1)} ${f(y + cx1)} ${f(x + w - sy)} ${f(y + sx)}`,
    `C ${f(x + w)} ${f(y + c2)} ${f(x + w)} ${f(y + c1)} ${f(x + w)} ${f(y + p)}`,
    `L ${f(x + w)} ${f(y + h - p)}`,
    `C ${f(x + w)} ${f(y + h - c1)} ${f(x + w)} ${f(y + h - c2)} ${f(x + w - sy)} ${f(y + h - sx)}`,
    `C ${f(x + w - cy1)} ${f(y + h - cx1)} ${f(x + w - cx1)} ${f(y + h - cy1)} ${f(x + w - sx)} ${f(y + h - sy)}`,
    `C ${f(x + w - c2)} ${f(y + h)} ${f(x + w - c1)} ${f(y + h)} ${f(x + w - p)} ${f(y + h)}`,
    `L ${f(x + p)} ${f(y + h)}`,
    `C ${f(x + c1)} ${f(y + h)} ${f(x + c2)} ${f(y + h)} ${f(x + sx)} ${f(y + h - sy)}`,
    `C ${f(x + cx1)} ${f(y + h - cy1)} ${f(x + cy1)} ${f(y + h - cx1)} ${f(x + sy)} ${f(y + h - sx)}`,
    `C ${f(x)} ${f(y + h - c2)} ${f(x)} ${f(y + h - c1)} ${f(x)} ${f(y + h - p)}`,
    `L ${f(x)} ${f(y + p)}`,
    `C ${f(x)} ${f(y + c1)} ${f(x)} ${f(y + c2)} ${f(x + sy)} ${f(y + sx)}`,
    `C ${f(x + cy1)} ${f(y + cx1)} ${f(x + cx1)} ${f(y + cy1)} ${f(x + sx)} ${f(y + sy)}`,
    `C ${f(x + c2)} ${f(y)} ${f(x + c1)} ${f(y)} ${f(x + p)} ${f(y)}`,
    "Z",
  ].join(" ");
}

async function apiFetch(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return body;
}

function statusColors(status) {
  if (status === "CRITICAL" || status === "LOCKED") {
    return { stroke: "#ef4444", fill: "rgba(239, 68, 68, 0.16)", badge: "#ef4444", text: "#fca5a5" };
  }
  if (status === "DEGRADED" || status === "HIGH_LOAD") {
    return { stroke: "#f59e0b", fill: "rgba(245, 158, 11, 0.15)", badge: "#f59e0b", text: "#fcd34d" };
  }
  return { stroke: "#10b981", fill: "rgba(16, 185, 129, 0.14)", badge: "#10b981", text: "#6ee7b7" };
}

const NODE_LAYOUT = {
  "SVC-MOBILE-GW": { x: 22, y: 42, w: 162, h: 72 },
  "SVC-WEB-STORE": { x: 22, y: 158, w: 162, h: 72 },
  "SVC-CHECKOUT": { x: 224, y: 100, w: 162, h: 72 },
  "SVC-PAYMENT-GW": { x: 426, y: 100, w: 172, h: 76 },
  "SVC-FRAUD-ENGINE": { x: 426, y: 278, w: 172, h: 72 },
  "SVC-NOTIFICATION": { x: 224, y: 278, w: 162, h: 72 },
  "DB-SESSION-REDIS": { x: 22, y: 292, w: 162, h: 64 },
  "DB-ACCOUNT-LEDGER": { x: 618, y: 102, w: 128, h: 72 },
  "DB-ORDER-STORE": { x: 618, y: 278, w: 128, h: 72 },
};

function renderTopologySVG() {
  const svg = document.getElementById("topology-svg");
  if (!state.topology || !svg) return;

  const isLight = document.documentElement.getAttribute("data-theme") === "light";
  const labelColor = isLight ? "#0f172a" : "#f8fafc";
  const subColor = isLight ? "#475569" : "#cbd5e1";
  const edgeBase = isLight ? "rgba(71, 85, 105, 0.48)" : "rgba(148, 163, 184, 0.45)";

  const nodeMap = {};
  for (const n of state.topology.nodes) {
    nodeMap[n.id] = n;
  }

  const parts = [
    `<defs>
      <marker id="topo-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#94a3b8"/>
      </marker>
      <marker id="topo-arrow-hot" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
        <path d="M 0 1 L 10 5 L 0 9 z" fill="#f59e0b"/>
      </marker>
    </defs>`,
  ];

  // Draw directed CALLS and READS_WRITES edges
  for (const edge of state.topology.edges) {
    if (edge.link_type !== "CALLS" && edge.link_type !== "READS_WRITES") continue;
    const src = NODE_LAYOUT[edge.source_id];
    const tgt = NODE_LAYOUT[edge.target_id];
    if (!src || !tgt) continue;

    const x1 = src.x + src.w / 2;
    const y1 = src.y + src.h / 2;
    const x2 = tgt.x + tgt.w / 2;
    const y2 = tgt.y + tgt.h / 2;
    const dx = x2 - x1;
    const dy = y2 - y1;
    const dist = Math.hypot(dx, dy) || 1;
    const sx = x1 + (dx / dist) * (src.w * 0.42);
    const sy = y1 + (dy / dist) * (src.h * 0.42);
    const ex = x2 - (dx / dist) * (tgt.w * 0.46);
    const ey = y2 - (dy / dist) * (tgt.h * 0.46);

    const isHot =
      state.blastHighlightIds.has(edge.source_id) &&
      (state.blastHighlightIds.has(edge.target_id) || edge.target_id === state.selectedServiceId);
    const stroke = isHot ? "#f59e0b" : edgeBase;
    const dash = edge.properties?.circuit_breaker_open
      ? 'stroke-dasharray="5,4"'
      : edge.link_type === "READS_WRITES"
        ? 'stroke-dasharray="3,3"'
        : "";
    const marker = isHot ? "url(#topo-arrow-hot)" : "url(#topo-arrow)";

    parts.push(
      `<line x1="${sx.toFixed(1)}" y1="${sy.toFixed(1)}" x2="${ex.toFixed(1)}" y2="${ey.toFixed(1)}" stroke="${stroke}" stroke-width="${isHot ? 2.4 : 1.5}" ${dash} marker-end="${marker}" />`
    );
  }

  // Draw 60%-smooth Apple Squircle nodes
  for (const [id, box] of Object.entries(NODE_LAYOUT)) {
    const node = nodeMap[id];
    if (!node) continue;
    const data = node.data || {};
    const c = statusColors(data.status || "HEALTHY");
    const isSelected = state.selectedServiceId === id;
    const isBlasted = state.blastHighlightIds.has(id);
    const outerPath = appleSquirclePath(box.x, box.y, box.w, box.h, 16);

    const halo =
      isSelected || isBlasted
        ? `<path d="${appleSquirclePath(box.x - 4, box.y - 4, box.w + 8, box.h + 8, 19)}" fill="none" stroke="${isSelected ? "#2dd4bf" : "#f59e0b"}" stroke-width="2" stroke-opacity="0.85" />`
        : "";

    const isService = node.object_type === "Service";
    const subLine = isService
      ? `${data.tier} • ${data.current_version} • ${data.error_rate_pct}% err`
      : `${data.engine} • ${data.active_connections}/${data.max_connections}`;

    parts.push(`
      <g class="topo-node" data-id="${escapeHtml(id)}" data-type="${escapeHtml(node.object_type)}" style="cursor:${isService ? "pointer" : "default"};">
        ${halo}
        <path d="${outerPath}" fill="${c.fill}" stroke="${c.stroke}" stroke-width="${isSelected ? 2.4 : 1.6}" />
        <circle cx="${box.x + 15}" cy="${box.y + 21}" r="4.5" fill="${c.badge}" />
        <text x="${box.x + 26}" y="${box.y + 25}" fill="${labelColor}" font-size="11.5" font-weight="700">${escapeHtml(node.label)}</text>
        <text x="${box.x + 14}" y="${box.y + 44}" fill="${subColor}" font-size="9.8" font-weight="600">${escapeHtml(subLine)}</text>
        <text x="${box.x + 14}" y="${box.y + 59}" fill="${c.badge}" font-size="9.4" font-weight="700">${escapeHtml(data.status || "")}</text>
      </g>
    `);
  }

  svg.innerHTML = parts.join("");

  svg.querySelectorAll(".topo-node[data-type='Service']").forEach((el) => {
    el.addEventListener("click", () => {
      const svcId = el.getAttribute("data-id");
      if (svcId) inspectServiceNode(svcId);
    });
  });
}

async function inspectServiceNode(serviceId) {
  state.selectedServiceId = serviceId;
  try {
    const br = await apiFetch(`/api/blast-radius/${encodeURIComponent(serviceId)}`);
    state.blastHighlightIds = new Set([
      br.root_service_id,
      ...br.impacted_upstream_services.map((c) => c.service_id),
      ...br.downstream_dependencies.map((d) => d.object_id),
    ]);
    renderTopologySVG();

    const callers = br.impacted_upstream_services
      .map((c) => `<span class="badge badge-warn">${escapeHtml(c.service_id)} (${escapeHtml(c.tier)}, hop ${c.hop_distance})</span>`)
      .join(" ");
    const dbs = br.downstream_dependencies
      .filter((d) => d.object_type === "Database")
      .map((d) => {
        const sat = d.details?.connection_saturation_ratio;
        return `<span class="badge ${d.details?.is_connection_exhausted ? "badge-crit" : "badge-accent"}">${escapeHtml(d.object_id)} ${sat ? `(${Math.round(sat * 100)}% conns)` : ""}</span>`;
      })
      .join(" ");

    document.getElementById("node-inspector-body").innerHTML = `
      <div style="display:flex; flex-wrap:wrap; align-items:center; justify-content:space-between; gap:8px; margin-bottom:6px;">
        <strong>${escapeHtml(br.root_service_name)} (${escapeHtml(br.root_service_id)})</strong>
        <span class="badge ${br.root_status === "HEALTHY" ? "badge-ok" : "badge-crit"}">
          Blast-Radius Score: ${br.blast_radius_severity_score} • ${escapeHtml(br.root_status)}
        </span>
      </div>
      <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:4px;">
        <span class="kpi-meta" style="margin-right:4px;">Upstream P0/P1 Impact:</span>
        ${callers || '<span class="kpi-meta">None</span>'}
      </div>
      <div style="display:flex; flex-wrap:wrap; gap:6px;">
        <span class="kpi-meta" style="margin-right:4px;">Downstream Datastores:</span>
        ${dbs || '<span class="kpi-meta">None</span>'}
      </div>
    `;
  } catch (err) {
    document.getElementById("node-inspector-body").textContent = err.message;
  }
}

function renderKPIs() {
  if (!state.topology) return;
  const k = state.topology.kpis;

  document.getElementById("kpi-services").textContent = `${k.healthy_services} / ${k.total_services} Healthy`;
  document.getElementById("kpi-services-meta").textContent = `${k.critical_services} Critical • ${k.degraded_services} Degraded`;
  document.getElementById("kpi-services-dot").className =
    "status-dot " + (k.critical_services > 0 ? "dot-crit" : k.degraded_services > 0 ? "dot-warn" : "dot-ok");

  document.getElementById("kpi-incidents").textContent = `${k.open_incidents} Open`;
  document.getElementById("kpi-incidents-meta").textContent = `${k.mitigated_incidents} Mitigated`;
  document.getElementById("kpi-incidents-dot").className =
    "status-dot " + (k.open_incidents > 0 ? "dot-warn" : "dot-ok");

  document.getElementById("kpi-branches").textContent = String(k.pending_branches);
  const badge = document.getElementById("inbox-badge");
  badge.textContent = String(k.pending_branches);
  badge.classList.toggle("has-pending", k.pending_branches > 0);

  document.getElementById("kpi-ontology").textContent = `${k.certified_objects} Certified`;
  document.getElementById("kpi-ontology-meta").textContent = `${k.draft_objects} Draft awaiting SME`;
}

function renderInvestigationResult(result) {
  const r = result.report;
  const badge = document.getElementById("report-status-badge");
  const body = document.getElementById("report-body");

  if (!r.answerable) {
    badge.className = "badge badge-warn";
    badge.textContent = result.answerability.uncertified_concepts.length
      ? "Blocked: DRAFT Concept"
      : "Out of Ontology Scope";
    body.innerHTML = `
      <p style="margin:0 0 8px;"><strong>Answerability Gate:</strong> ${escapeHtml(r.root_cause_summary)}</p>
      ${
        result.answerability.uncertified_concepts.length
          ? `<button id="goto-ontology-btn" class="glass-btn primary squircle-sm" type="button">Open Auto-Ontology to Certify</button>`
          : ""
      }
    `;
    const btn = document.getElementById("goto-ontology-btn");
    if (btn) btn.addEventListener("click", () => switchTab("ontology"));
  } else {
    badge.className = "badge badge-ok";
    badge.textContent = `Verified • ${result.provider_used}`;
    const evidenceHtml = r.evidence_chain
      .map((line) => `<div class="trace-item squircle-sm"><span>${escapeHtml(line)}</span></div>`)
      .join("");
    body.innerHTML = `
      <p style="margin:0 0 8px; color:var(--text-primary); font-weight:600;">${escapeHtml(r.root_cause_summary)}</p>
      <div style="display:flex; flex-wrap:wrap; gap:6px; margin-bottom:8px;">
        <span class="badge badge-crit">Service: ${escapeHtml(r.primary_failing_service_id)}</span>
        ${r.culprit_pull_request_id ? `<span class="badge badge-warn">Culprit PR: ${escapeHtml(r.culprit_pull_request_id)}</span>` : ""}
        ${r.affected_downstream_resource_id ? `<span class="badge badge-accent">Resource: ${escapeHtml(r.affected_downstream_resource_id)}</span>` : ""}
        <span class="badge badge-accent">Blast Score: ${r.blast_radius_severity_score}</span>
      </div>
      <div class="evidence-list">${evidenceHtml}</div>
      ${
        r.staged_branch_name
          ? `<div style="display:flex; align-items:center; justify-content:space-between; gap:8px; margin-top:10px;">
               <span class="mono">Branch: ${escapeHtml(r.staged_branch_name)} (${escapeHtml(r.staged_commit_hash)})</span>
               <button id="goto-inbox-btn" class="glass-btn primary squircle-sm" type="button">Review in Approval Inbox</button>
             </div>`
          : ""
      }
    `;
    const inboxBtn = document.getElementById("goto-inbox-btn");
    if (inboxBtn) inboxBtn.addEventListener("click", () => switchTab("inbox"));
    if (r.primary_failing_service_id) {
      inspectServiceNode(r.primary_failing_service_id);
    }
  }

  document.getElementById("trace-count").textContent = `${result.tool_trace.length} MCP call(s)`;
  document.getElementById("trace-list").innerHTML = result.tool_trace
    .map(
      (t) => `
      <div class="trace-item squircle-sm">
        <div>
          <strong class="mono">${escapeHtml(t.tool_name)}</strong>
          <div class="kpi-meta">${escapeHtml(t.result_summary)}</div>
        </div>
        <span class="badge ${t.status === "OK" ? "badge-ok" : "badge-crit"} mono">${t.latency_ms.toFixed(1)} ms</span>
      </div>`
    )
    .join("");
}

function renderBranches() {
  if (!state.branchesData) return;
  const container = document.getElementById("branches-container");
  const commitsContainer = document.getElementById("commits-container");

  const featureBranches = state.branchesData.branches.filter((b) => b.branch_name !== "main");
  if (!featureBranches.length) {
    container.innerHTML = `<div class="inset-card kpi-meta">No staged remediation branches yet. Run an investigation in the Operations tab.</div>`;
  } else {
    container.innerHTML = featureBranches
      .map((b) => {
        const diffRows = (b.three_way_diff?.changes || [])
          .map(
            (d) => `
            <tr>
              <td class="mono">${escapeHtml(d.object_type)} • ${escapeHtml(d.object_id)}.${escapeHtml(d.field)}</td>
              <td class="mono diff-old">${escapeHtml(JSON.stringify(d.base_value))}</td>
              <td class="mono diff-new">${escapeHtml(JSON.stringify(d.branch_value))}</td>
            </tr>`
          )
          .join("");
        const statusBadge =
          b.status === "ACTIVE" ? "badge-warn" : b.status === "MERGED" ? "badge-ok" : "badge-crit";
        const policyId = b.pending_action?.policy_id || "PERMIT-AGENT-INCIDENT-BRANCH";
        const actionsHtml =
          b.status === "ACTIVE"
            ? `<div style="display:flex; gap:8px; margin-top:10px;">
                 <button class="glass-btn primary squircle-sm approve-btn" data-branch="${escapeHtml(b.branch_name)}" type="button">Approve &amp; Merge to Main</button>
                 <button class="glass-btn danger squircle-sm reject-btn" data-branch="${escapeHtml(b.branch_name)}" type="button">Reject Branch</button>
               </div>`
            : "";

        return `
          <article class="inset-card branch-card">
            <div class="panel-header" style="margin-bottom:6px;">
              <div>
                <strong class="mono">${escapeHtml(b.branch_name)}</strong>
                <div class="kpi-meta">Cedar Policy: <span class="mono">${escapeHtml(policyId)}</span> • Head <span class="mono">${escapeHtml(b.head_commit_hash)}</span></div>
              </div>
              <span class="badge ${statusBadge}">${escapeHtml(b.status)}</span>
            </div>
            ${
              diffRows
                ? `<table class="diff-table">
                     <thead><tr><th>Target Field</th><th>Current (main)</th><th>Proposed (branch)</th></tr></thead>
                     <tbody>${diffRows}</tbody>
                   </table>`
                : ""
            }
            ${actionsHtml}
          </article>
        `;
      })
      .join("");

    container.querySelectorAll(".approve-btn").forEach((btn) => {
      btn.addEventListener("click", () => openMergeDialog(btn.getAttribute("data-branch")));
    });
    container.querySelectorAll(".reject-btn").forEach((btn) => {
      btn.addEventListener("click", () => handleRejectBranch(btn.getAttribute("data-branch")));
    });
  }

  commitsContainer.innerHTML = [...state.branchesData.commits]
    .reverse()
    .map(
      (c) => `
      <div class="trace-item squircle-sm">
        <div>
          <strong class="mono">${escapeHtml(c.commit_hash)}</strong>
          <span class="badge badge-accent">${escapeHtml(c.branch_name)}</span>
          <div class="kpi-meta">${escapeHtml(c.summary)}</div>
        </div>
        <span class="mono">${escapeHtml(c.actor_role)}</span>
      </div>`
    )
    .join("");
}

function renderSchema() {
  if (!state.schemaData) return;
  const draftsEl = document.getElementById("drafts-container");
  const certEl = document.getElementById("certified-container");

  const draftEntries = Object.values(state.schemaData.draft_objects || {});
  if (!draftEntries.length) {
    draftsEl.innerHTML = `<div class="inset-card kpi-meta">All discovered SQLite tables have been certified by an SME.</div>`;
  } else {
    draftsEl.innerHTML = draftEntries
      .map(
        (obj) => `
        <article class="inset-card">
          <div class="panel-header" style="margin-bottom:6px;">
            <strong>${escapeHtml(obj.name)}</strong>
            <span class="badge badge-warn">DRAFT</span>
          </div>
          <p class="kpi-meta" style="margin:0 0 8px;">Table: <span class="mono">${escapeHtml(obj.source_table)}</span> • ${obj.properties.length} columns</p>
          <button class="glass-btn primary squircle-sm certify-btn" data-name="${escapeHtml(obj.name)}" type="button">
            Certify Schema (SME Gate)
          </button>
        </article>`
      )
      .join("");

    draftsEl.querySelectorAll(".certify-btn").forEach((btn) => {
      btn.addEventListener("click", () => certifyObject(btn.getAttribute("data-name")));
    });
  }

  const objects = Object.values(state.schemaData.objects || {}).map(
    (obj) => `
    <article class="inset-card">
      <div class="panel-header" style="margin-bottom:4px;">
        <strong>${escapeHtml(obj.name)}</strong>
        <span class="badge badge-ok">Object • CERTIFIED</span>
      </div>
      <div class="kpi-meta">${escapeHtml(obj.description)}</div>
      <div class="mono" style="margin-top:6px; color:var(--text-muted);">${escapeHtml(obj.source_table)} (${obj.properties.length} props)</div>
    </article>`
  );
  const actions = Object.values(state.schemaData.actions || {}).map(
    (act) => `
    <article class="inset-card">
      <div class="panel-header" style="margin-bottom:4px;">
        <strong>${escapeHtml(act.name)}</strong>
        <span class="badge badge-accent">Kinetic Action</span>
      </div>
      <div class="kpi-meta">${escapeHtml(act.description)}</div>
    </article>`
  );
  certEl.innerHTML = [...objects, ...actions].join("");
}

function switchTab(tabName) {
  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.setAttribute("aria-selected", String(btn.getAttribute("data-tab") === tabName));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.hidden = panel.id !== `tab-${tabName}`;
  });
}

function openMergeDialog(branchName) {
  state.pendingMergeBranch = branchName;
  document.getElementById("merge-dialog-subtitle").textContent =
    `Execute 3-way merge of '${branchName}' onto production 'main'.`;
  const dlg = document.getElementById("merge-dialog");
  if (typeof dlg.showModal === "function") {
    dlg.showModal();
  } else {
    dlg.setAttribute("open", "true");
  }
}

async function handleRejectBranch(branchName) {
  try {
    await apiFetch("/api/branches/reject", {
      method: "POST",
      body: JSON.stringify({
        branch_name: branchName,
        reviewer: "senior.sre@netsol.example",
        reason: "Rejected from Approval Inbox",
      }),
    });
    await refreshAll();
  } catch (err) {
    alert(err.message);
  }
}

async function certifyObject(entityName) {
  try {
    await apiFetch("/api/ontology/certify", {
      method: "POST",
      body: JSON.stringify({
        entity_kind: "object",
        entity_name: entityName,
        reviewer: "senior.architect@netsol.example",
      }),
    });
    await refreshAll();
  } catch (err) {
    alert(err.message);
  }
}

async function runInvestigation({ question = null, incidentId = null }) {
  const btn = document.getElementById("investigate-btn");
  const preferOffline = document.getElementById("prefer-offline").checked;
  btn.disabled = true;
  btn.textContent = "Investigating via MCP...";
  try {
    const result = await apiFetch("/api/investigate", {
      method: "POST",
      body: JSON.stringify({ question, incident_id: incidentId, prefer_offline: preferOffline }),
    });
    renderInvestigationResult(result);
    await refreshAll();
  } catch (err) {
    document.getElementById("report-status-badge").className = "badge badge-crit";
    document.getElementById("report-status-badge").textContent = "Error";
    document.getElementById("report-body").textContent = err.message;
  } finally {
    btn.disabled = false;
    btn.textContent = "Run MCP Investigation";
  }
}

async function refreshAll() {
  const [topo, branches, schema] = await Promise.all([
    apiFetch("/api/topology"),
    apiFetch("/api/branches"),
    apiFetch("/api/ontology/schema"),
  ]);
  state.topology = topo;
  state.branchesData = branches;
  state.schemaData = schema;

  renderKPIs();
  renderTopologySVG();
  renderBranches();
  renderSchema();
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const toggleBtn = document.getElementById("theme-toggle");
  if (toggleBtn) {
    toggleBtn.textContent = theme === "light" ? "Dark Glass" : "Light Glass";
  }
  renderTopologySVG();
}

async function init() {
  const params = new URLSearchParams(window.location.search);
  const urlTheme = params.get("theme");
  if (urlTheme === "light" || urlTheme === "dark") {
    applyTheme(urlTheme);
  }

  document.querySelectorAll(".seg-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.getAttribute("data-tab")));
  });

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme") || "dark";
    applyTheme(current === "dark" ? "light" : "dark");
  });

  document.getElementById("reset-btn").addEventListener("click", async () => {
    await apiFetch("/api/reset", { method: "POST" });
    document.getElementById("question-input").value = "";
    document.getElementById("report-status-badge").className = "badge badge-accent";
    document.getElementById("report-status-badge").textContent = "Awaiting Query";
    document.getElementById("report-body").textContent =
      "Demo reset to clean seeded state. Select a Golden Incident above to investigate.";
    document.getElementById("trace-count").textContent = "0 calls";
    document.getElementById("trace-list").innerHTML = "";
    await refreshAll();
    await inspectServiceNode("SVC-PAYMENT-GW");
  });

  document.querySelectorAll(".scenario-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const incId = chip.getAttribute("data-incident");
      const q = chip.getAttribute("data-question");
      if (q) {
        document.getElementById("question-input").value = q;
        runInvestigation({ question: q });
      } else if (incId) {
        const prompt = `Analyze ${incId}, trace upstream blast radius, identify culprit PR, and stage a safe remediation.`;
        document.getElementById("question-input").value = prompt;
        runInvestigation({ question: prompt, incidentId: incId });
      }
    });
  });

  document.getElementById("investigate-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const q = document.getElementById("question-input").value.trim();
    if (!q) return;
    runInvestigation({ question: q });
  });

  const dlg = document.getElementById("merge-dialog");
  document.getElementById("merge-cancel-btn").addEventListener("click", () => {
    if (typeof dlg.close === "function") dlg.close();
    else dlg.removeAttribute("open");
  });
  document.getElementById("merge-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!state.pendingMergeBranch) return;
    try {
      await apiFetch("/api/branches/approve", {
        method: "POST",
        body: JSON.stringify({
          branch_name: state.pendingMergeBranch,
          approver: document.getElementById("approver-input").value.trim(),
          approval_note: document.getElementById("approval-note-input").value.trim(),
        }),
      });
      if (typeof dlg.close === "function") dlg.close();
      else dlg.removeAttribute("open");
      await refreshAll();
      await inspectServiceNode("SVC-PAYMENT-GW");
    } catch (err) {
      alert(err.message);
    }
  });

  const cfg = await apiFetch("/api/config");
  const activeMode = cfg.providers.gemini ? "Gemini Primary" : cfg.providers.groq ? "Groq Reasoning" : "Deterministic Ontology Mode";
  document.getElementById("provider-pill").textContent = activeMode;

  await refreshAll();
  await inspectServiceNode("SVC-PAYMENT-GW");
}

document.addEventListener("DOMContentLoaded", init);
