"""HTML page template + inline theme-toggle script."""

_PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<main class="doc {doc_severity_class}">

  <header class="topbar">
    <div class="brand">
      <span class="brand-mark">▣</span>
      claude-config-auditor
    </div>
    <code class="topbar-path">{subject}</code>
    <div class="topbar-meta">
      <span><strong>v{version}</strong></span>
      <span>{generated_at}</span>
      <span>id <strong>{report_id}</strong></span>
      <button class="theme-toggle" id="theme-toggle"
              type="button" aria-label="Cycle color theme"
              title="Cycle theme (auto / light / dark)"></button>
    </div>
  </header>

  {kpis}
  {utilization}
  {categories}
  {consumers}
  {findings}

  <footer class="colophon">
    <div class="colophon-block">
      <div class="colophon-row"><dt>Tool</dt><dd>claude-config-auditor v{version}</dd></div>
      <div class="colophon-row"><dt>Report ID</dt><dd>{report_id}</dd></div>
    </div>
    <div class="colophon-block">
      <div class="colophon-row"><dt>Generated</dt><dd>{generated_at}</dd></div>
      <div class="colophon-row"><dt>Tokenizer</dt><dd>{tokenizer}</dd></div>
    </div>
    <p class="colophon-note">
      <span class="ro">Read-only</span>
      {tokenizer_note} No files in the audited target were modified.
    </p>
  </footer>

</main>

<script>
/* Theme toggle: cycles auto -> light -> dark -> auto, persisted in
   localStorage. "auto" defers to prefers-color-scheme. Inline because the
   report file must remain self-contained (no external network). */
(function () {{
  var KEY = "cca-theme";
  var ICONS = {{ auto: "◑", light: "☀", dark: "☾" }};
  var ORDER = ["auto", "light", "dark"];
  var root = document.documentElement;
  var btn = document.getElementById("theme-toggle");
  function apply(theme) {{
    if (theme === "auto") {{
      root.removeAttribute("data-theme");
    }} else {{
      root.setAttribute("data-theme", theme);
    }}
    btn.dataset.theme = theme;
    btn.dataset.icon = ICONS[theme];
    btn.setAttribute(
      "aria-label",
      "Cycle color theme (current: " + theme + ")"
    );
  }}
  var stored;
  try {{ stored = localStorage.getItem(KEY); }} catch (e) {{ stored = null; }}
  apply(stored && ORDER.indexOf(stored) >= 0 ? stored : "auto");
  btn.addEventListener("click", function () {{
    var i = ORDER.indexOf(btn.dataset.theme);
    var next = ORDER[(i + 1) % ORDER.length];
    try {{ localStorage.setItem(KEY, next); }} catch (e) {{}}
    apply(next);
  }});
}})();

/* Info tooltips: tap-to-toggle for touch devices that have no hover
   state. Desktop users still get the CSS hover behaviour for free. */
(function () {{
  var openTip = null;
  function close(b) {{ if (b) b.removeAttribute("data-open"); }}
  document.querySelectorAll(".info").forEach(function (btn) {{
    btn.addEventListener("click", function (e) {{
      e.stopPropagation();
      if (openTip && openTip !== btn) close(openTip);
      if (btn.dataset.open === "true") {{
        close(btn);
        openTip = null;
      }} else {{
        btn.setAttribute("data-open", "true");
        openTip = btn;
      }}
    }});
  }});
  // Clicking anywhere else closes the open tooltip.
  document.addEventListener("click", function () {{
    if (openTip) {{ close(openTip); openTip = null; }}
  }});
  // Esc also closes — keyboard-friendly.
  document.addEventListener("keydown", function (e) {{
    if (e.key === "Escape" && openTip) {{ close(openTip); openTip = null; }}
  }});
}})();
</script>
</body>
</html>
"""
