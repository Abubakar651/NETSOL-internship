"""Generate an easy-to-read, visual 5-page executive PDF for senior review.

Uses standard library Python + headless Google Chrome (--print-to-pdf) with inline
vector SVGs and local system fonts so it works reliably offline.

Run from any directory:
    python3 OmniOps_Ontology_Agent/docs/build_senior_overview_pdf.py
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output" / "pdf"
HTML_PATH = OUTPUT_DIR / "Omniops-Overview.html"
PDF_PATH = OUTPUT_DIR / "Omniops-Overview.pdf"


HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>OmniOps Ontology Agent — Executive Overview</title>
<style>
  @page {
    size: A4;
    margin: 0;
  }
  * {
    box-sizing: border-box;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
  html, body {
    margin: 0;
    padding: 0;
    background: #ffffff;
    color: #1e293b;
    font-family: "Lato", "Liberation Sans", "DejaVu Sans", Arial, sans-serif;
    font-size: 10pt;
    line-height: 1.42;
  }
  .page {
    width: 210mm;
    height: 297mm;
    padding: 12mm 14mm 14mm 14mm;
    position: relative;
    overflow: hidden;
    page-break-after: always;
    background: #ffffff;
  }
  .page:last-child {
    page-break-after: auto;
  }

  /* Header & Section Titles */
  .page-kicker {
    font-size: 8pt;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #0d9488;
    margin-bottom: 3px;
  }
  h1.page-title {
    margin: 0 0 6px 0;
    font-size: 18pt;
    font-weight: 800;
    color: #0f172a;
    line-height: 1.18;
  }
  .lead {
    margin: 0 0 12px 0;
    font-size: 10pt;
    color: #475569;
  }

  /* Cover Hero */
  .hero {
    background: linear-gradient(135deg, #0f172a 0%, #16263f 65%, #0f3d47 100%);
    color: #ffffff;
    border-radius: 10px;
    padding: 18px 20px;
    margin-bottom: 14px;
    border-left: 6px solid #0d9488;
  }
  .hero-badge {
    display: inline-block;
    background: rgba(13, 148, 136, 0.24);
    border: 1px solid #2dd4bf;
    color: #99f6e4;
    font-size: 7.8pt;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 3px 9px;
    border-radius: 999px;
    margin-bottom: 8px;
  }
  .hero h1 {
    margin: 0 0 6px 0;
    font-size: 22pt;
    font-weight: 800;
    letter-spacing: -0.01em;
    color: #ffffff;
  }
  .hero-sub {
    margin: 0 0 10px 0;
    font-size: 11.2pt;
    color: #99f6e4;
    font-weight: 600;
  }
  .hero p {
    margin: 0;
    font-size: 9.7pt;
    color: #e2e8f0;
    line-height: 1.45;
  }

  /* Grid & Cards */
  .grid-2 {
    display: flex;
    gap: 12px;
    margin-bottom: 14px;
  }
  .grid-2 > .card {
    flex: 1;
  }
  .grid-3 {
    display: flex;
    gap: 10px;
    margin-bottom: 12px;
  }
  .grid-3 > .card {
    flex: 1;
  }
  .grid-4 {
    display: flex;
    gap: 9px;
    margin-top: 10px;
  }
  .grid-4 > .card {
    flex: 1;
  }
  .card {
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 11px 13px;
    background: #f8fafc;
  }
  .card-bad {
    background: #fef2f2;
    border-color: #fecaca;
    border-top: 4px solid #dc2626;
  }
  .card-good {
    background: #f0fdfa;
    border-color: #99f6e4;
    border-top: 4px solid #0d9488;
  }
  .card-navy {
    background: #f8fafc;
    border-color: #cbd5e1;
    border-top: 4px solid #0f172a;
  }
  .card-amber {
    background: #fffbeb;
    border-color: #fde68a;
    border-top: 4px solid #d97706;
  }
  .card-title {
    font-size: 10.2pt;
    font-weight: 800;
    color: #0f172a;
    margin: 0 0 6px 0;
  }
  .card-bad .card-title { color: #991b1b; }
  .card-good .card-title { color: #115e59; }
  .card ul {
    margin: 0;
    padding-left: 16px;
    font-size: 9.2pt;
    color: #334155;
  }
  .card li {
    margin-bottom: 5px;
  }
  .card p {
    margin: 0;
    font-size: 9pt;
    color: #334155;
    line-height: 1.38;
  }

  .section-label {
    font-size: 10.5pt;
    font-weight: 800;
    color: #0f172a;
    margin: 8px 0 7px 0;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .pill {
    display: inline-block;
    font-size: 7.5pt;
    font-weight: 700;
    padding: 2px 7px;
    border-radius: 999px;
    background: #e2e8f0;
    color: #0f172a;
  }
  .pill-teal { background: #ccfbf1; color: #0f766e; }
  .pill-green { background: #d1fae5; color: #065f46; }
  .pill-blue { background: #dbeafe; color: #1e40af; }
  .pill-amber { background: #fef3c7; color: #92400e; }

  .svg-frame {
    border: 1px solid #cbd5e1;
    border-radius: 10px;
    background: #f8fafc;
    padding: 8px;
    margin-bottom: 10px;
  }
  svg {
    width: 100%;
    height: auto;
    display: block;
  }

  /* Storyboard */
  .steps-row {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .step-box {
    flex: 1;
    border: 1px solid #cbd5e1;
    border-radius: 8px;
    padding: 9px 9px;
    background: #ffffff;
  }
  .step-num {
    display: inline-block;
    width: 19px;
    height: 19px;
    line-height: 19px;
    text-align: center;
    border-radius: 50%;
    background: #0d9488;
    color: #ffffff;
    font-size: 8.5pt;
    font-weight: 800;
    margin-bottom: 4px;
  }
  .step-title {
    font-size: 8.8pt;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 3px;
  }
  .step-desc {
    font-size: 8pt;
    color: #475569;
    line-height: 1.32;
  }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 8.6pt;
    margin-bottom: 10px;
  }
  th {
    background: #0f172a;
    color: #ffffff;
    text-align: left;
    padding: 6px 8px;
    font-weight: 700;
    font-size: 8.4pt;
  }
  td {
    padding: 6px 8px;
    border-bottom: 1px solid #e2e8f0;
    color: #334155;
    vertical-align: top;
  }
  tr:nth-child(even) td {
    background: #f8fafc;
  }
  code {
    font-family: "DejaVu Sans Mono", "Liberation Mono", monospace;
    font-size: 8pt;
    background: #e2e8f0;
    color: #0f172a;
    padding: 1px 4px;
    border-radius: 3px;
  }

  .callout-box {
    background: #f0fdfa;
    border: 1px solid #99f6e4;
    border-left: 5px solid #0d9488;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 9pt;
    color: #1e293b;
  }

  .footer {
    position: absolute;
    bottom: 8mm;
    left: 14mm;
    right: 14mm;
    border-top: 1px solid #cbd5e1;
    padding-top: 4px;
    display: flex;
    justify-content: space-between;
    font-size: 8pt;
    color: #64748b;
  }
</style>
</head>
<body>

<!-- ==================== PAGE 1: THE BIG IDEA ==================== -->
<div class="page">
  <div class="hero">
    <div class="hero-badge">NETSOL Internship • Executive Project Brief • Jira Board: OO</div>
    <h1>OmniOps Ontology Agent</h1>
    <div class="hero-sub">An AI Root-Cause &amp; Blast-Radius Assistant Grounded in a Governed Ontology</div>
    <p>
      Instead of letting an AI guess SQL queries or fire risky commands directly, <b>OmniOps</b> builds a
      structured digital map of our microservices (an <b>Ontology</b>), serves it through a standard
      <b>MCP Server</b>, and stages every proposed fix on a safe <b>Git-style branch</b> for human approval.
    </p>
  </div>

  <div class="section-label">1. Why Build an Ontology Layer? <span class="pill pill-teal">30-Second Comparison</span></div>
  <div class="grid-2">
    <div class="card card-bad">
      <div class="card-title">Standard AI (Raw Text-to-SQL / Vector RAG)</div>
      <ul>
        <li><b>Guesses Service Topology:</b> LLMs often hallucinate database joins or miss multi-hop upstream callers during an outage.</li>
        <li><b>No Shared Definitions:</b> Every prompt re-invents what "P0 critical" or "connection exhaustion" means.</li>
        <li><b>Unsafe Mutations:</b> Giving an agent direct API access to restart or rollback production services risks catastrophic outages.</li>
        <li><b>No Audit Trail:</b> Hard to trace why the AI picked a culprit or what state changed.</li>
      </ul>
    </div>
    <div class="card card-good">
      <div class="card-title">OmniOps (Governed Ontology + MCP Agent)</div>
      <ul>
        <li><b>Exact Graph Math:</b> Upstream blast radius and downstream dependencies are calculated deterministically—never guessed.</li>
        <li><b>Certified Semantics:</b> Objects, links, and metrics are discovered from schemas and certified before agent use.</li>
        <li><b>Branch-First Safety:</b> Agents cannot edit <code>main</code>; they stage rollbacks on isolated branches for a human to approve.</li>
        <li><b>Evidence Gate:</b> Every service or PR ID cited by the AI is verified against real MCP tool outputs.</li>
      </ul>
    </div>
  </div>

  <div class="section-label">2. How It Combines Your 3 Reference Architectures</div>
  <div class="grid-3">
    <div class="card card-navy">
      <div class="card-title">1. NVIDIA Auto-Ontology</div>
      <p style="margin-bottom:6px;"><span class="pill pill-blue">Discovery &amp; MCP</span></p>
      <p>Automatically scans raw SQLite/telemetry tables, drafts semantic concepts, enforces an SME <b>CERTIFIED</b> gate, checks if questions are answerable first, and exposes everything via <b>MCP</b>.</p>
    </div>
    <div class="card card-navy">
      <div class="card-title">2. Palantir Foundry</div>
      <p style="margin-bottom:6px;"><span class="pill pill-teal">Objects, Links &amp; Actions</span></p>
      <p>Splits the world into <b>Nouns</b> (<code>Service</code>, <code>Database</code>, <code>PullRequest</code>, <code>Incident</code>), <b>Relationships</b> (<code>CALLS</code>, <code>READS_WRITES</code>, <code>DEPLOYED_TO</code>), and validated <b>Actions</b> (<code>TriggerSafeRollback</code>).</p>
    </div>
    <div class="card card-navy">
      <div class="card-title">3. ModernRelay Omnigraph</div>
      <p style="margin-bottom:6px;"><span class="pill pill-amber">Branches &amp; Cedar Rules</span></p>
      <p>Adds Git-style state branching (<code>main</code> vs. <code>incident/*</code>), 3-way diffing, commit audit logs, and Cedar policy rules blocking unapproved production edits.</p>
    </div>
  </div>

  <div class="callout-box">
    <b>Bottom Line for Engineering Teams:</b> When a payment service breaks at 2:00 AM, OmniOps takes <b>seconds</b> to trace which customer-facing apps are impacted, pinpoints the exact Pull Request that caused it, and puts a verified rollback card in your <b>Approval Inbox</b>—with zero chance of unapproved production changes.
  </div>

  <div class="footer">
    <span>OmniOps Ontology Agent — Executive Overview | NETSOL Internship</span>
    <span>Page 1 of 5</span>
  </div>
</div>

<!-- ==================== PAGE 2: 4-TIER VISUAL ARCHITECTURE ==================== -->
<div class="page">
  <div class="page-kicker">Architecture Blueprint</div>
  <h1 class="page-title">How It Works: Clean 4-Tier Separation</h1>
  <p class="lead">
    Raw database logs stay cleanly separated from the AI. Every agent question flows through a certified Ontology and standardized MCP protocol boundary.
  </p>

  <div class="svg-frame">
    <svg viewBox="0 0 800 410" xmlns="http://www.w3.org/2000/svg" font-family="Lato, Liberation Sans, DejaVu Sans, Arial, sans-serif">
      <defs>
        <marker id="arr-p2" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#0f172a"/>
        </marker>
        <marker id="arr-p2-teal" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#0d9488"/>
        </marker>
      </defs>

      <!-- Tier 4 -->
      <rect x="20" y="12" width="760" height="76" rx="10" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.6"/>
      <text x="36" y="31" font-size="11" font-weight="800" fill="#1e3a8a">TIER 4 — CONSUMERS &amp; AUTONOMOUS AGENT LAYER</text>
      <rect x="38" y="38" width="225" height="40" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1.2"/>
      <text x="150" y="55" text-anchor="middle" font-size="10.5" font-weight="700" fill="#0f172a">Operations Center Web UI</text>
      <text x="150" y="69" text-anchor="middle" font-size="8.8" fill="#475569">Apple Liquid Glass UI + Approval Inbox</text>

      <rect x="288" y="38" width="235" height="40" rx="6" fill="#0f172a" stroke="#0f172a"/>
      <text x="405" y="55" text-anchor="middle" font-size="10.5" font-weight="700" fill="#ffffff">OmniOps SRE Agent</text>
      <text x="405" y="69" text-anchor="middle" font-size="8.8" fill="#99f6e4">Gemini 3.5 / Groq + Evidence Gate</text>

      <rect x="548" y="38" width="214" height="40" rx="6" fill="#ffffff" stroke="#93c5fd" stroke-width="1.2"/>
      <text x="655" y="55" text-anchor="middle" font-size="10.5" font-weight="700" fill="#0f172a">External MCP Clients</text>
      <text x="655" y="69" text-anchor="middle" font-size="8.8" fill="#475569">Claude / Cursor / Antigravity IDE</text>

      <!-- Arrows Tier 4 <-> Tier 3 -->
      <line x1="405" y1="78" x2="405" y2="108" stroke="#0f172a" stroke-width="2" marker-end="url(#arr-p2)"/>
      <line x1="655" y1="78" x2="655" y2="108" stroke="#0f172a" stroke-width="2" marker-end="url(#arr-p2)"/>
      <line x1="263" y1="58" x2="288" y2="58" stroke="#0f172a" stroke-width="1.8" marker-end="url(#arr-p2)"/>

      <!-- Tier 3 -->
      <rect x="20" y="112" width="760" height="72" rx="10" fill="#f0fdf4" stroke="#10b981" stroke-width="1.6"/>
      <text x="36" y="131" font-size="11" font-weight="800" fill="#065f46">TIER 3 — MODEL CONTEXT PROTOCOL (MCP) SERVER BOUNDARY (JSON-RPC 2.0 + In-Process)</text>
      <rect x="38" y="138" width="225" height="36" rx="6" fill="#ffffff" stroke="#6ee7b7"/>
      <text x="150" y="153" text-anchor="middle" font-size="10" font-weight="700" fill="#064e3b">MCP Resources</text>
      <text x="150" y="166" text-anchor="middle" font-size="8.4" fill="#475569">ontology://schema, topology, commits</text>

      <rect x="288" y="138" width="235" height="36" rx="6" fill="#ffffff" stroke="#6ee7b7"/>
      <text x="405" y="153" text-anchor="middle" font-size="10" font-weight="700" fill="#064e3b">7 MCP Tools</text>
      <text x="405" y="166" text-anchor="middle" font-size="8.4" fill="#475569">Blast Radius, PR Suspect, Stage Action</text>

      <rect x="548" y="138" width="214" height="36" rx="6" fill="#ffffff" stroke="#6ee7b7"/>
      <text x="655" y="153" text-anchor="middle" font-size="10" font-weight="700" fill="#064e3b">MCP Runbook Prompts</text>
      <text x="655" y="166" text-anchor="middle" font-size="8.4" fill="#475569">sre_rca_runbook, pr_risk_gate</text>

      <!-- Arrows Tier 3 <-> Tier 2 -->
      <line x1="150" y1="184" x2="150" y2="212" stroke="#0d9488" stroke-width="2" marker-end="url(#arr-p2-teal)"/>
      <line x1="405" y1="184" x2="405" y2="212" stroke="#0d9488" stroke-width="2" marker-end="url(#arr-p2-teal)"/>
      <line x1="655" y1="184" x2="655" y2="212" stroke="#0d9488" stroke-width="2" marker-end="url(#arr-p2-teal)"/>

      <!-- Tier 2 -->
      <rect x="20" y="216" width="760" height="96" rx="10" fill="#f0fdfa" stroke="#0d9488" stroke-width="2.2"/>
      <text x="36" y="236" font-size="11" font-weight="800" fill="#115e59">TIER 2 — GOVERNED ONTOLOGY ENGINE (THE BRAIN &amp; GUARDRAILS)</text>

      <rect x="38" y="245" width="225" height="55" rx="6" fill="#ffffff" stroke="#5eead4" stroke-width="1.3"/>
      <text x="150" y="263" text-anchor="middle" font-size="10" font-weight="800" fill="#0f172a">Auto-Ontology Discovery</text>
      <text x="150" y="277" text-anchor="middle" font-size="8.4" fill="#475569">Schema Profiler + DRAFT/CERTIFIED</text>
      <text x="150" y="290" text-anchor="middle" font-size="8.4" fill="#0d9488" font-weight="700">+ Pre-Flight Answerability Check</text>

      <rect x="288" y="245" width="235" height="55" rx="6" fill="#ffffff" stroke="#5eead4" stroke-width="1.3"/>
      <text x="405" y="263" text-anchor="middle" font-size="10" font-weight="800" fill="#0f172a">Palantir Semantic &amp; Kinetic</text>
      <text x="405" y="277" text-anchor="middle" font-size="8.4" fill="#475569">6 Objects, 7 Links, Reverse-BFS Graph</text>
      <text x="405" y="290" text-anchor="middle" font-size="8.4" fill="#0d9488" font-weight="700">+ Validated Kinetic Actions</text>

      <rect x="548" y="245" width="214" height="55" rx="6" fill="#ffffff" stroke="#5eead4" stroke-width="1.3"/>
      <text x="655" y="263" text-anchor="middle" font-size="10" font-weight="800" fill="#0f172a">Omnigraph VCS &amp; Policies</text>
      <text x="655" y="277" text-anchor="middle" font-size="8.4" fill="#475569">Branches (main vs incident/*)</text>
      <text x="655" y="290" text-anchor="middle" font-size="8.4" fill="#d97706" font-weight="700">+ Cedar Policy Gate + 3-Way Merge</text>

      <!-- Arrows Tier 2 <-> Tier 1 -->
      <line x1="250" y1="312" x2="250" y2="338" stroke="#0f172a" stroke-width="2" marker-end="url(#arr-p2)"/>
      <line x1="550" y1="312" x2="550" y2="338" stroke="#0f172a" stroke-width="2" marker-end="url(#arr-p2)"/>

      <!-- Tier 1 -->
      <rect x="20" y="342" width="760" height="56" rx="10" fill="#f1f5f9" stroke="#64748b" stroke-width="1.5"/>
      <text x="400" y="364" text-anchor="middle" font-size="11" font-weight="800" fill="#0f172a">TIER 1 — RAW ENTERPRISE DATA &amp; TELEMETRY STORE (SQLite + Manifests)</text>
      <text x="400" y="382" text-anchor="middle" font-size="9" fill="#475569">raw_services  •  raw_service_calls  •  raw_endpoints  •  raw_databases  •  raw_pull_requests  •  raw_incidents  •  raw_wifi_telemetry (DRAFT)</text>
    </svg>
  </div>

  <div class="grid-4">
    <div class="card">
      <div class="card-title">Tier 1: Raw Data</div>
      <p>Stores raw service tables, PR logs, and telemetry—plus an uncertified table to prove our certification gate works.</p>
    </div>
    <div class="card">
      <div class="card-title">Tier 2: Ontology</div>
      <p>Turns raw rows into typed Objects, calculates exact blast radius, and isolates proposed fixes on Git-style branches.</p>
    </div>
    <div class="card">
      <div class="card-title">Tier 3: MCP Server</div>
      <p>Standard protocol interface so both our built-in agent and tools like Cursor or Claude share one source of truth.</p>
    </div>
    <div class="card">
      <div class="card-title">Tier 4: Agent &amp; UI</div>
      <p>Runs root-cause investigations, blocks hallucinated IDs, and lets humans approve fixes in one click.</p>
    </div>
  </div>

  <div class="footer">
    <span>OmniOps Ontology Agent — Executive Overview | NETSOL Internship</span>
    <span>Page 2 of 5</span>
  </div>
</div>

<!-- ==================== PAGE 3: LIVE DEMO WALKTHROUGH (INC-409) ==================== -->
<div class="page">
  <div class="page-kicker">Live Demo Scenario</div>
  <h1 class="page-title">What You Will See: Solving Incident INC-409</h1>
  <p class="lead">
    A real-world fintech outage simulation: <b>PaymentGatewayService</b> suddenly throws HTTP 500 errors. Watch how the Ontology Agent traces impact, correlates the bad deployment, and stages a safe rollback.
  </p>

  <div class="svg-frame">
    <svg viewBox="0 0 800 330" xmlns="http://www.w3.org/2000/svg" font-family="Lato, Liberation Sans, DejaVu Sans, Arial, sans-serif">
      <defs>
        <marker id="arr-p3-red" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#dc2626"/>
        </marker>
        <marker id="arr-p3-amb" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#d97706"/>
        </marker>
        <marker id="arr-p3-grn" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#10b981"/>
        </marker>
      </defs>

      <!-- Zone Labels -->
      <rect x="14" y="14" width="296" height="236" rx="10" fill="#fffbeb" stroke="#fcd34d" stroke-dasharray="5,4"/>
      <text x="162" y="34" text-anchor="middle" font-size="9.5" font-weight="800" fill="#b45309">UPSTREAM BLAST RADIUS (P0 IMPACTED)</text>

      <rect x="326" y="14" width="224" height="236" rx="10" fill="#fef2f2" stroke="#fca5a5" stroke-dasharray="5,4"/>
      <text x="438" y="34" text-anchor="middle" font-size="9.5" font-weight="800" fill="#991b1b">ROOT INCIDENT &amp; CULPRIT PR</text>

      <rect x="566" y="14" width="220" height="236" rx="10" fill="#f8fafc" stroke="#cbd5e1" stroke-dasharray="5,4"/>
      <text x="676" y="34" text-anchor="middle" font-size="9.5" font-weight="800" fill="#334155">DOWNSTREAM DEPENDENCIES</text>

      <!-- Upstream Nodes -->
      <rect x="28" y="54" width="128" height="58" rx="8" fill="#ffffff" stroke="#d97706" stroke-width="1.8"/>
      <text x="92" y="74" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">MobileAppGateway</text>
      <text x="92" y="88" text-anchor="middle" font-size="8.2" fill="#b45309" font-weight="700">Tier P0 • Hop 2</text>
      <text x="92" y="101" text-anchor="middle" font-size="8" fill="#64748b">DEGRADED (Checkout fails)</text>

      <rect x="28" y="142" width="128" height="58" rx="8" fill="#ffffff" stroke="#d97706" stroke-width="1.8"/>
      <text x="92" y="162" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">WebStorefront</text>
      <text x="92" y="176" text-anchor="middle" font-size="8.2" fill="#b45309" font-weight="700">Tier P0 • Hop 2</text>
      <text x="92" y="189" text-anchor="middle" font-size="8" fill="#64748b">DEGRADED (Checkout fails)</text>

      <rect x="178" y="96" width="120" height="62" rx="8" fill="#ffffff" stroke="#d97706" stroke-width="2"/>
      <text x="238" y="117" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">CheckoutService</text>
      <text x="238" y="131" text-anchor="middle" font-size="8.2" fill="#b45309" font-weight="700">Tier P0 • Hop 1</text>
      <text x="238" y="145" text-anchor="middle" font-size="8" fill="#dc2626" font-weight="700">DEGRADED (Hard Call)</text>

      <!-- PR Suspect Badge -->
      <rect x="342" y="46" width="192" height="44" rx="7" fill="#fff1f2" stroke="#e11d48" stroke-width="1.6"/>
      <text x="438" y="63" text-anchor="middle" font-size="9.2" font-weight="800" fill="#9f1239">PR-882 (Culprit Deployed 22m ago)</text>
      <text x="438" y="78" text-anchor="middle" font-size="8" fill="#475569">"Refactor ledger DB connection pool"</text>

      <!-- Root Failing Node -->
      <rect x="342" y="114" width="192" height="72" rx="9" fill="#dc2626" stroke="#991b1b" stroke-width="2"/>
      <text x="438" y="136" text-anchor="middle" font-size="10.8" font-weight="800" fill="#ffffff">PaymentGatewayService</text>
      <text x="438" y="152" text-anchor="middle" font-size="8.8" fill="#fee2e2" font-weight="700">INC-409 • CRITICAL • v2.5.0</text>
      <text x="438" y="168" text-anchor="middle" font-size="8.5" fill="#ffffff">Error Rate: 18.4% | p99: 2,450 ms</text>
      <text x="438" y="180" text-anchor="middle" font-size="7.8" fill="#fecaca">Last Stable: v2.4.1 (Rollback Target)</text>

      <!-- Downstream DB -->
      <rect x="582" y="114" width="190" height="72" rx="9" fill="#ffffff" stroke="#dc2626" stroke-width="2"/>
      <text x="677" y="135" text-anchor="middle" font-size="10.2" font-weight="800" fill="#0f172a">AccountLedgerDB</text>
      <text x="677" y="150" text-anchor="middle" font-size="8.4" fill="#dc2626" font-weight="700">PostgreSQL • CONNECTION EXHAUSTED</text>
      <text x="677" y="165" text-anchor="middle" font-size="8.4" fill="#334155">498 / 500 Conns (99.6% Full)</text>
      <text x="677" y="178" text-anchor="middle" font-size="8" fill="#64748b">CPU: 94.2%</text>

      <!-- Healthy Neighbors -->
      <rect x="342" y="264" width="192" height="50" rx="8" fill="#ecfdf5" stroke="#10b981" stroke-width="1.5"/>
      <text x="438" y="284" text-anchor="middle" font-size="9.5" font-weight="800" fill="#065f46">FraudDetectionService</text>
      <text x="438" y="299" text-anchor="middle" font-size="8.2" fill="#047857">HEALTHY (Not affected by INC-409)</text>

      <rect x="582" y="264" width="190" height="50" rx="8" fill="#ecfdf5" stroke="#10b981" stroke-width="1.5"/>
      <text x="677" y="284" text-anchor="middle" font-size="9.5" font-weight="800" fill="#065f46">NotificationWorker</text>
      <text x="677" y="299" text-anchor="middle" font-size="8.2" fill="#047857">HEALTHY (Async queue isolated)</text>

      <rect x="28" y="264" width="270" height="50" rx="8" fill="#f1f5f9" stroke="#94a3b8"/>
      <text x="163" y="283" text-anchor="middle" font-size="9" font-weight="800" fill="#0f172a">Blast Radius Severity Score = 30</text>
      <text x="163" y="298" text-anchor="middle" font-size="8.2" fill="#475569">3 Upstream P0 Services × 10 = High Priority Triage</text>

      <!-- Graph Edges -->
      <line x1="156" y1="84" x2="176" y2="112" stroke="#d97706" stroke-width="2" marker-end="url(#arr-p3-amb)"/>
      <line x1="156" y1="170" x2="176" y2="142" stroke="#d97706" stroke-width="2" marker-end="url(#arr-p3-amb)"/>
      <line x1="298" y1="127" x2="340" y2="142" stroke="#dc2626" stroke-width="2.2" marker-end="url(#arr-p3-red)"/>
      <line x1="438" y1="90" x2="438" y2="112" stroke="#dc2626" stroke-width="2" marker-end="url(#arr-p3-red)"/>
      <line x1="534" y1="150" x2="580" y2="150" stroke="#dc2626" stroke-width="2.2" marker-end="url(#arr-p3-red)"/>
      <line x1="438" y1="186" x2="438" y2="262" stroke="#10b981" stroke-width="1.6" stroke-dasharray="4,3" marker-end="url(#arr-p3-grn)"/>
    </svg>
  </div>

  <div class="section-label">Step-by-Step Live Investigation Trace</div>
  <div class="steps-row">
    <div class="step-box">
      <div class="step-num">1</div>
      <div class="step-title">Alert Triggered</div>
      <div class="step-desc">Engineer asks: <i>"Analyze INC-409 on PaymentGateway and propose a fix."</i></div>
    </div>
    <div class="step-box">
      <div class="step-num">2</div>
      <div class="step-title">Answerable Gate</div>
      <div class="step-desc">MCP checks that <code>Incident</code>, <code>Service</code>, and <code>PullRequest</code> are certified in Ontology.</div>
    </div>
    <div class="step-box">
      <div class="step-num">3</div>
      <div class="step-title">Blast Radius</div>
      <div class="step-desc">Reverse graph traversal finds 3 upstream <code>P0</code> services affected: Checkout, Mobile &amp; Web.</div>
    </div>
    <div class="step-box">
      <div class="step-num">4</div>
      <div class="step-title">PR Correlation</div>
      <div class="step-desc">Links DB saturation (99.6%) with <code>PR-882</code> merged 22 minutes earlier into <code>v2.5.0</code>.</div>
    </div>
    <div class="step-box">
      <div class="step-num">5</div>
      <div class="step-title">Safe Branch Fix</div>
      <div class="step-desc">Agent stages <code>TriggerSafeRollback(v2.4.1)</code> on branch <code>incident/INC-409-rollback</code> for approval.</div>
    </div>
  </div>

  <div class="footer">
    <span>OmniOps Ontology Agent — Executive Overview | NETSOL Internship</span>
    <span>Page 3 of 5</span>
  </div>
</div>

<!-- ==================== PAGE 4: SAFETY, OMNIGRAPH BRANCHING & MCP ==================== -->
<div class="page">
  <div class="page-kicker">Safety &amp; Ecosystem</div>
  <h1 class="page-title">Built-In Guardrails: Git Branches &amp; MCP Hub</h1>
  <p class="lead">
    Autonomous agents should prepare the exact fix—never push blindly to production. OmniOps protects <code>main</code> with Omnigraph branching and Cedar policies.
  </p>

  <div class="section-label">1. Omnigraph Copy-on-Write Branching &amp; Cedar Policy Shield</div>
  <div class="svg-frame">
    <svg viewBox="0 0 800 215" xmlns="http://www.w3.org/2000/svg" font-family="Lato, Liberation Sans, DejaVu Sans, Arial, sans-serif">
      <defs>
        <marker id="arr-p4a-blue" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#2563eb"/>
        </marker>
      </defs>

      <!-- Main Branch Header & Track -->
      <text x="24" y="28" font-size="10" font-weight="800" fill="#065f46">PRODUCTION BRANCH (main)</text>
      <line x1="160" y1="94" x2="620" y2="94" stroke="#10b981" stroke-width="4"/>

      <!-- C0 & Left Label -->
      <text x="24" y="90" text-anchor="start" font-size="8.6" font-weight="700" fill="#0f172a">Live Topology</text>
      <text x="24" y="104" text-anchor="start" font-size="8" font-weight="700" fill="#dc2626">v2.5.0 (CRITICAL)</text>
      <circle cx="160" cy="94" r="14" fill="#059669" stroke="#ffffff" stroke-width="2.5"/>
      <text x="160" y="98" text-anchor="middle" font-size="9" font-weight="800" fill="#ffffff">C0</text>

      <!-- Cedar Block Sign above main track -->
      <rect x="275" y="30" width="230" height="44" rx="7" fill="#fef2f2" stroke="#dc2626" stroke-width="1.6"/>
      <text x="390" y="48" text-anchor="middle" font-size="8.8" font-weight="800" fill="#991b1b">CEDAR POLICY BLOCK</text>
      <text x="390" y="62" text-anchor="middle" font-size="7.8" fill="#7f1d1d">Agent forbidden from direct write to main</text>
      <line x1="390" y1="74" x2="390" y2="94" stroke="#dc2626" stroke-width="2" stroke-dasharray="3,2"/>
      <circle cx="390" cy="94" r="5" fill="#dc2626"/>

      <!-- M1 Merge Commit & Right Label -->
      <circle cx="620" cy="94" r="15" fill="#059669" stroke="#ffffff" stroke-width="2.5"/>
      <text x="620" y="98" text-anchor="middle" font-size="9" font-weight="800" fill="#ffffff">M1</text>
      <text x="646" y="90" text-anchor="start" font-size="8.6" font-weight="700" fill="#065f46">3-Way Merge Applied</text>
      <text x="646" y="104" text-anchor="start" font-size="8" fill="#059669" font-weight="700">v2.4.1 (HEALTHY)</text>

      <!-- Branch Fork -->
      <text x="24" y="158" font-size="9.5" font-weight="800" fill="#1e40af">ISOLATED AGENT BRANCH</text>
      <text x="24" y="172" font-size="8" fill="#475569">incident/INC-409-rollback</text>

      <path d="M 160 108 C 160 154, 190 164, 220 164 L 550 164 C 585 164, 610 144, 617 110" fill="none" stroke="#2563eb" stroke-width="3" marker-end="url(#arr-p4a-blue)"/>

      <circle cx="260" cy="164" r="13" fill="#2563eb" stroke="#ffffff" stroke-width="2"/>
      <text x="260" y="168" text-anchor="middle" font-size="8.5" font-weight="800" fill="#ffffff">C1</text>
      <text x="260" y="192" text-anchor="middle" font-size="8.2" font-weight="700" fill="#1e3a8a">Agent Stages Rollback</text>
      <text x="260" y="204" text-anchor="middle" font-size="7.6" fill="#475569">Simulates healthy preview</text>

      <rect x="355" y="138" width="185" height="52" rx="8" fill="#eff6ff" stroke="#3b82f6" stroke-width="1.5"/>
      <text x="447" y="158" text-anchor="middle" font-size="9" font-weight="800" fill="#1e40af">Human Approval Inbox</text>
      <text x="447" y="172" text-anchor="middle" font-size="8" fill="#334155">SRE reviews diff &amp; clicks</text>
      <text x="447" y="183" text-anchor="middle" font-size="8" font-weight="700" fill="#059669">"Approve &amp; Merge"</text>
    </svg>
  </div>

  <div class="section-label">2. One Certified MCP Server + Anti-Hallucination Gate</div>
  <div class="svg-frame">
    <svg viewBox="0 0 800 175" xmlns="http://www.w3.org/2000/svg" font-family="Lato, Liberation Sans, DejaVu Sans, Arial, sans-serif">
      <defs>
        <marker id="arr-p4b" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#0d9488"/>
        </marker>
      </defs>

      <!-- Left Clients -->
      <rect x="24" y="18" width="190" height="40" rx="7" fill="#ffffff" stroke="#94a3b8"/>
      <text x="119" y="36" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">Built-In SRE Agent</text>
      <text x="119" y="49" text-anchor="middle" font-size="8" fill="#475569">Gemini -&gt; Groq -&gt; Offline</text>

      <rect x="24" y="68" width="190" height="40" rx="7" fill="#ffffff" stroke="#94a3b8"/>
      <text x="119" y="86" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">Cursor / Claude Desktop</text>
      <text x="119" y="99" text-anchor="middle" font-size="8" fill="#475569">External MCP Clients (JSON-RPC)</text>

      <rect x="24" y="118" width="190" height="40" rx="7" fill="#ffffff" stroke="#94a3b8"/>
      <text x="119" y="136" text-anchor="middle" font-size="9.5" font-weight="800" fill="#0f172a">Antigravity IDE</text>
      <text x="119" y="149" text-anchor="middle" font-size="8" fill="#475569">Developer Workflow Integration</text>

      <!-- Center Hub -->
      <rect x="275" y="24" width="230" height="128" rx="10" fill="#0f172a" stroke="#0d9488" stroke-width="2.5"/>
      <text x="390" y="49" text-anchor="middle" font-size="11" font-weight="800" fill="#ffffff">OmniOps MCP Server</text>
      <text x="390" y="69" text-anchor="middle" font-size="8.6" fill="#99f6e4">• 6 Ontology Resources</text>
      <text x="390" y="86" text-anchor="middle" font-size="8.6" fill="#99f6e4">• 7 Validated Graph Tools</text>
      <text x="390" y="103" text-anchor="middle" font-size="8.6" fill="#99f6e4">• 2 SRE Runbook Prompts</text>
      <text x="390" y="126" text-anchor="middle" font-size="8.2" fill="#cbd5e1">Single Source of Certified Truth</text>

      <!-- Right Verifier -->
      <rect x="562" y="24" width="214" height="128" rx="10" fill="#f0fdfa" stroke="#0d9488" stroke-width="2"/>
      <text x="669" y="49" text-anchor="middle" font-size="10.2" font-weight="800" fill="#115e59">Evidence Verifier Gate</text>
      <text x="669" y="72" text-anchor="middle" font-size="8.4" fill="#334155">1. Every SVC-*, PR-*, DB-*</text>
      <text x="669" y="86" text-anchor="middle" font-size="8.4" fill="#334155">ID must appear in tool trace.</text>
      <text x="669" y="108" text-anchor="middle" font-size="8.4" fill="#334155">2. Fabricated IDs are blocked</text>
      <text x="669" y="122" text-anchor="middle" font-size="8.4" fill="#334155">before reaching the engineer.</text>
      <text x="669" y="140" text-anchor="middle" font-size="8.4" font-weight="800" fill="#059669">0% Unverified Claims</text>

      <line x1="214" y1="38" x2="272" y2="66" stroke="#0d9488" stroke-width="1.8" marker-end="url(#arr-p4b)"/>
      <line x1="214" y1="88" x2="272" y2="88" stroke="#0d9488" stroke-width="1.8" marker-end="url(#arr-p4b)"/>
      <line x1="214" y1="138" x2="272" y2="112" stroke="#0d9488" stroke-width="1.8" marker-end="url(#arr-p4b)"/>
      <line x1="505" y1="88" x2="559" y2="88" stroke="#0d9488" stroke-width="2.2" marker-end="url(#arr-p4b)"/>
    </svg>
  </div>

  <div class="grid-3">
    <div class="card">
      <div class="card-title">Zero Unapproved Edits</div>
      <p>Agents can simulate fixes safely on branches; only a human click merges to production.</p>
    </div>
    <div class="card">
      <div class="card-title">Zero Vendor Lock-In</div>
      <p>Runs with Gemini, auto-falls back to Groq/OpenRouter, or works 100% offline via deterministic graph reasoning.</p>
    </div>
    <div class="card">
      <div class="card-title">Zero Secret Leaks</div>
      <p>Server-only <code>.env</code> loading with automatic API key redaction in diagnostics (matching <code>Voice_Coach</code>).</p>
    </div>
  </div>

  <div class="footer">
    <span>OmniOps Ontology Agent — Executive Overview | NETSOL Internship</span>
    <span>Page 4 of 5</span>
  </div>
</div>

<!-- ==================== PAGE 5: 5-PHASE PLAN & JIRA TRACKING ==================== -->
<div class="page">
  <div class="page-kicker">Execution Roadmap &amp; Diagnostics</div>
  <h1 class="page-title">5-Phase Delivery Plan &amp; Jira (OO) Tracking</h1>
  <p class="lead">
    All 6 workstreams and 70 Jira issues on board <b>OO (Omni-ops)</b> are <b>DONE</b>—verified by <b>45/45 automated tests</b> (~0.3s), live <b>Gemini &amp; Groq</b> cloud RCA runs, and an active <b>omniops-ontology</b> MCP server.
  </p>

  <div class="svg-frame">
    <svg viewBox="0 0 800 100" xmlns="http://www.w3.org/2000/svg" font-family="Lato, Liberation Sans, DejaVu Sans, Arial, sans-serif">
      <defs>
        <marker id="arr-p5" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
          <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748b"/>
        </marker>
      </defs>

      <!-- P0 -->
      <rect x="12" y="16" width="114" height="68" rx="8" fill="#059669"/>
      <text x="69" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 0 (OO-1)</text>
      <text x="69" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">Specs, PDF &amp; Jira</text>
      <text x="69" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (4 Tasks)</text>

      <!-- P1 -->
      <rect x="144" y="16" width="114" height="68" rx="8" fill="#059669"/>
      <text x="201" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 1 (OO-3)</text>
      <text x="201" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">Auto-Ontology</text>
      <text x="201" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (11/11 Pass)</text>

      <!-- P2 -->
      <rect x="276" y="16" width="114" height="68" rx="8" fill="#059669"/>
      <text x="333" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 2 (OO-4)</text>
      <text x="333" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">Graph &amp; Branches</text>
      <text x="333" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (12/12 Pass)</text>

      <!-- P3 -->
      <rect x="408" y="16" width="114" height="68" rx="8" fill="#059669"/>
      <text x="465" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 3 (OO-5)</text>
      <text x="465" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">MCP Server</text>
      <text x="465" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (7/7 Pass)</text>

      <!-- P4 -->
      <rect x="540" y="16" width="114" height="68" rx="8" fill="#059669"/>
      <text x="597" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 4 (OO-6)</text>
      <text x="597" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">Agent &amp; Verifier</text>
      <text x="597" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (11/11 Pass)</text>

      <!-- P5 -->
      <rect x="672" y="16" width="114" height="68" rx="8" fill="#0d9488"/>
      <text x="729" y="37" text-anchor="middle" font-size="9.5" font-weight="800" fill="#ffffff">Phase 5 (OO-7)</text>
      <text x="729" y="52" text-anchor="middle" font-size="8" fill="#d1fae5">Glass UI &amp; E2E</text>
      <text x="729" y="69" text-anchor="middle" font-size="8" font-weight="800" fill="#ffffff">DONE (4/4 Pass)</text>

      <line x1="126" y1="50" x2="142" y2="50" stroke="#64748b" stroke-width="1.8" marker-end="url(#arr-p5)"/>
      <line x1="258" y1="50" x2="274" y2="50" stroke="#64748b" stroke-width="1.8" marker-end="url(#arr-p5)"/>
      <line x1="390" y1="50" x2="406" y2="50" stroke="#64748b" stroke-width="1.8" marker-end="url(#arr-p5)"/>
      <line x1="522" y1="50" x2="538" y2="50" stroke="#64748b" stroke-width="1.8" marker-end="url(#arr-p5)"/>
      <line x1="654" y1="50" x2="670" y2="50" stroke="#64748b" stroke-width="1.8" marker-end="url(#arr-p5)"/>
    </svg>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:15%;">Phase &amp; Jira</th>
        <th style="width:20%;">Focus Area</th>
        <th style="width:40%;">What Gets Built (Plain-English Deliverable)</th>
        <th style="width:25%;">Task IDs &amp; Gate</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><b>Phase 0</b><br><code>OO-1</code></td>
        <td>Architecture &amp; Planning</td>
        <td>PRD, System RFC, Ontology Spec, MCP Spec, ADRs, Executive PDF &amp; Jira <code>OO</code> alignment.</td>
        <td><code>OO-2, OO-8..OO-10</code><br><span class="pill pill-green">Done (4 Tasks)</span></td>
      </tr>
      <tr>
        <td><b>Phase 1</b><br><code>OO-3</code></td>
        <td>Auto-Ontology &amp; Schema</td>
        <td>Pydantic models, SQLite seed data, automatic table discovery, SME certification gate &amp; answerability checker.</td>
        <td><code>OO-11..OO-16</code><br><span class="pill pill-green">Done • 11/11 Tests</span></td>
      </tr>
      <tr>
        <td><b>Phase 2</b><br><code>OO-4</code></td>
        <td>Omnigraph &amp; Policies</td>
        <td>Directed graph traversal, upstream blast radius, PR suspect ranking, Git-style branches, 3-way merge &amp; Cedar policy rules.</td>
        <td><code>OO-17..OO-22</code><br><span class="pill pill-green">Done • 12/12 Tests</span></td>
      </tr>
      <tr>
        <td><b>Phase 3</b><br><code>OO-5</code></td>
        <td>MCP Server Layer</td>
        <td>Exposes 6 Resources, 7 Tools, and 2 Prompts over JSON-RPC 2.0 (Stdio/HTTP) &amp; in-process Python calls.</td>
        <td><code>OO-23..OO-27</code><br><span class="pill pill-green">Done • 7/7 Tests</span></td>
      </tr>
      <tr>
        <td><b>Phase 4</b><br><code>OO-6</code></td>
        <td>Autonomous Agent</td>
        <td>Gemini/Groq/Offline investigation loop with deterministic Evidence Verifier blocking hallucinated IDs.</td>
        <td><code>OO-28..OO-33</code><br><span class="pill pill-green">Done • 11/11 Tests</span></td>
      </tr>
      <tr>
        <td><b>Phase 5</b><br><code>OO-7</code></td>
        <td>Operations Center UI</td>
        <td>FastAPI web server, Apple Liquid Glass SVG Topology, Live MCP console, Approval Inbox &amp; final QA report.</td>
        <td><code>OO-34..OO-38</code><br><span class="pill pill-green">Done • 4/4 E2E + Live</span></td>
      </tr>
    </tbody>
  </table>

  <div class="section-label">3 Golden Demo Scenarios Built Into the Test Suite</div>
  <div class="grid-3">
    <div class="card card-bad">
      <div class="card-title">INC-409 (SEV1)</div>
      <p><b>PaymentGateway 500s:</b> Caused by <code>PR-882</code> leaking PostgreSQL connections on <code>AccountLedgerDB</code> (498/500 conns).</p>
    </div>
    <div class="card card-amber">
      <div class="card-title">INC-512 (SEV2)</div>
      <p><b>FraudEngine Latency:</b> Caused by <code>PR-879</code> deploying an unindexed schema migration onto <code>OrderStore</code>.</p>
    </div>
    <div class="card card-good">
      <div class="card-title">INC-601 (SEV2)</div>
      <p><b>MobileGateway Saturation:</b> Caused by <code>PR-885</code> overloading <code>SessionRedis</code> cache connections.</p>
    </div>
  </div>

  <div class="footer">
    <span>OmniOps Ontology Agent — Executive Overview | NETSOL Internship</span>
    <span>Page 5 of 5</span>
  </div>
</div>

</body>
</html>
"""


def find_chrome() -> str:
    for candidate in ("/usr/bin/google-chrome", "google-chrome", "chromium", "chromium-browser"):
        resolved = shutil.which(candidate) if "/" not in candidate else candidate
        if resolved and Path(resolved).exists():
            return resolved
    raise FileNotFoundError("Google Chrome / Chromium binary not found for PDF rendering.")


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(HTML_CONTENT, encoding="utf-8")

    chrome = find_chrome()
    cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={PDF_PATH}",
        HTML_PATH.as_uri(),
    ]
    subprocess.run(cmd, check=True)
    print(f"Generated Senior Executive Overview PDF: {PDF_PATH}")


if __name__ == "__main__":
    main()
