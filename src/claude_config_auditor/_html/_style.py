"""CSS for the HTML report. Single large string kept in its own module
so it can be edited without scrolling past the Python that consumes it."""

_CSS = r"""
/* ============ Theme tokens ============
   :root holds the light theme. Dark theme overrides via either
   [data-theme="dark"] (manual override) or @media prefers-color-scheme.
   ===================================== */
:root {
  --bg: #f7f6f3;
  --surface: #ffffff;
  --surface-alt: #fbfaf7;
  --border: #e6e3dc;
  --border-strong: #cfccc3;
  --border-faint: #efece5;

  --ink-1: #0c0c0b;
  --ink-2: #4d4b46;
  --ink-3: #8a8780;
  --ink-4: #b4b1a8;

  --critical: #cc2c1f;
  --critical-bg: #fdedea;
  --critical-line: #f0c0b9;
  --warning: #b87618;
  --warning-bg: #fbf3e3;
  --warning-line: #e9d4a4;
  --info: #1f5ec0;
  --info-bg: #ebf1fb;
  --info-line: #c2d2ee;
  --ok: #1d7a45;
  --ok-bg: #e8f3ec;
  --ok-line: #b8d8c2;

  --cat-claude-md: #2b6358;
  --cat-claude-md-bg: rgba(43, 99, 88, 0.12);
  --cat-agent: #6b3a18;
  --cat-agent-bg: rgba(107, 58, 24, 0.12);
  --cat-skill: #2e4b86;
  --cat-skill-bg: rgba(46, 75, 134, 0.12);
  --cat-rule: #6a2e54;
  --cat-rule-bg: rgba(106, 46, 84, 0.12);

  --sans: "SF Pro Text", -apple-system, BlinkMacSystemFont, system-ui,
          "Segoe UI", "Helvetica Neue", sans-serif;
  --mono: "JetBrains Mono", "SF Mono", "Cascadia Mono", Menlo, Consolas,
          ui-monospace, monospace;

  color-scheme: light;
}

/* Dark — applied when user OS prefers dark AND no manual override,
   OR when manual override sets dark explicitly. */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg: #0d1014;
    --surface: #161a21;
    --surface-alt: #1a1f28;
    --border: #262c37;
    --border-strong: #353c4a;
    --border-faint: #1f242d;

    --ink-1: #e9ecf1;
    --ink-2: #a3a9b6;
    --ink-3: #6c7484;
    --ink-4: #4d5462;

    --critical: #ff5b62;
    --critical-bg: rgba(255, 91, 98, 0.12);
    --critical-line: rgba(255, 91, 98, 0.3);
    --warning: #f3b04a;
    --warning-bg: rgba(243, 176, 74, 0.12);
    --warning-line: rgba(243, 176, 74, 0.3);
    --info: #5fa3ff;
    --info-bg: rgba(95, 163, 255, 0.12);
    --info-line: rgba(95, 163, 255, 0.3);
    --ok: #5ad095;
    --ok-bg: rgba(90, 208, 149, 0.12);
    --ok-line: rgba(90, 208, 149, 0.3);

    --cat-claude-md: #6dc9b3;
    --cat-claude-md-bg: rgba(109, 201, 179, 0.15);
    --cat-agent: #e09368;
    --cat-agent-bg: rgba(224, 147, 104, 0.15);
    --cat-skill: #7fa9e8;
    --cat-skill-bg: rgba(127, 169, 232, 0.15);
    --cat-rule: #d68caf;
    --cat-rule-bg: rgba(214, 140, 175, 0.15);

    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --bg: #0d1014;
  --surface: #161a21;
  --surface-alt: #1a1f28;
  --border: #262c37;
  --border-strong: #353c4a;
  --border-faint: #1f242d;

  --ink-1: #e9ecf1;
  --ink-2: #a3a9b6;
  --ink-3: #6c7484;
  --ink-4: #4d5462;

  --critical: #ff5b62;
  --critical-bg: rgba(255, 91, 98, 0.12);
  --critical-line: rgba(255, 91, 98, 0.3);
  --warning: #f3b04a;
  --warning-bg: rgba(243, 176, 74, 0.12);
  --warning-line: rgba(243, 176, 74, 0.3);
  --info: #5fa3ff;
  --info-bg: rgba(95, 163, 255, 0.12);
  --info-line: rgba(95, 163, 255, 0.3);
  --ok: #5ad095;
  --ok-bg: rgba(90, 208, 149, 0.12);
  --ok-line: rgba(90, 208, 149, 0.3);

  --cat-claude-md: #6dc9b3;
  --cat-claude-md-bg: rgba(109, 201, 179, 0.15);
  --cat-agent: #e09368;
  --cat-agent-bg: rgba(224, 147, 104, 0.15);
  --cat-skill: #7fa9e8;
  --cat-skill-bg: rgba(127, 169, 232, 0.15);
  --cat-rule: #d68caf;
  --cat-rule-bg: rgba(214, 140, 175, 0.15);

  color-scheme: dark;
}

* { box-sizing: border-box; }
html { font-size: 16px; -webkit-font-smoothing: antialiased; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink-1);
  font-family: var(--sans);
  font-size: 13.5px;
  line-height: 1.55;
  font-feature-settings: "kern", "liga", "ss01";
  font-variant-numeric: tabular-nums;
}

.doc {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 32px 64px;
}

/* ============ Top bar ============ */
.topbar {
  display: grid;
  grid-template-columns: auto 1fr auto;
  gap: 24px;
  align-items: center;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  margin-bottom: 20px;
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--mono);
  font-size: 12.5px;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink-1);
}
.brand-mark {
  width: 18px; height: 18px;
  display: inline-grid; place-items: center;
  background: var(--ink-1);
  color: var(--bg);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  border-radius: 2px;
  line-height: 1;
}
.topbar-path {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-2);
  word-break: break-all;
  padding: 4px 10px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 3px;
  justify-self: start;
}
.topbar-meta {
  display: flex;
  gap: 18px;
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.04em;
  color: var(--ink-3);
}
.topbar-meta span strong {
  color: var(--ink-2);
  font-weight: 600;
}
.theme-toggle {
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--ink-2);
  width: 30px; height: 30px;
  display: inline-grid; place-items: center;
  cursor: pointer;
  border-radius: 3px;
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1;
  padding: 0;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}
.theme-toggle:hover {
  border-color: var(--border-strong);
  color: var(--ink-1);
}
.theme-toggle::before { content: attr(data-icon); }
.theme-toggle[data-theme="auto"] { color: var(--ink-3); }
.theme-toggle[data-theme="light"] { color: var(--warning); }
.theme-toggle[data-theme="dark"] { color: var(--info); }

/* ============ KPIs ============ */
.kpis {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.kpi {
  position: relative;
  background: var(--surface);
  border: 1px solid var(--border);
  padding: 16px 18px 22px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-height: 124px;
}
.kpi-label {
  font-size: 10.5px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
}
.kpi-value {
  font-family: var(--mono);
  font-size: 34px;
  font-weight: 500;
  letter-spacing: -0.02em;
  color: var(--ink-1);
  line-height: 1;
  margin-top: 2px;
  font-variant-numeric: tabular-nums lining-nums;
}
.kpi-unit {
  font-family: var(--mono);
  font-size: 14px;
  color: var(--ink-3);
  font-weight: 400;
  margin-left: 6px;
  letter-spacing: 0;
}
.kpi-sub {
  font-size: 12px;
  color: var(--ink-2);
  line-height: 1.45;
  margin-top: auto;
}
.kpi-strip {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  height: 3px;
  background: var(--border-strong);
}
.kpi--ok .kpi-strip { background: var(--ok); }
.kpi--info .kpi-strip { background: var(--info); }
.kpi--warning .kpi-strip { background: var(--warning); }
.kpi--critical .kpi-strip { background: var(--critical); }
.kpi--critical .kpi-value { color: var(--critical); }

/* ============ Panels ============ */
.panel {
  background: var(--surface);
  border: 1px solid var(--border);
  margin-bottom: 16px;
}
.panel-h {
  display: flex;
  align-items: baseline;
  gap: 14px;
  padding: 14px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-alt);
}
.panel-h h2 {
  margin: 0;
  font-size: 12px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-1);
}
.panel-sub {
  font-size: 11.5px;
  color: var(--ink-3);
}
.panel-foot {
  padding: 10px 20px;
  border-top: 1px solid var(--border);
  font-size: 11.5px;
  color: var(--ink-3);
  background: var(--surface-alt);
}

/* Expand block (top-consumers overflow) */
.expand {
  border-top: 1px solid var(--border);
  background: var(--surface);
}
.expand-summary {
  cursor: pointer;
  user-select: none;
  list-style: none;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 20px;
  font-size: 11.5px;
  letter-spacing: 0.04em;
  background: var(--surface-alt);
  border-bottom: 1px solid transparent;
  transition: background 0.15s, color 0.15s, border-color 0.15s;
}
.expand-summary::-webkit-details-marker { display: none; }
.expand-summary:hover {
  background: var(--surface);
  color: var(--ink-1);
}
.expand-summary:focus-visible {
  outline: 2px solid var(--info);
  outline-offset: -2px;
}
.expand-toggle {
  display: inline-block;
  width: 0; height: 0;
  border-style: solid;
  border-width: 5px 0 5px 8px;
  border-color: transparent transparent transparent var(--ink-3);
  transition: transform 0.18s ease;
  flex-shrink: 0;
}
.expand[open] .expand-toggle { transform: rotate(90deg); }
.expand[open] .expand-summary {
  border-bottom-color: var(--border);
  color: var(--ink-1);
  background: var(--surface);
}
.expand-label {
  font-family: var(--mono);
  color: var(--ink-2);
  font-size: 12px;
}
.expand[open] .expand-label { color: var(--ink-1); }
.expand-hint {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}
.dt--continuation thead {
  /* Continuation table — keep header subtle since it's a repeat */
}
.dt--continuation thead th {
  background: var(--surface);
  color: var(--ink-4);
  font-size: 9.5px;
}

/* ============ Utilization chart ============ */
.util-chart {
  padding: 20px 20px 8px;
}
.util-chart svg {
  width: 100%;
  height: auto;
  overflow: visible;
}
.util-baseline { stroke: var(--ink-1); stroke-width: 1; }
.util-tick { stroke: var(--ink-2); stroke-width: 1; }
.util-tick-label {
  font-family: var(--mono);
  font-size: 10px;
  fill: var(--ink-3);
}
.util-wall {
  stroke: var(--ink-1);
  stroke-width: 1.5;
  stroke-dasharray: 3 2;
}
.util-wall-label {
  font-family: var(--mono);
  font-size: 10.5px;
  fill: var(--ink-2);
  letter-spacing: 0.08em;
  font-weight: 600;
}
.util-over-label {
  font-family: var(--mono);
  font-size: 10.5px;
  fill: var(--critical);
  font-weight: 700;
  letter-spacing: 0.08em;
}
.util-seg { transition: opacity 0.15s; }
.util-seg:hover { opacity: 0.85; }
.util-seg--claude-md { fill: var(--cat-claude-md); }
.util-seg--agent { fill: var(--cat-agent); }
.util-seg--skill { fill: var(--cat-skill); }
.util-seg--rule { fill: var(--cat-rule); }
.util-seg--over { fill: var(--critical); }

.util-legend {
  padding: 12px 20px 18px;
  display: grid;
  gap: 4px;
}
.leg-row {
  display: grid;
  grid-template-columns: 14px 1fr 90px 60px 90px;
  align-items: center;
  gap: 12px;
  padding: 6px 0;
  font-size: 12.5px;
  border-bottom: 1px solid var(--border-faint);
}
.leg-row:last-child { border-bottom: none; }
.leg-swatch {
  display: inline-block;
  width: 10px; height: 10px;
  border-radius: 2px;
  vertical-align: middle;
  background: var(--ink-2);
}
.leg-swatch--claude-md { background: var(--cat-claude-md); }
.leg-swatch--agent { background: var(--cat-agent); }
.leg-swatch--skill { background: var(--cat-skill); }
.leg-swatch--rule { background: var(--cat-rule); }
.leg-name {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-1);
}
.leg-files {
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  text-align: right;
}
.leg-pct {
  font-family: var(--mono);
  font-size: 12px;
  color: var(--ink-2);
  text-align: right;
}
.leg-tok {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  text-align: right;
  font-weight: 500;
}

/* ============ Data tables ============ */
.dt {
  width: 100%;
  border-collapse: collapse;
  font-size: 12.5px;
}
.dt thead th {
  text-align: left;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-alt);
}
.dt tbody td {
  padding: 10px 14px;
  border-bottom: 1px solid var(--border-faint);
  vertical-align: middle;
}
.dt tbody tr:hover td { background: var(--surface-alt); }
.dt tbody tr:last-child td { border-bottom: none; }

.t-rank {
  width: 40px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
  letter-spacing: 0.04em;
}
.t-cat {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  width: 140px;
}
.t-cat-small { width: 80px; }
.t-path code {
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  background: transparent;
  word-break: break-all;
}
.t-num {
  text-align: right;
  font-family: var(--mono);
  font-size: 12.5px;
  color: var(--ink-1);
  white-space: nowrap;
}
.t-num-pct {
  width: 70px;
  color: var(--ink-2);
}
.t-num-tok {
  width: 100px;
  font-weight: 500;
}
.t-bar {
  width: 35%;
  padding-right: 18px;
}
th.t-num, th.t-num-pct, th.t-num-tok { text-align: right; }

.row-bar {
  display: block;
  height: 8px;
  background: var(--ink-1);
  border-radius: 1px;
}
.row-bar--claude-md { background: var(--cat-claude-md); }
.row-bar--agent { background: var(--cat-agent); }
.row-bar--skill { background: var(--cat-skill); }
.row-bar--rule { background: var(--cat-rule); }

.cat-tag {
  display: inline-block;
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  border: 1px solid currentColor;
  border-radius: 2px;
  text-transform: lowercase;
  background: transparent;
}
.cat-tag--claude-md { color: var(--cat-claude-md); background: var(--cat-claude-md-bg); border-color: transparent; }
.cat-tag--agent { color: var(--cat-agent); background: var(--cat-agent-bg); border-color: transparent; }
.cat-tag--skill { color: var(--cat-skill); background: var(--cat-skill-bg); border-color: transparent; }
.cat-tag--rule { color: var(--cat-rule); background: var(--cat-rule-bg); border-color: transparent; }

/* ============ Findings ============ */
.f-group { padding: 14px 20px 18px; border-bottom: 1px solid var(--border); }
.f-group:last-child { border-bottom: none; }
.f-group-h {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 10px;
}
.f-group-sev {
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 2px;
}
.f-group-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--ink-1);
}
.f-group-blurb {
  font-size: 12px;
  color: var(--ink-3);
}
.f-group-count {
  margin-left: auto;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink-3);
}

.f-list { list-style: none; padding: 0; margin: 0; }
.f {
  display: grid;
  grid-template-columns: 12px 88px 1fr;
  gap: 14px;
  padding: 12px 0;
  border-bottom: 1px dotted var(--border);
  align-items: start;
}
.f:last-child { border-bottom: none; }
.f-bullet {
  width: 5px; height: 5px;
  border-radius: 50%;
  margin-top: 8px;
  margin-left: 4px;
  background: var(--ink-3);
}
.f--error .f-bullet { background: var(--critical); }
.f--warning .f-bullet { background: var(--warning); }
.f--info .f-bullet { background: var(--info); }
.f-code code {
  font-family: var(--mono);
  font-size: 11px;
  letter-spacing: 0.04em;
  padding: 2px 6px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  border-radius: 2px;
  color: var(--ink-2);
  white-space: nowrap;
}
.f-body { min-width: 0; }
.f-msg {
  font-size: 13px;
  color: var(--ink-1);
  line-height: 1.5;
}
.f-path {
  display: inline-block;
  margin-top: 4px;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-3);
  background: transparent;
  word-break: break-all;
}
.f-path--none { font-style: italic; }
.f-hint {
  margin-top: 6px;
  font-size: 12px;
  color: var(--ink-2);
  padding-left: 14px;
  border-left: 2px solid var(--border-strong);
}

.sev {
  display: inline-block;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.sev-error { color: var(--critical); background: var(--critical-bg); }
.sev-warning { color: var(--warning); background: var(--warning-bg); }
.sev-info { color: var(--info); background: var(--info-bg); }

.all-clear {
  display: flex;
  gap: 14px;
  align-items: center;
  padding: 20px;
  margin: 14px 20px;
  background: var(--ok-bg);
  border: 1px solid var(--ok-line);
  border-left: 3px solid var(--ok);
}
.all-clear-mark {
  font-size: 22px;
  color: var(--ok);
  font-weight: 700;
}
.all-clear strong { color: var(--ok); font-size: 14px; font-weight: 600; display: block; }
.all-clear span { color: var(--ink-2); font-size: 12px; }

/* ============ Footer ============ */
.colophon {
  margin-top: 24px;
  padding: 16px 20px;
  background: var(--surface);
  border: 1px solid var(--border);
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
  align-items: start;
}
.colophon-block { display: grid; gap: 4px; }
.colophon-row {
  display: grid;
  grid-template-columns: 130px 1fr;
  gap: 12px;
  font-size: 11.5px;
}
.colophon-row dt {
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--ink-3);
  padding-top: 2px;
}
.colophon-row dd {
  margin: 0;
  font-family: var(--mono);
  font-size: 11.5px;
  color: var(--ink-1);
}
.colophon-note {
  grid-column: 1 / -1;
  font-size: 11.5px;
  color: var(--ink-3);
  border-top: 1px solid var(--border-faint);
  padding-top: 12px;
  line-height: 1.55;
}
.colophon-note .ro {
  font-family: var(--mono);
  font-size: 10.5px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 600;
  padding: 1px 6px;
  background: var(--surface-alt);
  border: 1px solid var(--border);
  color: var(--ink-2);
  margin-right: 8px;
}

@media (max-width: 920px) {
  .kpis { grid-template-columns: repeat(2, 1fr); }
  .topbar { grid-template-columns: 1fr; }
  .topbar-path { justify-self: stretch; }
}
@media (max-width: 560px) {
  .kpis { grid-template-columns: 1fr; }
  .leg-row { grid-template-columns: 14px 1fr auto; }
  .leg-files, .leg-pct { display: none; }
  .f { grid-template-columns: 12px 1fr; }
  .f-code { grid-column: 2; }
  .colophon { grid-template-columns: 1fr; }
}

/* ============ Info tooltips ============
   Tiny ⓘ button next to KPI labels and panel titles. Reveals a
   tooltip on hover, keyboard focus, or tap (data-open is toggled by
   the inline script). Tooltip colours invert the page palette so
   the bubble stands out in both themes. */
.info {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 14px;
  height: 14px;
  margin-left: 6px;
  padding: 0;
  border-radius: 50%;
  border: 1px solid var(--ink-4);
  background: transparent;
  color: var(--ink-3);
  font-family: var(--sans);
  font-size: 9px;
  font-weight: 700;
  line-height: 1;
  cursor: help;
  user-select: none;
  vertical-align: middle;
  transition: color 0.12s, border-color 0.12s, background 0.12s;
}
.info:hover,
.info:focus-visible,
.info[data-open="true"] {
  color: var(--ink-1);
  border-color: var(--ink-1);
  background: var(--surface);
  outline: none;
}
.info-mark { pointer-events: none; }

.info-tip {
  position: absolute;
  top: calc(100% + 8px);
  right: -6px;
  z-index: 50;
  width: 260px;
  padding: 10px 12px;
  background: var(--ink-1);
  color: var(--surface);
  border-radius: 4px;
  font-family: var(--sans);
  font-size: 11.5px;
  font-weight: 400;
  line-height: 1.5;
  letter-spacing: 0;
  text-transform: none;
  text-align: left;
  cursor: default;
  opacity: 0;
  transform: translateY(-2px);
  pointer-events: none;
  transition: opacity 0.14s ease, transform 0.14s ease;
  box-shadow: 0 6px 20px -6px rgba(0, 0, 0, 0.25);
  /* Small triangle pointing back at the icon. */
}
.info-tip::before {
  content: "";
  position: absolute;
  top: -5px;
  right: 8px;
  width: 0; height: 0;
  border-left: 5px solid transparent;
  border-right: 5px solid transparent;
  border-bottom: 5px solid var(--ink-1);
}
.info:hover .info-tip,
.info:focus-visible .info-tip,
.info[data-open="true"] .info-tip {
  opacity: 1;
  transform: translateY(0);
  pointer-events: auto;
}

/* Some hosts (KPI label, panel h2) are uppercase tracked — undo that
   inside tooltip text so the prose reads naturally. */
.info-tip {
  letter-spacing: normal;
  font-weight: 400;
}

/* Make the KPI label a flex row so the button doesn't blow out spacing. */
.kpi-label {
  display: flex;
  align-items: center;
  gap: 2px;
}
"""
